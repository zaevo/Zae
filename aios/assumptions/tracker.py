"""
Assumption Tracking Database

Every decision AIOS helps make gets tagged with its underlying assumptions.
When a new fact contradicts a stored assumption, every decision built on it
is automatically surfaced for review.

This is the "immune system" for bad decisions.
"""

import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from ..config import config
from ..agents.base import BaseAgent, AgentResult
from ..system_prompt import MASTER_SYSTEM_PROMPT


ASSUMPTION_EXTRACTOR_PROMPT = f"""
{MASTER_SYSTEM_PROMPT}

## YOUR ROLE: Assumption Extractor

You read a task and its result, then extract every assumption embedded in the reasoning.

An assumption is any statement that:
- Was taken for granted without verification
- Could be false in some circumstances
- Would change the conclusion if it were wrong

For each assumption, also produce:
- The "invalidation trigger" — what fact would prove this assumption wrong
- Impact if wrong: HIGH (conclusion collapses) / MEDIUM (conclusion weakens) / LOW (minor adjustment needed)

Output as JSON array:
[
  {{
    "assumption": "Restaurant margins in this market are approximately 15%",
    "domain": "finance",
    "invalidation_trigger": "actual margin data shows significantly different figure",
    "impact_if_wrong": "HIGH",
    "confidence": 0.7
  }}
]

Only output the JSON array. No preamble.
"""

INVALIDATION_CHECKER_PROMPT = f"""
{MASTER_SYSTEM_PROMPT}

## YOUR ROLE: Assumption Invalidation Checker

You receive:
1. A new fact or piece of information
2. A list of existing assumptions

Your job: determine which assumptions (if any) this new information contradicts or invalidates.

Be precise. An assumption is invalidated only if the new fact is genuinely contradictory,
not merely tangentially related.

Output as JSON:
{{
  "invalidated": [
    {{
      "assumption_id": "...",
      "reason": "Why this new fact invalidates the assumption",
      "severity": "FULL | PARTIAL"
    }}
  ],
  "unaffected_count": 12
}}
"""


@dataclass
class Assumption:
    id: str
    task_id: str
    content: str
    domain: str
    invalidation_trigger: str
    impact_if_wrong: str          # HIGH | MEDIUM | LOW
    confidence: float
    created_at: datetime
    status: str = "active"       # active | invalidated | verified | expired
    project_id: str | None = None
    invalidated_by: str | None = None
    invalidated_at: datetime | None = None


@dataclass
class InvalidationAlert:
    assumption: Assumption
    new_fact: str
    reason: str
    severity: str                 # FULL | PARTIAL
    decisions_at_risk: list[str]  # task IDs that depended on this assumption


