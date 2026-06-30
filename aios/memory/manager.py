import asyncio
import json
import sqlite3
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from ..config import config
from .types import Memory, MemoryQueryResult, MemoryStatus, MemoryType


class MemoryManager:
    """
    Unified memory system with episodic, semantic, project, procedural,
    and preference memory. Backed by SQLite for persistence and ChromaDB
    for vector similarity search.
    """

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or config.db_path
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None
        self._vector_store = None
        self._initialized = False

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def initialize(self) -> None:
        if self._initialized:
            return
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata TEXT DEFAULT '{}',
                importance REAL DEFAULT 5.0,
                confidence REAL DEFAULT 1.0,
                created_at TEXT NOT NULL,
                accessed_at TEXT NOT NULL,
                access_count INTEGER DEFAULT 0,
                status TEXT DEFAULT 'active',
                tags TEXT DEFAULT '[]',
                project_id TEXT,
                session_id TEXT,
                source_agent TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_memories_type ON memories(type);
            CREATE INDEX IF NOT EXISTS idx_memories_project ON memories(project_id);
            CREATE INDEX IF NOT EXISTS idx_memories_status ON memories(status);
            CREATE INDEX IF NOT EXISTS idx_memories_importance ON memories(importance DESC);

            CREATE TABLE IF NOT EXISTS knowledge_nodes (
                id TEXT PRIMARY KEY,
                label TEXT NOT NULL,
                node_type TEXT NOT NULL,
                properties TEXT DEFAULT '{}',
                confidence REAL DEFAULT 1.0,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS knowledge_edges (
                id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL,
                target_id TEXT NOT NULL,
                relationship TEXT NOT NULL,
                weight REAL DEFAULT 1.0,
                confidence REAL DEFAULT 1.0,
                metadata TEXT DEFAULT '{}',
                FOREIGN KEY(source_id) REFERENCES knowledge_nodes(id),
                FOREIGN KEY(target_id) REFERENCES knowledge_nodes(id)
            );

            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                started_at TEXT NOT NULL,
                ended_at TEXT,
                task_count INTEGER DEFAULT 0,
                summary TEXT
            );

            CREATE TABLE IF NOT EXISTS heuristics (
                id TEXT PRIMARY KEY,
                domain TEXT NOT NULL,
                rule TEXT NOT NULL,
                confidence REAL DEFAULT 0.5,
                applications INTEGER DEFAULT 0,
                successes INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
        """)
        conn.commit()
        self._try_init_vector_store()
        self._initialized = True

    def _try_init_vector_store(self) -> None:
        try:
            import chromadb
            Path(config.vector_path).mkdir(parents=True, exist_ok=True)
            client = chromadb.PersistentClient(path=config.vector_path)
            self._vector_store = client.get_or_create_collection(
                name="aios_memories",
                metadata={"hnsw:space": "cosine"},
            )
        except ImportError:
            pass  # ChromaDB optional; falls back to SQLite FTS

    def store(
        self,
        content: str,
        memory_type: MemoryType,
        importance: float = 5.0,
        confidence: float = 1.0,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        project_id: str | None = None,
        session_id: str | None = None,
        source_agent: str | None = None,
    ) -> Memory:
        if not self._initialized:
            self.initialize()

        memory = Memory(
            id=str(uuid.uuid4()),
            type=memory_type,
            content=content,
            metadata=metadata or {},
            importance=min(10.0, max(0.0, importance)),
            confidence=min(1.0, max(0.0, confidence)),
            created_at=datetime.utcnow(),
            accessed_at=datetime.utcnow(),
            tags=tags or [],
            project_id=project_id,
            session_id=session_id,
            source_agent=source_agent,
        )

        conn = self._get_conn()
        conn.execute(
            """INSERT INTO memories
               (id, type, content, metadata, importance, confidence,
                created_at, accessed_at, access_count, status, tags,
                project_id, session_id, source_agent)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                memory.id, memory.type.value, memory.content,
                json.dumps(memory.metadata), memory.importance, memory.confidence,
                memory.created_at.isoformat(), memory.accessed_at.isoformat(),
                memory.access_count, memory.status.value, json.dumps(memory.tags),
                memory.project_id, memory.session_id, memory.source_agent,
            ),
        )
        conn.commit()

        self._index_in_vector_store(memory)
        return memory

    def _index_in_vector_store(self, memory: Memory) -> None:
        if self._vector_store is None:
            return
        try:
            self._vector_store.add(
                documents=[memory.content],
                metadatas=[{
                    "memory_id": memory.id,
                    "type": memory.type.value,
                    "importance": memory.importance,
                    "tags": ",".join(memory.tags),
                }],
                ids=[memory.id],
            )
        except Exception:
            pass

    def query(
        self,
        query: str,
        memory_types: list[MemoryType] | None = None,
        top_k: int | None = None,
        min_importance: float = 0.0,
        project_id: str | None = None,
    ) -> list[MemoryQueryResult]:
        if not self._initialized:
            self.initialize()

        top_k = top_k or config.memory_top_k
        results = self._vector_query(query, top_k * 2) if self._vector_store else []

        if not results:
            results = self._sqlite_fts_query(query, top_k * 2)

        filtered = []
        for r in results:
            if r.memory.importance < min_importance:
                continue
            if memory_types and r.memory.type not in memory_types:
                continue
            if project_id and r.memory.project_id != project_id:
                continue
            filtered.append(r)

        filtered.sort(key=lambda x: x.relevance_score, reverse=True)
        return filtered[:top_k]

    def _vector_query(self, query: str, top_k: int) -> list[MemoryQueryResult]:
        if self._vector_store is None:
            return []
        try:
            results = self._vector_store.query(
                query_texts=[query],
                n_results=min(top_k, self._vector_store.count() or 1),
            )
            memories = []
            if not results["ids"][0]:
                return []
            for i, mem_id in enumerate(results["ids"][0]):
                memory = self._load_by_id(mem_id)
                if memory:
                    distance = results["distances"][0][i]
                    memories.append(MemoryQueryResult(
                        memory=memory,
                        relevance_score=1.0 - distance,
                        distance=distance,
                    ))
            return memories
        except Exception:
            return []

    def _sqlite_fts_query(self, query: str, top_k: int) -> list[MemoryQueryResult]:
        conn = self._get_conn()
        keywords = " OR ".join(f'"%{w}%"' for w in query.split()[:5])
        rows = conn.execute(
            f"""SELECT * FROM memories
                WHERE status = 'active' AND content LIKE ?
                ORDER BY importance DESC LIMIT ?""",
            (f"%{query[:50]}%", top_k),
        ).fetchall()
        return [
            MemoryQueryResult(
                memory=self._row_to_memory(row),
                relevance_score=row["importance"] / 10.0,
                distance=1.0 - row["importance"] / 10.0,
            )
            for row in rows
        ]

    def _load_by_id(self, memory_id: str) -> Memory | None:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM memories WHERE id = ?", (memory_id,)
        ).fetchone()
        return self._row_to_memory(row) if row else None

    def _row_to_memory(self, row: sqlite3.Row) -> Memory:
        return Memory(
            id=row["id"],
            type=MemoryType(row["type"]),
            content=row["content"],
            metadata=json.loads(row["metadata"] or "{}"),
            importance=row["importance"],
            confidence=row["confidence"],
            created_at=datetime.fromisoformat(row["created_at"]),
            accessed_at=datetime.fromisoformat(row["accessed_at"]),
            access_count=row["access_count"],
            status=MemoryStatus(row["status"]),
            tags=json.loads(row["tags"] or "[]"),
            project_id=row["project_id"],
            session_id=row["session_id"],
            source_agent=row["source_agent"],
        )

    def retrieve_context_for_task(
        self, task: str, session_id: str | None = None, project_id: str | None = None
    ) -> str:
        results = self.query(task, top_k=config.memory_top_k)
        if not results:
            return ""

        sections = {
            MemoryType.EPISODIC: [],
            MemoryType.PROJECT: [],
            MemoryType.SEMANTIC: [],
            MemoryType.PREFERENCE: [],
            MemoryType.PROCEDURAL: [],
        }
        for r in results:
            sections[r.memory.type].append(
                f"[{r.relevance_score:.2f}] {r.memory.content}"
            )

        parts = []
        if sections[MemoryType.PROJECT]:
            parts.append("## Active Project Context\n" + "\n".join(sections[MemoryType.PROJECT]))
        if sections[MemoryType.EPISODIC]:
            parts.append("## Past Experience\n" + "\n".join(sections[MemoryType.EPISODIC]))
        if sections[MemoryType.SEMANTIC]:
            parts.append("## Relevant Knowledge\n" + "\n".join(sections[MemoryType.SEMANTIC]))
        if sections[MemoryType.PREFERENCE]:
            parts.append("## User Preferences\n" + "\n".join(sections[MemoryType.PREFERENCE]))
        if sections[MemoryType.PROCEDURAL]:
            parts.append("## Relevant Workflows\n" + "\n".join(sections[MemoryType.PROCEDURAL]))

        return "\n\n".join(parts)

    def consolidate(self, session_id: str | None = None) -> int:
        """Merge overlapping memories, decay old ones, prune low-value ones."""
        if not self._initialized:
            self.initialize()
        conn = self._get_conn()
        cutoff = (datetime.utcnow() - timedelta(days=config.memory_decay_days)).isoformat()
        result = conn.execute(
            """UPDATE memories SET status = 'decayed'
               WHERE accessed_at < ? AND importance < 3.0 AND status = 'active'""",
            (cutoff,),
        )
        conn.commit()
        return result.rowcount

    def store_heuristic(
        self, domain: str, rule: str, confidence: float = 0.5
    ) -> None:
        if not self._initialized:
            self.initialize()
        conn = self._get_conn()
        now = datetime.utcnow().isoformat()
        conn.execute(
            """INSERT OR REPLACE INTO heuristics
               (id, domain, rule, confidence, applications, successes, created_at, updated_at)
               VALUES (?, ?, ?, ?, 0, 0, ?, ?)""",
            (str(uuid.uuid4()), domain, rule, confidence, now, now),
        )
        conn.commit()

    def get_heuristics(self, domain: str) -> list[dict]:
        if not self._initialized:
            self.initialize()
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM heuristics WHERE domain = ? ORDER BY confidence DESC LIMIT 10",
            (domain,),
        ).fetchall()
        return [dict(r) for r in rows]


# Module-level singleton
memory = MemoryManager()
