"""
Cross-Session Pattern Mining

Finds patterns across ALL your past sessions that you never noticed yourself.
Surfaces insights about how you work, what you struggle with, and what you're optimizing wrong.
"""

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from ..config import config
from ..agents.base import BaseAgent
from ..system_prompt import MASTER_SYSTEM_PROMPT


PATTERN_MINER_PROMPT = f"""
{MASTER_SYSTEM_PROMPT}

## YOUR ROLE: Cross-Session Pattern Miner

You analyze a history of tasks and interactions to find non-obvious patterns.
You are looking for things the user would never notice on their own.

Focus on:

TEMPORAL PATTERNS
- Do certain task types cluster on certain days/times?
- Are there productivity patterns? (certain times = higher quality work)
- What tasks tend to get started but never finished?

COGNITIVE PATTERNS
- What topics does the user ask about repeatedly without resolution?
- What types of problems does the user consistently underestimate?
- Where does the user ask for help vs. try to figure out alone?

QUALITY PATTERNS
- What tasks produce the highest quality output?
- What conditions correlate with lower quality requests?
- Are there recurring mistakes across sessions?

PROGRESS PATTERNS
- What projects are making progress vs. stalled?
- What decisions keep getting revisited (indecision signals)?
- What tasks recur because the root problem wasn't solved?

OPPORTUNITY PATTERNS
- What has the user mentioned wanting to do but never followed through on?
- What adjacent capabilities would clearly help based on the work pattern?
- What could be automated based on repetition frequency?

Output as JSON:
{{
  "patterns": [
    {{
      "type": "temporal|cognitive|quality|progress|opportunity",
      "title": "You request timeline estimates on Monday but almost never on Friday",
      "evidence": "9 of 12 timeline requests in last 30 days were Monday-Wednesday",
      "implication": "Planning mode is early-week; execution mode is late-week",
      "recommendation": "Schedule strategic planning sessions for Monday/Tuesday explicitly",
      "confidence": 0.8
    }}
  ],
  "key_insight": "The single most valuable pattern found",
  "automatable_tasks": ["List tasks that recur frequently enough to automate"],
  "stalled_projects": ["Projects mentioned multiple times with no progress signals"]
}}
"""


@dataclass
class DiscoveredPattern:
    pattern_type: str               # temporal | cognitive | quality | progress | opportunity
    title: str
    evidence: str
    implication: str
    recommendation: str
    confidence: float
    discovered_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class PatternMiningResult:
    patterns: list[DiscoveredPattern]
    key_insight: str
    automatable_tasks: list[str]
    stalled_projects: list[str]
    sessions_analyzed: int
    tasks_analyzed: int
    date_range: str


