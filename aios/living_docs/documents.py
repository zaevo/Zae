"""
Living Documentation

Documents that rewrite themselves as projects evolve.
Not static files — dynamic knowledge artifacts that stay accurate automatically.
"""

import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from ..agents.base import BaseAgent
from ..config import config
from ..memory.manager import memory
from ..system_prompt import MASTER_SYSTEM_PROMPT


LIVING_DOC_AGENT_PROMPT = f"""
{MASTER_SYSTEM_PROMPT}

## YOUR ROLE: Living Documentation Agent

You maintain documents that automatically update as projects evolve.
Given a current document and new information, you produce an updated version.

Rules:
- Preserve accurate information
- Update stale or outdated sections
- Add new sections for new developments
- Remove sections that are no longer relevant
- Mark changes with a changelog entry
- Never lose important historical context — archive it, don't delete it

Output format:
---
CHANGELOG: [What changed and why]
---
[Updated document content]
"""


@dataclass
class LivingDocument:
    id: str
    title: str
    content: str
    document_type: str          # "project_overview" | "decision_log" | "status" | "runbook" | "custom"
    project_id: str | None
    version: int
    created_at: datetime
    updated_at: datetime
    update_triggers: list[str]  # What kinds of new info should trigger an update
    changelog: list[dict] = field(default_factory=list)


class LivingDocumentSystem:
    """
    Manages documents that update themselves when relevant new information arrives.
    """

    def __init__(self):
        self._conn: sqlite3.Connection | None = None
        self._agent = _LivingDocAgent()
        self._initialized = False

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            db_path = config.db_path
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def initialize(self) -> None:
        if self._initialized:
            return
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS living_documents (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                document_type TEXT DEFAULT 'custom',
                project_id TEXT,
                version INTEGER DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                update_triggers TEXT DEFAULT '[]',
                changelog TEXT DEFAULT '[]'
            );

            CREATE INDEX IF NOT EXISTS idx_ld_project ON living_documents(project_id);
            CREATE INDEX IF NOT EXISTS idx_ld_type ON living_documents(document_type);
        """)
        conn.commit()
        self._initialized = True

    def create(
        self,
        title: str,
        initial_content: str,
        document_type: str = "custom",
        project_id: str | None = None,
        update_triggers: list[str] | None = None,
    ) -> LivingDocument:
        if not self._initialized:
            self.initialize()

        now = datetime.utcnow()
        doc = LivingDocument(
            id=str(uuid.uuid4()),
            title=title,
            content=initial_content,
            document_type=document_type,
            project_id=project_id,
            version=1,
            created_at=now,
            updated_at=now,
            update_triggers=update_triggers or ["project update", "status change", "new decision"],
        )
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO living_documents
               (id, title, content, document_type, project_id, version,
                created_at, updated_at, update_triggers, changelog)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                doc.id, doc.title, doc.content, doc.document_type,
                doc.project_id, doc.version,
                now.isoformat(), now.isoformat(),
                json.dumps(doc.update_triggers), json.dumps([]),
            ),
        )
        conn.commit()
        return doc

    async def update(
        self, doc_id: str, new_information: str, reason: str = ""
    ) -> LivingDocument:
        if not self._initialized:
            self.initialize()

        doc = self.get(doc_id)
        if not doc:
            raise ValueError(f"Document {doc_id} not found")

        result = await self._agent.run(
            f"CURRENT DOCUMENT (v{doc.version}):\n{doc.content}\n\n"
            f"NEW INFORMATION:\n{new_information}\n\n"
            f"UPDATE REASON: {reason or 'New information available'}\n\n"
            f"Update the document to reflect this new information."
        )
        if not result.succeeded:
            return doc

        # Parse changelog and new content
        new_content, changelog_entry = self._parse_update(result.content)
        if not new_content:
            return doc

        now = datetime.utcnow()
        new_version = doc.version + 1
        new_changelog = doc.changelog + [{
            "version": new_version,
            "change": changelog_entry,
            "reason": reason,
            "updated_at": now.isoformat(),
        }]

        conn = self._get_conn()
        conn.execute(
            """UPDATE living_documents
               SET content = ?, version = ?, updated_at = ?, changelog = ?
               WHERE id = ?""",
            (new_content, new_version, now.isoformat(), json.dumps(new_changelog), doc_id),
        )
        conn.commit()
        doc.content = new_content
        doc.version = new_version
        doc.updated_at = now
        doc.changelog = new_changelog
        return doc

    async def auto_update_from_memory(
        self, doc_id: str, project_id: str | None = None
    ) -> LivingDocument | None:
        """Pull recent memory and update the document if relevant new info exists."""
        doc = self.get(doc_id)
        if not doc:
            return None

        context = memory.retrieve_context_for_task(
            " ".join(doc.update_triggers), project_id=project_id or doc.project_id
        )
        if not context or len(context) < 100:
            return doc

        return await self.update(doc_id, context, reason="Auto-update from project memory")

    def get(self, doc_id: str) -> LivingDocument | None:
        if not self._initialized:
            self.initialize()
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM living_documents WHERE id = ?", (doc_id,)
        ).fetchone()
        return self._row_to_doc(row) if row else None

    def list_documents(self, project_id: str | None = None) -> list[LivingDocument]:
        if not self._initialized:
            self.initialize()
        conn = self._get_conn()
        if project_id:
            rows = conn.execute(
                "SELECT * FROM living_documents WHERE project_id = ? ORDER BY updated_at DESC",
                (project_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM living_documents ORDER BY updated_at DESC LIMIT 20"
            ).fetchall()
        return [self._row_to_doc(r) for r in rows]

    def _parse_update(self, response: str) -> tuple[str, str]:
        changelog = ""
        content = response
        if "CHANGELOG:" in response:
            parts = response.split("---", 2)
            if len(parts) >= 2:
                changelog = parts[1].replace("CHANGELOG:", "").strip()
                content = parts[2].strip() if len(parts) > 2 else parts[1]
        return content, changelog

    def _row_to_doc(self, row: sqlite3.Row) -> LivingDocument:
        return LivingDocument(
            id=row["id"], title=row["title"], content=row["content"],
            document_type=row["document_type"], project_id=row["project_id"],
            version=row["version"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            update_triggers=json.loads(row["update_triggers"] or "[]"),
            changelog=json.loads(row["changelog"] or "[]"),
        )


class _LivingDocAgent(BaseAgent):
    name = "living_doc_agent"

    def __init__(self):
        super().__init__()
        self._system_prompt = LIVING_DOC_AGENT_PROMPT
        self.model = config.worker_model


living_docs = LivingDocumentSystem()
