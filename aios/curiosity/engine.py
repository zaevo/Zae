"""
Curiosity Engine + Knowledge Gap Tracker
Notices knowledge gaps while working, stores them, and autonomously
investigates the highest-priority ones in the background.
Real intelligence is driven to fill its own gaps.
"""

import json
import sqlite3
import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from ..config import config

GAP_EXTRACTOR_PROMPT = """You are a Curiosity Engine. Your job is to notice what you DON'T know.

After processing this task and generating a response, identify knowledge gaps:
- Questions you couldn't fully answer
- Claims you made with low confidence
- Related questions that would improve future responses
- Things that would be useful to know for similar future tasks
- Surprising things that warrant deeper investigation

Task: {task}
Response given: {response}

Return JSON array of knowledge gaps:
[
  {{
    "question": "The specific gap or open question",
    "why_matters": "How knowing this would improve future responses",
    "priority": 0.8,
    "domain": "the knowledge domain this falls in",
    "investigation_hint": "How one might find the answer"
  }}
]

Focus on gaps that are:
- Actually answerable (not pure opinion)
- Genuinely useful to know
- Not already obvious from the response

Return 2-5 gaps max. Empty array [] if there are none worth investigating."""

INVESTIGATOR_PROMPT = """You are an Autonomous Investigator. Investigate this knowledge gap thoroughly.

Knowledge Gap: {question}
Why it matters: {why_matters}
Investigation hint: {hint}

Prior context (from memory): {context}

Provide a thorough answer to this gap. Be specific, cite reasoning, note remaining uncertainties.
Format: Direct answer, then supporting reasoning, then any remaining open sub-questions."""


@dataclass
class KnowledgeGap:
    gap_id: int
    question: str
    why_matters: str
    priority: float
    domain: str
    investigation_hint: str
    source_task: str
    investigated: bool = False
    answer: str = ""
    discovered_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    investigated_at: str = ""


