"""
Recursive Self-Architecture Engine

After every task, AIOS analyzes its own performance and rewrites agent
system prompts to be better. The more it's used, the smarter it gets.

This is not metaphorical. The prompts are literally rewritten in the database.
Each agent's behavior improves based on measured outcomes.
"""

import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from ..config import config
from ..agents.base import BaseAgent
from ..system_prompt import MASTER_SYSTEM_PROMPT, AGENT_SYSTEM_PROMPTS


META_ANALYST_PROMPT = f"""
{MASTER_SYSTEM_PROMPT}

## YOUR ROLE: Meta-Performance Analyst

You analyze AI agent performance data to identify systematic weaknesses.
Your job: find patterns in where agents underperform and prescribe specific improvements.

You are not vague. "Be more thorough" is useless. You produce specific,
implementable changes to agent behavior.

Given performance data across tasks, identify:
1. Which agent consistently produces the lowest quality output?
2. What specific type of task does each agent fail at?
3. What instructions are missing from agent prompts that would fix this?
4. What new heuristics should be added based on observed patterns?

Output as JSON:
{{
  "performance_insights": [
    {{
      "agent": "researcher",
      "weakness": "Fails to acknowledge conflicting evidence when sources disagree",
      "evidence": "3 of last 5 research tasks produced one-sided analysis",
      "fix": "Add explicit instruction: Always present the strongest counterargument before concluding",
      "priority": "HIGH"
    }}
  ],
  "new_heuristics": [
    {{
      "domain": "research",
      "heuristic": "When 2+ sources conflict, spend at least 20% of the response on the conflict itself"
    }}
  ],
  "prompt_additions": [
    {{
      "agent": "researcher",
      "addition": "CRITICAL INSTRUCTION: Before stating any conclusion, explicitly state the strongest evidence against it."
    }}
  ]
}}
"""

PROMPT_REWRITER_PROMPT = f"""
{MASTER_SYSTEM_PROMPT}

## YOUR ROLE: Prompt Architect

You rewrite agent system prompts to make agents more effective.
Given: an existing prompt + specific improvements to make.
Produce: an improved prompt that incorporates the improvements seamlessly.

Rules:
- Preserve everything that was working
- Add improvements in the most impactful location in the prompt
- Do not make the prompt longer than necessary
- Be specific — improvements must change behavior, not just add words
- Test your additions mentally: will this actually change what the agent does?
"""


@dataclass
class PerformanceRecord:
    task_id: str
    agent_name: str
    task_type: str
    quality_score: float        # 0–100 from critic
    confidence: float
    tokens_used: int
    duration_ms: float
    issues_found: list[str]
    succeeded: bool
    recorded_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class PromptImprovement:
    agent_name: str
    weakness_identified: str
    fix_description: str
    priority: str               # HIGH | MEDIUM | LOW
    applied: bool = False
    applied_at: datetime | None = None


@dataclass
class ArchitectureUpdate:
    improvements_analyzed: int
    agents_updated: list[str]
    new_heuristics_added: int
    prompt_additions: list[dict]
    performance_delta: float    # estimated improvement
    update_notes: str