class CrossSessionPatternMiner:
    """
    Mines patterns across all sessions to surface insights the user never sees.
    """

    def __init__(self):
        self._conn: sqlite3.Connection | None = None
        self._miner_agent = _PatternMinerAgent()
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
            CREATE TABLE IF NOT EXISTS task_log (
                id TEXT PRIMARY KEY,
                session_id TEXT,
                task_text TEXT NOT NULL,
                task_type TEXT,
                quality_score REAL,
                completed INTEGER DEFAULT 1,
                logged_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS discovered_patterns (
                id TEXT PRIMARY KEY,
                pattern_type TEXT,
                title TEXT NOT NULL,
                evidence TEXT,
                implication TEXT,
                recommendation TEXT,
                confidence REAL DEFAULT 0.5,
                discovered_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_tl_session ON task_log(session_id);
            CREATE INDEX IF NOT EXISTS idx_tl_logged ON task_log(logged_at);
        """)
        conn.commit()
        self._initialized = True

    def log_task(
        self,
        task: str,
        session_id: str,
        quality_score: float = 0.0,
        task_type: str = "general",
    ) -> None:
        if not self._initialized:
            self.initialize()
        conn = self._get_conn()
        import uuid
        conn.execute(
            "INSERT INTO task_log (id, session_id, task_text, task_type, quality_score, logged_at) VALUES (?,?,?,?,?,?)",
            (str(uuid.uuid4()), session_id, task[:500], task_type, quality_score,
             datetime.utcnow().isoformat()),
        )
        conn.commit()

    async def mine(self, lookback_days: int = 30) -> PatternMiningResult:
        if not self._initialized:
            self.initialize()

        conn = self._get_conn()
        cutoff = (datetime.utcnow() - timedelta(days=lookback_days)).isoformat()
        rows = conn.execute(
            "SELECT * FROM task_log WHERE logged_at > ? ORDER BY logged_at ASC",
            (cutoff,),
        ).fetchall()

        if len(rows) < 3:
            return PatternMiningResult(
                patterns=[], key_insight="Not enough data yet. Keep using AIOS.",
                automatable_tasks=[], stalled_projects=[],
                sessions_analyzed=0, tasks_analyzed=len(rows),
                date_range=f"Last {lookback_days} days",
            )

        # Build history text
        history = []
        sessions: set[str] = set()
        for r in rows:
            sessions.add(r["session_id"])
            logged_at = datetime.fromisoformat(r["logged_at"])
            history.append(
                f"[{logged_at.strftime('%a %Y-%m-%d %H:%M')}] "
                f"Type={r['task_type']} Quality={r['quality_score']:.0f}: "
                f"{r['task_text'][:100]}"
            )

        history_text = "\n".join(history)
        result = await self._miner_agent.run(
            f"TASK HISTORY ({len(rows)} tasks across {len(sessions)} sessions, last {lookback_days} days):\n\n"
            f"{history_text}\n\nMine for non-obvious patterns."
        )

        if not result.succeeded:
            return PatternMiningResult(
                patterns=[], key_insight="Pattern mining unavailable.",
                automatable_tasks=[], stalled_projects=[],
                sessions_analyzed=len(sessions), tasks_analyzed=len(rows),
                date_range=f"Last {lookback_days} days",
            )

        patterns, key_insight, automatable, stalled = self._parse_mining_result(result.content)

        # Store newly discovered patterns
        self._store_patterns(patterns)

        return PatternMiningResult(
            patterns=patterns,
            key_insight=key_insight,
            automatable_tasks=automatable,
            stalled_projects=stalled,
            sessions_analyzed=len(sessions),
            tasks_analyzed=len(rows),
            date_range=f"Last {lookback_days} days",
        )

    def get_previous_patterns(self) -> list[DiscoveredPattern]:
        if not self._initialized:
            self.initialize()
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM discovered_patterns ORDER BY confidence DESC LIMIT 20"
        ).fetchall()
        return [
            DiscoveredPattern(
                pattern_type=r["pattern_type"],
                title=r["title"],
                evidence=r["evidence"] or "",
                implication=r["implication"] or "",
                recommendation=r["recommendation"] or "",
                confidence=r["confidence"],
                discovered_at=datetime.fromisoformat(r["discovered_at"]),
            )
            for r in rows
        ]

    def _parse_mining_result(
        self, content: str
    ) -> tuple[list[DiscoveredPattern], str, list[str], list[str]]:
        patterns = []
        key_insight = ""
        automatable: list[str] = []
        stalled: list[str] = []
        try:
            start = content.find("{")
            end = content.rfind("}") + 1
            if start < 0:
                return patterns, content[:200], automatable, stalled
            data = json.loads(content[start:end])
            for p in data.get("patterns", []):
                patterns.append(DiscoveredPattern(
                    pattern_type=p.get("type", "cognitive"),
                    title=p.get("title", ""),
                    evidence=p.get("evidence", ""),
                    implication=p.get("implication", ""),
                    recommendation=p.get("recommendation", ""),
                    confidence=float(p.get("confidence", 0.5)),
                ))
            key_insight = data.get("key_insight", "")
            automatable = data.get("automatable_tasks", [])
            stalled = data.get("stalled_projects", [])
        except (json.JSONDecodeError, ValueError):
            key_insight = content[:300]
        return patterns, key_insight, automatable, stalled

    def _store_patterns(self, patterns: list[DiscoveredPattern]) -> None:
        import uuid
        conn = self._get_conn()
        now = datetime.utcnow().isoformat()
        for p in patterns:
            conn.execute(
                """INSERT OR IGNORE INTO discovered_patterns
                   (id, pattern_type, title, evidence, implication, recommendation, confidence, discovered_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (str(uuid.uuid4()), p.pattern_type, p.title, p.evidence,
                 p.implication, p.recommendation, p.confidence, now),
            )
        conn.commit()

    def format_insights(self, result: PatternMiningResult) -> str:
        if not result.patterns:
            return "No patterns detected yet. More interactions needed."
        lines = [
            f"\n## Pattern Intelligence ({result.tasks_analyzed} tasks analyzed)\n",
            f"**Key Insight:** {result.key_insight}\n",
        ]
        for p in sorted(result.patterns, key=lambda x: x.confidence, reverse=True)[:5]:
            lines.append(
                f"**[{p.pattern_type.upper()}]** {p.title}\n"
                f"  Evidence: {p.evidence[:100]}\n"
                f"  → {p.recommendation[:150]}\n"
            )
        if result.automatable_tasks:
            lines.append(f"**Automatable:** {', '.join(result.automatable_tasks[:3])}")
        if result.stalled_projects:
            lines.append(f"**Stalled:** {', '.join(result.stalled_projects[:3])}")
        return "\n".join(lines)


class _PatternMinerAgent(BaseAgent):
    name = "pattern_miner"

    def __init__(self):
        super().__init__()
        self._system_prompt = PATTERN_MINER_PROMPT
        self.model = config.worker_model


pattern_miner = CrossSessionPatternMiner()
