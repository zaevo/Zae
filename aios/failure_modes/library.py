"""
Failure Mode Library

A living database of how things go wrong, built from every difficult task.
Every new plan is stress-tested against the entire library before delivery.

"Those who cannot remember the past are condemned to repeat it." — Santayana
"""

import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from ..config import config
from ..agents.base import BaseAgent
from ..system_prompt import MASTER_SYSTEM_PROMPT


FAILURE_EXTRACTOR_PROMPT = f"""
{MASTER_SYSTEM_PROMPT}

## YOUR ROLE: Failure Mode Extractor

You analyze tasks where things went wrong or could have gone wrong.
Your job: extract reusable failure modes that can warn future plans.

A failure mode is a specific, recurring pattern of how plans fail.
NOT "the plan was bad" but "plans that assume X without verifying Y always fail because Z."

Output as JSON array:
[
  {{
    "title": "Underestimating stakeholder resistance to change",
    "category": "people",
    "pattern": "Plans that assume adoption will happen naturally without explicit change management",
    "trigger_conditions": ["involves process change", "multiple stakeholders", "no change budget"],
    "how_it_fails": "People revert to old behavior within 30 days because incentives weren't aligned",
    "prevention": "Explicit change management plan, incentive alignment review, 90-day adoption tracking",
    "severity": "HIGH",
    "frequency": "COMMON"
  }}
]

Categories: technical, people, market, financial, timeline, process, communication, assumptions
Severity: CRITICAL | HIGH | MEDIUM | LOW
Frequency: VERY_COMMON | COMMON | OCCASIONAL | RARE
"""

STRESS_TEST_PROMPT = f"""
{MASTER_SYSTEM_PROMPT}

## YOUR ROLE: Plan Stress-Tester

You receive a plan/answer AND a library of known failure modes.
Your job: identify which failure modes this plan is vulnerable to.

For each matching failure mode, assess:
- How likely is this failure mode to activate for this specific plan?
- What in the plan triggers it?
- How would you modify the plan to prevent it?

Output as JSON:
{{
  "vulnerabilities": [
    {{
      "failure_mode_id": "...",
      "title": "...",
      "likelihood": "HIGH | MEDIUM | LOW",
      "trigger_in_plan": "Specific part of the plan that activates this failure mode",
      "prevention": "Specific modification to prevent this"
    }}
  ],
  "overall_risk": "HIGH | MEDIUM | LOW",
  "plan_hardened": "The plan with all vulnerabilities addressed"
}}
"""


@dataclass
class FailureMode:
    id: str
    title: str
    category: str
    pattern: str
    trigger_conditions: list[str]
    how_it_fails: str
    prevention: str
    severity: str
    frequency: str
    occurrence_count: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_matched: datetime | None = None


@dataclass
class PlanVulnerability:
    failure_mode: FailureMode
    likelihood: str
    trigger_in_plan: str
    prevention: str


@dataclass
class StressTestResult:
    original_plan: str
    vulnerabilities: list[PlanVulnerability]
    overall_risk: str
    hardened_plan: str
    failure_modes_checked: int