class SelfArchitectEngine:
    """
    The engine that makes AIOS smarter after every use.

    Process:
    1. Record performance metrics after every task
    2. Periodically analyze patterns in performance data
    3. Generate specific prompt improvements
    4. Rewrite agent prompts with improvements
    5. Store the version history (can roll back if worse)
    """

    MIN_TASKS_BEFORE_IMPROVEMENT = 5  # don't update on too little data

    def __init__(self):
        self._conn: sqlite3.Connection | None = None
        self._meta_analyst = _MetaAnalystAgent()
        self._prompt_rewriter = _PromptRewriterAgent()
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
            CREATE TABLE IF NOT EXISTS performance_records (
                id TEXT PRIMARY KEY,
                task_id TEXT,
                agent_name TEXT NOT NULL,
                task_type TEXT,
                quality_score REAL DEFAULT 0.0,
                confidence REAL DEFAULT 0.5,
                tokens_used INTEGER DEFAULT 0,
                duration_ms REAL DEFAULT 0.0,
                issues_found TEXT DEFAULT '[]',
                succeeded INTEGER DEFAULT 1,
                recorded_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS agent_prompts (
                id TEXT PRIMARY KEY,
                agent_name TEXT NOT NULL,
                prompt_text TEXT NOT NULL,
                version INTEGER DEFAULT 1,
                performance_score REAL DEFAULT 0.0,
                created_at TEXT NOT NULL,
                is_active INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS prompt_improvements (
                id TEXT PRIMARY KEY,
                agent_name TEXT NOT NULL,
                weakness TEXT NOT NULL,
                fix_description TEXT NOT NULL,
                priority TEXT DEFAULT 'MEDIUM',
                applied INTEGER DEFAULT 0,
                applied_at TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS architecture_updates (
                id TEXT PRIMARY KEY,
                improvements_analyzed INTEGER DEFAULT 0,
                agents_updated TEXT DEFAULT '[]',
                new_heuristics INTEGER DEFAULT 0,
                update_notes TEXT,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_pr_agent ON performance_records(agent_name);
            CREATE INDEX IF NOT EXISTS idx_pr_score ON performance_records(quality_score);
            CREATE INDEX IF NOT EXISTS idx_ap_agent ON agent_prompts(agent_name, is_active);
        """)
        # Load base prompts if not already stored
        self._seed_base_prompts()
        conn.commit()
        self._initialized = True

    def _seed_base_prompts(self) -> None:
        conn = self._get_conn()
        existing = conn.execute("SELECT COUNT(*) FROM agent_prompts").fetchone()[0]
        if existing > 0:
            return
        now = datetime.utcnow().isoformat()
        for agent_name, prompt in AGENT_SYSTEM_PROMPTS.items():
            conn.execute(
                """INSERT INTO agent_prompts
                   (id, agent_name, prompt_text, version, performance_score, created_at, is_active)
                   VALUES (?,?,?,?,?,?,?)""",
                (str(uuid.uuid4()), agent_name, prompt, 1, 50.0, now, 1),
            )

    def record_performance(
        self,
        task_id: str,
        agent_name: str,
        quality_score: float,
        confidence: float,
        tokens_used: int,
        duration_ms: float,
        issues_found: list[str] | None = None,
        succeeded: bool = True,
        task_type: str = "general",
    ) -> None:
        if not self._initialized:
            self.initialize()
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO performance_records
               (id, task_id, agent_name, task_type, quality_score, confidence,
                tokens_used, duration_ms, issues_found, succeeded, recorded_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                str(uuid.uuid4()), task_id, agent_name, task_type,
                quality_score, confidence, tokens_used, duration_ms,
                json.dumps(issues_found or []), int(succeeded),
                datetime.utcnow().isoformat(),
            ),
        )
        conn.commit()

    async def analyze_and_improve(self) -> ArchitectureUpdate | None:
        if not self._initialized:
            self.initialize()

        conn = self._get_conn()
        total_records = conn.execute("SELECT COUNT(*) FROM performance_records").fetchone()[0]
        if total_records < self.MIN_TASKS_BEFORE_IMPROVEMENT:
            return None

        # Aggregate performance by agent
        rows = conn.execute(
            """SELECT agent_name,
               AVG(quality_score) as avg_score,
               MIN(quality_score) as min_score,
               COUNT(*) as task_count,
               SUM(CASE WHEN succeeded = 0 THEN 1 ELSE 0 END) as failure_count
               FROM performance_records
               GROUP BY agent_name
               ORDER BY avg_score ASC"""
        ).fetchall()

        perf_summary = "Agent Performance Summary:\n"
        for row in rows:
            perf_summary += (
                f"- {row['agent_name']}: avg={row['avg_score']:.1f}/100, "
                f"min={row['min_score']:.1f}, tasks={row['task_count']}, "
                f"failures={row['failure_count']}\n"
            )

        # Get recent issues
        issue_rows = conn.execute(
            "SELECT agent_name, issues_found FROM performance_records WHERE quality_score < 60 ORDER BY recorded_at DESC LIMIT 20"
        ).fetchall()
        issues_text = "Recent Quality Issues:\n"
        for row in issue_rows:
            issues = json.loads(row["issues_found"] or "[]")
            if issues:
                issues_text += f"- {row['agent_name']}: {'; '.join(issues[:2])}\n"

        # Meta-analysis
        analysis_result = await self._meta_analyst.run(
            f"{perf_summary}\n\n{issues_text}\n\nAnalyze and prescribe improvements."
        )
        if not analysis_result.succeeded:
            return None

        improvements = self._parse_improvements(analysis_result.content)
        agents_updated = []

        # Apply improvements to prompts
        for imp in improvements:
            if imp.priority == "HIGH":
                updated = await self._apply_improvement(imp)
                if updated:
                    agents_updated.append(imp.agent_name)
                    self._record_improvement(imp)

        now = datetime.utcnow().isoformat()
        update = ArchitectureUpdate(
            improvements_analyzed=len(improvements),
            agents_updated=agents_updated,
            new_heuristics_added=0,
            prompt_additions=[],
            performance_delta=0.05 * len(agents_updated),
            update_notes=f"Auto-improved {len(agents_updated)} agents based on {total_records} task records",
        )
        conn.execute(
            """INSERT INTO architecture_updates
               (id, improvements_analyzed, agents_updated, new_heuristics, update_notes, created_at)
               VALUES (?,?,?,?,?,?)""",
            (str(uuid.uuid4()), len(improvements), json.dumps(agents_updated), 0, update.update_notes, now),
        )
        conn.commit()
        return update

    async def _apply_improvement(self, improvement: PromptImprovement) -> bool:
        conn = self._get_conn()
        current = conn.execute(
            "SELECT * FROM agent_prompts WHERE agent_name = ? AND is_active = 1",
            (improvement.agent_name,),
        ).fetchone()
        if not current:
            return False

        result = await self._prompt_rewriter.run(
            f"CURRENT PROMPT:\n{current['prompt_text'][:3000]}\n\n"
            f"IMPROVEMENT TO APPLY:\n"
            f"Weakness: {improvement.weakness_identified}\n"
            f"Fix: {improvement.fix_description}\n\n"
            f"Rewrite the prompt with this improvement integrated."
        )
        if not result.succeeded or len(result.content) < 200:
            return False

        now = datetime.utcnow().isoformat()
        # Deactivate old version
        conn.execute(
            "UPDATE agent_prompts SET is_active = 0 WHERE agent_name = ? AND is_active = 1",
            (improvement.agent_name,),
        )
        # Insert new version
        new_version = (current["version"] or 1) + 1
        conn.execute(
            """INSERT INTO agent_prompts
               (id, agent_name, prompt_text, version, performance_score, created_at, is_active)
               VALUES (?,?,?,?,?,?,?)""",
            (str(uuid.uuid4()), improvement.agent_name, result.content, new_version, 50.0, now, 1),
        )
        conn.commit()
        return True

    def get_current_prompt(self, agent_name: str) -> str | None:
        if not self._initialized:
            self.initialize()
        conn = self._get_conn()
        row = conn.execute(
            "SELECT prompt_text FROM agent_prompts WHERE agent_name = ? AND is_active = 1",
            (agent_name,),
        ).fetchone()
        return row["prompt_text"] if row else None

    def get_improvement_history(self) -> list[dict]:
        if not self._initialized:
            self.initialize()
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM architecture_updates ORDER BY created_at DESC LIMIT 10"
        ).fetchall()
        return [dict(r) for r in rows]

    def _parse_improvements(self, analysis: str) -> list[PromptImprovement]:
        improvements = []
        try:
            start = analysis.find("{")
            end = analysis.rfind("}") + 1
            if start < 0:
                return []
            data = json.loads(analysis[start:end])
            for item in data.get("performance_insights", []):
                improvements.append(PromptImprovement(
                    agent_name=item.get("agent", ""),
                    weakness_identified=item.get("weakness", ""),
                    fix_description=item.get("fix", ""),
                    priority=item.get("priority", "MEDIUM"),
                ))
        except (json.JSONDecodeError, ValueError):
            pass
        return improvements

    def _record_improvement(self, imp: PromptImprovement) -> None:
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO prompt_improvements
               (id, agent_name, weakness, fix_description, priority, applied, applied_at, created_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                str(uuid.uuid4()), imp.agent_name, imp.weakness_identified,
                imp.fix_description, imp.priority, 1,
                datetime.utcnow().isoformat(), datetime.utcnow().isoformat(),
            ),
        )
        conn.commit()


class _MetaAnalystAgent(BaseAgent):
    name = "meta_analyst"

    def __init__(self):
        super().__init__()
        self._system_prompt = META_ANALYST_PROMPT
        self.model = config.ceo_model


class _PromptRewriterAgent(BaseAgent):
    name = "prompt_rewriter"

    def __init__(self):
        super().__init__()
        self._system_prompt = PROMPT_REWRITER_PROMPT
        self.model = config.ceo_model


self_architect = SelfArchitectEngine()