class AssumptionTracker:
    """
    Tracks every assumption made across all AIOS tasks.
    Automatically alerts when new information invalidates past assumptions.
    """

    def __init__(self):
        self._conn: sqlite3.Connection | None = None
        self._extractor = _AssumptionExtractorAgent()
        self._checker = _InvalidationCheckerAgent()
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
            CREATE TABLE IF NOT EXISTS assumptions (
                id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                content TEXT NOT NULL,
                domain TEXT DEFAULT 'general',
                invalidation_trigger TEXT,
                impact_if_wrong TEXT DEFAULT 'MEDIUM',
                confidence REAL DEFAULT 0.7,
                created_at TEXT NOT NULL,
                status TEXT DEFAULT 'active',
                project_id TEXT,
                invalidated_by TEXT,
                invalidated_at TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_assumptions_status ON assumptions(status);
            CREATE INDEX IF NOT EXISTS idx_assumptions_project ON assumptions(project_id);
            CREATE INDEX IF NOT EXISTS idx_assumptions_domain ON assumptions(domain);

            CREATE TABLE IF NOT EXISTS assumption_task_links (
                assumption_id TEXT NOT NULL,
                task_id TEXT NOT NULL,
                PRIMARY KEY (assumption_id, task_id),
                FOREIGN KEY(assumption_id) REFERENCES assumptions(id)
            );
        """)
        conn.commit()
        self._initialized = True

    async def extract_and_store(
        self,
        task: str,
        result: str,
        task_id: str,
        project_id: str | None = None,
    ) -> list[Assumption]:
        if not self._initialized:
            self.initialize()

        agent_result = await self._extractor.run(
            f"TASK:\n{task[:1000]}\n\nRESULT:\n{result[:2000]}\n\nExtract all assumptions."
        )
        if not agent_result.succeeded:
            return []

        assumptions = []
        try:
            content = agent_result.content
            start = content.find("[")
            end = content.rfind("]") + 1
            if start < 0:
                return []
            items = json.loads(content[start:end])
            conn = self._get_conn()
            for item in items:
                if not isinstance(item, dict) or not item.get("assumption"):
                    continue
                assumption = Assumption(
                    id=str(uuid.uuid4()),
                    task_id=task_id,
                    content=item["assumption"],
                    domain=item.get("domain", "general"),
                    invalidation_trigger=item.get("invalidation_trigger", ""),
                    impact_if_wrong=item.get("impact_if_wrong", "MEDIUM"),
                    confidence=float(item.get("confidence", 0.7)),
                    created_at=datetime.utcnow(),
                    project_id=project_id,
                )
                conn.execute(
                    """INSERT INTO assumptions
                       (id, task_id, content, domain, invalidation_trigger,
                        impact_if_wrong, confidence, created_at, status, project_id)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (assumption.id, assumption.task_id, assumption.content,
                     assumption.domain, assumption.invalidation_trigger,
                     assumption.impact_if_wrong, assumption.confidence,
                     assumption.created_at.isoformat(), assumption.status,
                     assumption.project_id),
                )
                conn.execute(
                    "INSERT OR IGNORE INTO assumption_task_links VALUES (?,?)",
                    (assumption.id, task_id),
                )
                assumptions.append(assumption)
            conn.commit()
        except (json.JSONDecodeError, ValueError):
            pass
        return assumptions

    async def check_new_fact(
        self, new_fact: str, project_id: str | None = None
    ) -> list[InvalidationAlert]:
        if not self._initialized:
            self.initialize()

        active = self._get_active_assumptions(project_id)
        if not active:
            return []

        # Check in batches of 20
        alerts = []
        for i in range(0, len(active), 20):
            batch = active[i:i+20]
            assumption_list = json.dumps([
                {"id": a.id, "assumption": a.content, "trigger": a.invalidation_trigger}
                for a in batch
            ])
            result = await self._checker.run(
                f"NEW FACT:\n{new_fact}\n\nASSUMPTIONS TO CHECK:\n{assumption_list}"
            )
            if not result.succeeded:
                continue
            try:
                content = result.content
                start = content.find("{")
                end = content.rfind("}") + 1
                if start < 0:
                    continue
                data = json.loads(content[start:end])
                for inv in data.get("invalidated", []):
                    assumption = next(
                        (a for a in batch if a.id == inv.get("assumption_id")), None
                    )
                    if assumption:
                        self._mark_invalidated(assumption.id, new_fact)
                        alerts.append(InvalidationAlert(
                            assumption=assumption,
                            new_fact=new_fact,
                            reason=inv.get("reason", ""),
                            severity=inv.get("severity", "PARTIAL"),
                            decisions_at_risk=self._get_linked_tasks(assumption.id),
                        ))
            except (json.JSONDecodeError, ValueError):
                pass
        return alerts

    def get_active_assumptions(
        self, project_id: str | None = None, domain: str | None = None
    ) -> list[Assumption]:
        if not self._initialized:
            self.initialize()
        return self._get_active_assumptions(project_id, domain)

    def _get_active_assumptions(
        self, project_id: str | None = None, domain: str | None = None
    ) -> list[Assumption]:
        conn = self._get_conn()
        query = "SELECT * FROM assumptions WHERE status = 'active'"
        params: list = []
        if project_id:
            query += " AND project_id = ?"
            params.append(project_id)
        if domain:
            query += " AND domain = ?"
            params.append(domain)
        query += " ORDER BY impact_if_wrong DESC, confidence ASC LIMIT 100"
        rows = conn.execute(query, params).fetchall()
        return [self._row_to_assumption(r) for r in rows]

    def _mark_invalidated(self, assumption_id: str, invalidated_by: str) -> None:
        conn = self._get_conn()
        conn.execute(
            """UPDATE assumptions SET status = 'invalidated',
               invalidated_by = ?, invalidated_at = ? WHERE id = ?""",
            (invalidated_by[:500], datetime.utcnow().isoformat(), assumption_id),
        )
        conn.commit()

    def _get_linked_tasks(self, assumption_id: str) -> list[str]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT task_id FROM assumption_task_links WHERE assumption_id = ?",
            (assumption_id,),
        ).fetchall()
        return [r["task_id"] for r in rows]

    def format_alert_summary(self, alerts: list[InvalidationAlert]) -> str:
        if not alerts:
            return ""
        lines = [f"\n⚠️  ASSUMPTION ALERT: {len(alerts)} past assumption(s) invalidated\n"]
        for alert in alerts:
            lines.append(
                f"  [{alert.severity}] \"{alert.assumption.content[:100]}\"\n"
                f"  → {alert.reason}\n"
                f"  → Impact if wrong: {alert.assumption.impact_if_wrong}\n"
                f"  → {len(alert.decisions_at_risk)} past decision(s) may need review\n"
            )
        return "\n".join(lines)

    def _row_to_assumption(self, row: sqlite3.Row) -> Assumption:
        return Assumption(
            id=row["id"],
            task_id=row["task_id"],
            content=row["content"],
            domain=row["domain"],
            invalidation_trigger=row["invalidation_trigger"] or "",
            impact_if_wrong=row["impact_if_wrong"],
            confidence=row["confidence"],
            created_at=datetime.fromisoformat(row["created_at"]),
            status=row["status"],
            project_id=row["project_id"],
            invalidated_by=row["invalidated_by"],
            invalidated_at=(
                datetime.fromisoformat(row["invalidated_at"])
                if row["invalidated_at"] else None
            ),
        )


class _AssumptionExtractorAgent(BaseAgent):
    name = "assumption_extractor"

    def __init__(self):
        super().__init__()
        self._system_prompt = ASSUMPTION_EXTRACTOR_PROMPT
        self.model = config.fast_model


class _InvalidationCheckerAgent(BaseAgent):
    name = "invalidation_checker"

    def __init__(self):
        super().__init__()
        self._system_prompt = INVALIDATION_CHECKER_PROMPT
        self.model = config.fast_model


assumption_tracker = AssumptionTracker()