class CuriosityEngine:
    """
    Tracks knowledge gaps discovered during task execution.
    Autonomously investigates them in the background.
    """

    def __init__(self):
        self._db_path = Path(config.db_path).parent / "curiosity.db"
        self._investigating = False

    def initialize(self) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS knowledge_gaps (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    question TEXT NOT NULL,
                    why_matters TEXT,
                    priority REAL DEFAULT 0.5,
                    domain TEXT,
                    investigation_hint TEXT,
                    source_task TEXT,
                    investigated INTEGER DEFAULT 0,
                    answer TEXT DEFAULT '',
                    discovered_at TEXT DEFAULT (datetime('now')),
                    investigated_at TEXT DEFAULT ''
                )
            """)

    async def notice_gaps(self, task: str, response: str) -> list[KnowledgeGap]:
        """Extract knowledge gaps from a task/response pair and store them."""
        import anthropic

        client = anthropic.Anthropic(api_key=config.api_key)
        try:
            gap_response = client.messages.create(
                model=config.fast_model,
                max_tokens=1200,
                messages=[{"role": "user", "content": GAP_EXTRACTOR_PROMPT.format(
                    task=task[:1500],
                    response=response[:1500],
                )}],
            )
            text = gap_response.content[0].text
            start = text.find("[")
            end = text.rfind("]") + 1
            if start < 0 or end <= start:
                return []

            raw_gaps = json.loads(text[start:end])
            gaps: list[KnowledgeGap] = []

            with sqlite3.connect(self._db_path) as conn:
                for g in raw_gaps:
                    cursor = conn.execute("""
                        INSERT INTO knowledge_gaps
                        (question, why_matters, priority, domain, investigation_hint, source_task)
                        VALUES (?,?,?,?,?,?)
                    """, (
                        g.get("question", "")[:500],
                        g.get("why_matters", "")[:300],
                        float(g.get("priority", 0.5)),
                        g.get("domain", "general"),
                        g.get("investigation_hint", "")[:300],
                        task[:200],
                    ))
                    gaps.append(KnowledgeGap(
                        gap_id=cursor.lastrowid,
                        question=g.get("question", ""),
                        why_matters=g.get("why_matters", ""),
                        priority=float(g.get("priority", 0.5)),
                        domain=g.get("domain", "general"),
                        investigation_hint=g.get("investigation_hint", ""),
                        source_task=task[:200],
                    ))
            return gaps
        except Exception:
            return []

    async def investigate_next(self, memory_context: str = "") -> KnowledgeGap | None:
        """Investigate the highest-priority uninvestigated gap."""
        import anthropic

        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute("""
                SELECT id, question, why_matters, priority, domain, investigation_hint, source_task
                FROM knowledge_gaps
                WHERE investigated=0
                ORDER BY priority DESC
                LIMIT 1
            """).fetchone()

        if not row:
            return None

        gap_id, question, why_matters, priority, domain, hint, source_task = row

        client = anthropic.Anthropic(api_key=config.api_key)
        try:
            inv_response = client.messages.create(
                model=config.worker_model,
                max_tokens=2000,
                messages=[{"role": "user", "content": INVESTIGATOR_PROMPT.format(
                    question=question,
                    why_matters=why_matters,
                    hint=hint or "Use general reasoning and available knowledge.",
                    context=memory_context[:800] if memory_context else "None available.",
                )}],
            )
            answer = inv_response.content[0].text.strip()

            with sqlite3.connect(self._db_path) as conn:
                conn.execute("""
                    UPDATE knowledge_gaps
                    SET investigated=1, answer=?, investigated_at=datetime('now')
                    WHERE id=?
                """, (answer[:3000], gap_id))

            return KnowledgeGap(
                gap_id=gap_id,
                question=question,
                why_matters=why_matters,
                priority=priority,
                domain=domain,
                investigation_hint=hint or "",
                source_task=source_task,
                investigated=True,
                answer=answer,
            )
        except Exception:
            return None

    async def start_background_investigation(
        self, interval_seconds: int = 600, max_per_cycle: int = 3
    ) -> None:
        """Background loop: investigate gaps when the system is idle."""
        while True:
            await asyncio.sleep(interval_seconds)
            if self._investigating:
                continue
            self._investigating = True
            try:
                for _ in range(max_per_cycle):
                    result = await self.investigate_next()
                    if not result:
                        break
            except Exception:
                pass
            finally:
                self._investigating = False

    def get_open_gaps(self, limit: int = 20) -> list[KnowledgeGap]:
        """Return uninvestigated gaps sorted by priority."""
        try:
            with sqlite3.connect(self._db_path) as conn:
                rows = conn.execute("""
                    SELECT id, question, why_matters, priority, domain,
                           investigation_hint, source_task, investigated, answer
                    FROM knowledge_gaps
                    WHERE investigated=0
                    ORDER BY priority DESC
                    LIMIT ?
                """, (limit,)).fetchall()
            return [KnowledgeGap(
                gap_id=r[0], question=r[1], why_matters=r[2],
                priority=r[3], domain=r[4], investigation_hint=r[5],
                source_task=r[6], investigated=bool(r[7]), answer=r[8] or "",
            ) for r in rows]
        except Exception:
            return []

    def get_recent_discoveries(self, limit: int = 10) -> list[KnowledgeGap]:
        """Return recently investigated gaps with answers."""
        try:
            with sqlite3.connect(self._db_path) as conn:
                rows = conn.execute("""
                    SELECT id, question, why_matters, priority, domain,
                           investigation_hint, source_task, investigated, answer
                    FROM knowledge_gaps
                    WHERE investigated=1
                    ORDER BY investigated_at DESC
                    LIMIT ?
                """, (limit,)).fetchall()
            return [KnowledgeGap(
                gap_id=r[0], question=r[1], why_matters=r[2],
                priority=r[3], domain=r[4], investigation_hint=r[5],
                source_task=r[6], investigated=bool(r[7]), answer=r[8] or "",
            ) for r in rows]
        except Exception:
            return []

    def gap_stats(self) -> dict:
        try:
            with sqlite3.connect(self._db_path) as conn:
                total = conn.execute("SELECT COUNT(*) FROM knowledge_gaps").fetchone()[0]
                investigated = conn.execute(
                    "SELECT COUNT(*) FROM knowledge_gaps WHERE investigated=1"
                ).fetchone()[0]
            return {"total_gaps": total, "investigated": investigated, "pending": total - investigated}
        except Exception:
            return {"total_gaps": 0, "investigated": 0, "pending": 0}


curiosity_engine = CuriosityEngine()