class FailureModeLibrary:
    """
    Learns from every failure. Protects every future plan.
    """

    def __init__(self):
        self._conn: sqlite3.Connection | None = None
        self._extractor = _FailureExtractorAgent()
        self._stress_tester = _StressTesterAgent()
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
            CREATE TABLE IF NOT EXISTS failure_modes (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                category TEXT DEFAULT 'general',
                pattern TEXT NOT NULL,
                trigger_conditions TEXT DEFAULT '[]',
                how_it_fails TEXT NOT NULL,
                prevention TEXT NOT NULL,
                severity TEXT DEFAULT 'MEDIUM',
                frequency TEXT DEFAULT 'OCCASIONAL',
                occurrence_count INTEGER DEFAULT 1,
                created_at TEXT NOT NULL,
                last_matched TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_fm_category ON failure_modes(category);
            CREATE INDEX IF NOT EXISTS idx_fm_severity ON failure_modes(severity);
        """)
        conn.commit()
        self._seed_library()
        self._initialized = True

    def _seed_library(self) -> None:
        """Pre-load universal failure modes that apply to almost every plan."""
        conn = self._get_conn()
        existing = conn.execute("SELECT COUNT(*) FROM failure_modes").fetchone()[0]
        if existing > 0:
            return

        seed_modes = [
            {
                "title": "Optimism bias in time estimation",
                "category": "timeline",
                "pattern": "Plans assume best-case scenario timelines without contingency",
                "trigger_conditions": ["timeline mentioned", "deadline", "launch date"],
                "how_it_fails": "Everything takes 2-3x longer than planned. First delay causes cascade.",
                "prevention": "Multiply estimates by 1.5x for known tasks, 2x for novel tasks. Add explicit buffer.",
                "severity": "HIGH",
                "frequency": "VERY_COMMON",
            },
            {
                "title": "Assumption of rational actors",
                "category": "people",
                "pattern": "Plans assume people will act in their own best interest as you define it",
                "trigger_conditions": ["user adoption", "behavior change", "incentive"],
                "how_it_fails": "People don't change behavior even when the new way is objectively better.",
                "prevention": "Map actual incentives. Design for current behavior, not desired behavior.",
                "severity": "HIGH",
                "frequency": "VERY_COMMON",
            },
            {
                "title": "Integration complexity underestimation",
                "category": "technical",
                "pattern": "Technical plans underestimate the difficulty of connecting existing systems",
                "trigger_conditions": ["integration", "API", "connect", "sync", "migrate"],
                "how_it_fails": "APIs change, data formats differ, auth systems conflict, rate limits hit.",
                "prevention": "Spike integrations first. Add 3x time for any integration work.",
                "severity": "HIGH",
                "frequency": "VERY_COMMON",
            },
            {
                "title": "Scope creep without resource adjustment",
                "category": "process",
                "pattern": "Scope expands during execution without corresponding resource or timeline adjustment",
                "trigger_conditions": ["feature", "add", "also", "while we're at it"],
                "how_it_fails": "Team overloads, quality drops, deadline missed, morale drops.",
                "prevention": "Every scope addition requires explicit trade-off decision. Remove something or add resources.",
                "severity": "HIGH",
                "frequency": "VERY_COMMON",
            },
            {
                "title": "Single point of failure — key person dependency",
                "category": "people",
                "pattern": "Plan depends critically on one person's availability, knowledge, or approval",
                "trigger_conditions": ["depends on", "waiting for", "approval", "key person"],
                "how_it_fails": "Person leaves, gets sick, or is reassigned. Knowledge is lost. Progress stops.",
                "prevention": "Document everything. Cross-train. Identify backup decision-makers.",
                "severity": "CRITICAL",
                "frequency": "COMMON",
            },
            {
                "title": "Feedback loop too long",
                "category": "process",
                "pattern": "Plans have long cycles between action and feedback on whether it's working",
                "trigger_conditions": ["launch", "ship", "deploy", "release"],
                "how_it_fails": "Wrong direction pursued for weeks before anyone knows. Cost of correction is high.",
                "prevention": "Build in check-in points every 2 weeks max. Define leading indicators of success.",
                "severity": "MEDIUM",
                "frequency": "COMMON",
            },
            {
                "title": "Market assumption without validation",
                "category": "market",
                "pattern": "Business plans assume customer demand without direct evidence",
                "trigger_conditions": ["customers will", "market wants", "people need", "demand for"],
                "how_it_fails": "Built something nobody wants. Spent resources on wrong problem.",
                "prevention": "Talk to 10 real potential customers before building. Pre-sell before building.",
                "severity": "CRITICAL",
                "frequency": "COMMON",
            },
            {
                "title": "Cash flow miscalculation",
                "category": "financial",
                "pattern": "Financial plans show profitability but ignore timing of cash flows",
                "trigger_conditions": ["revenue", "profit", "margins", "unit economics"],
                "how_it_fails": "Profitable on paper but cash runs out before revenue arrives.",
                "prevention": "Model monthly cash flow, not just annual P&L. Calculate burn rate and runway.",
                "severity": "CRITICAL",
                "frequency": "COMMON",
            },
        ]

        now = datetime.utcnow().isoformat()
        for mode in seed_modes:
            conn.execute(
                """INSERT INTO failure_modes
                   (id, title, category, pattern, trigger_conditions, how_it_fails,
                    prevention, severity, frequency, occurrence_count, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    str(uuid.uuid4()), mode["title"], mode["category"],
                    mode["pattern"], json.dumps(mode["trigger_conditions"]),
                    mode["how_it_fails"], mode["prevention"],
                    mode["severity"], mode["frequency"], 1, now,
                ),
            )
        conn.commit()

    async def extract_from_experience(
        self, task: str, what_went_wrong: str
    ) -> list[FailureMode]:
        result = await self._extractor.run(
            f"TASK:\n{task[:500]}\n\nWHAT WENT WRONG:\n{what_went_wrong[:1000]}\n\n"
            f"Extract reusable failure modes."
        )
        if not result.succeeded:
            return []

        modes = []
        try:
            content = result.content
            start, end = content.find("["), content.rfind("]") + 1
            if start < 0:
                return []
            items = json.loads(content[start:end])
            conn = self._get_conn()
            for item in items:
                mode = FailureMode(
                    id=str(uuid.uuid4()),
                    title=item.get("title", ""),
                    category=item.get("category", "general"),
                    pattern=item.get("pattern", ""),
                    trigger_conditions=item.get("trigger_conditions", []),
                    how_it_fails=item.get("how_it_fails", ""),
                    prevention=item.get("prevention", ""),
                    severity=item.get("severity", "MEDIUM"),
                    frequency=item.get("frequency", "OCCASIONAL"),
                )
                conn.execute(
                    """INSERT INTO failure_modes
                       (id, title, category, pattern, trigger_conditions, how_it_fails,
                        prevention, severity, frequency, occurrence_count, created_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        mode.id, mode.title, mode.category, mode.pattern,
                        json.dumps(mode.trigger_conditions), mode.how_it_fails,
                        mode.prevention, mode.severity, mode.frequency,
                        1, datetime.utcnow().isoformat(),
                    ),
                )
                modes.append(mode)
            conn.commit()
        except (json.JSONDecodeError, ValueError):
            pass
        return modes

    async def stress_test(self, plan: str) -> StressTestResult:
        if not self._initialized:
            self.initialize()

        library = self._get_relevant_modes(plan)
        if not library:
            return StressTestResult(
                original_plan=plan,
                vulnerabilities=[],
                overall_risk="LOW",
                hardened_plan=plan,
                failure_modes_checked=0,
            )

        library_json = json.dumps([
            {
                "id": m.id,
                "title": m.title,
                "pattern": m.pattern,
                "trigger_conditions": m.trigger_conditions,
                "how_it_fails": m.how_it_fails,
                "prevention": m.prevention,
                "severity": m.severity,
            }
            for m in library[:15]  # top 15 most relevant
        ])

        result = await self._stress_tester.run(
            f"PLAN TO STRESS-TEST:\n{plan[:3000]}\n\n"
            f"FAILURE MODE LIBRARY:\n{library_json}\n\n"
            f"Identify vulnerabilities and produce hardened plan."
        )

        if not result.succeeded:
            return StressTestResult(
                original_plan=plan,
                vulnerabilities=[],
                overall_risk="UNKNOWN",
                hardened_plan=plan,
                failure_modes_checked=len(library),
            )

        try:
            content = result.content
            start, end = content.find("{"), content.rfind("}") + 1
            if start >= 0:
                data = json.loads(content[start:end])
                vulns = []
                for v in data.get("vulnerabilities", []):
                    mode = next((m for m in library if m.id == v.get("failure_mode_id")), None)
                    if mode:
                        vulns.append(PlanVulnerability(
                            failure_mode=mode,
                            likelihood=v.get("likelihood", "MEDIUM"),
                            trigger_in_plan=v.get("trigger_in_plan", ""),
                            prevention=v.get("prevention", mode.prevention),
                        ))
                        self._increment_match(mode.id)

                return StressTestResult(
                    original_plan=plan,
                    vulnerabilities=vulns,
                    overall_risk=data.get("overall_risk", "MEDIUM"),
                    hardened_plan=data.get("plan_hardened", plan),
                    failure_modes_checked=len(library),
                )
        except (json.JSONDecodeError, ValueError):
            pass

        return StressTestResult(
            original_plan=plan,
            vulnerabilities=[],
            overall_risk="UNKNOWN",
            hardened_plan=result.content,
            failure_modes_checked=len(library),
        )

    def _get_relevant_modes(self, plan: str) -> list[FailureMode]:
        if not self._initialized:
            self.initialize()
        conn = self._get_conn()
        rows = conn.execute(
            """SELECT * FROM failure_modes
               ORDER BY CASE severity
                 WHEN 'CRITICAL' THEN 0 WHEN 'HIGH' THEN 1
                 WHEN 'MEDIUM' THEN 2 ELSE 3 END,
               occurrence_count DESC LIMIT 30"""
        ).fetchall()
        return [self._row_to_mode(r) for r in rows]

    def _increment_match(self, mode_id: str) -> None:
        conn = self._get_conn()
        conn.execute(
            "UPDATE failure_modes SET occurrence_count = occurrence_count + 1, last_matched = ? WHERE id = ?",
            (datetime.utcnow().isoformat(), mode_id),
        )
        conn.commit()

    def _row_to_mode(self, row: sqlite3.Row) -> FailureMode:
        return FailureMode(
            id=row["id"], title=row["title"], category=row["category"],
            pattern=row["pattern"],
            trigger_conditions=json.loads(row["trigger_conditions"] or "[]"),
            how_it_fails=row["how_it_fails"], prevention=row["prevention"],
            severity=row["severity"], frequency=row["frequency"],
            occurrence_count=row["occurrence_count"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def format_stress_test_report(self, result: StressTestResult) -> str:
        if not result.vulnerabilities:
            return f"✓ Plan stress-tested against {result.failure_modes_checked} failure modes. No critical vulnerabilities found."

        lines = [
            f"\n🔥 FAILURE MODE ANALYSIS ({result.failure_modes_checked} modes checked)",
            f"Overall Risk: {result.overall_risk}",
            f"Vulnerabilities Found: {len(result.vulnerabilities)}\n",
        ]
        for v in sorted(result.vulnerabilities, key=lambda x: {"HIGH": 0, "MEDIUM": 1, "LOW": 2}.get(x.likelihood, 3)):
            lines.append(
                f"  [{v.likelihood}] {v.failure_mode.title}\n"
                f"  Pattern: {v.failure_mode.pattern[:100]}\n"
                f"  Triggered by: {v.trigger_in_plan[:100]}\n"
                f"  Prevention: {v.prevention[:150]}\n"
            )
        return "\n".join(lines)


class _FailureExtractorAgent(BaseAgent):
    name = "failure_extractor"

    def __init__(self):
        super().__init__()
        self._system_prompt = FAILURE_EXTRACTOR_PROMPT
        self.model = config.fast_model


class _StressTesterAgent(BaseAgent):
    name = "stress_tester"

    def __init__(self):
        super().__init__()
        self._system_prompt = STRESS_TEST_PROMPT
        self.model = config.worker_model


failure_library = FailureModeLibrary()
