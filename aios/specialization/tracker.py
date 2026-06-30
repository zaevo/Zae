"""
Emergent Agent Specialization Tracker
Agents aren't just labeled by their default role.
They track their actual win/loss record per task category
and compete to handle tasks they're provably good at.
"""

import json
import sqlite3
import math
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from ..config import config

TASK_CLASSIFIER_PROMPT = """Classify this task into its primary category.

Task: {task}

Choose the MOST specific applicable category:
research | analysis | writing | coding | debugging | security | financial |
planning | brainstorming | explanation | data | creative | scientific | legal | other

Return JSON: {{"category": "research", "confidence": 0.9}}"""

ROUTING_ADVISOR_PROMPT = """You are routing a task to the best-specialized agent.

Task: {task}
Task Category: {category}

Agent Track Records (based on actual performance data):
{track_records}

Given their track records, rank these agents for this specific task.
Consider: win rate, average quality, number of tasks (more = more reliable estimate).

Return JSON:
{{
  "ranking": [
    {{"agent": "researcher", "score": 0.91, "reason": "why"}},
    {{"agent": "analyst", "score": 0.85, "reason": "why"}}
  ],
  "recommendation": "researcher",
  "confidence": 0.88
}}"""


@dataclass
class AgentSpecialization:
    agent_name: str
    category: str
    wins: int
    total: int
    avg_quality: float
    wilson_score: float  # lower bound of Wilson confidence interval
    last_task_at: str


@dataclass
class RoutingRecommendation:
    task: str
    category: str
    recommended_agent: str
    ranking: list[dict]
    confidence: float


class SpecializationTracker:
    """
    Tracks each agent's performance per task category.
    Uses Wilson confidence interval for reliable small-sample estimates.
    Routes future tasks to proven specialists.
    """

    def __init__(self):
        self._db_path = Path(config.db_path).parent / "specialization.db"

    def initialize(self) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS agent_performance (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_name TEXT NOT NULL,
                    task TEXT NOT NULL,
                    category TEXT NOT NULL,
                    quality_score REAL NOT NULL,
                    was_selected INTEGER DEFAULT 1,
                    recorded_at TEXT DEFAULT (datetime('now'))
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS agent_specializations (
                    agent_name TEXT NOT NULL,
                    category TEXT NOT NULL,
                    wins INTEGER DEFAULT 0,
                    total INTEGER DEFAULT 0,
                    sum_quality REAL DEFAULT 0,
                    last_task_at TEXT DEFAULT (datetime('now')),
                    PRIMARY KEY (agent_name, category)
                )
            """)

    def record_outcome(
        self,
        agent_name: str,
        task: str,
        category: str,
        quality_score: float,
        was_selected: bool = True,
    ) -> None:
        """Record an agent's performance on a task."""
        win = quality_score >= 70.0

        with sqlite3.connect(self._db_path) as conn:
            conn.execute("""
                INSERT INTO agent_performance
                (agent_name, task, category, quality_score, was_selected)
                VALUES (?,?,?,?,?)
            """, (agent_name, task[:300], category, quality_score, int(was_selected)))

            conn.execute("""
                INSERT INTO agent_specializations (agent_name, category, wins, total, sum_quality)
                VALUES (?,?,?,1,?)
                ON CONFLICT(agent_name, category) DO UPDATE SET
                    wins = wins + ?,
                    total = total + 1,
                    sum_quality = sum_quality + ?,
                    last_task_at = datetime('now')
            """, (agent_name, category, int(win), quality_score, int(win), quality_score))

    @staticmethod
    def _wilson_score(wins: int, total: int, z: float = 1.28) -> float:
        """Wilson score lower bound — conservative estimate of true win rate."""
        if total == 0:
            return 0.0
        p_hat = wins / total
        denominator = 1 + z**2 / total
        center = p_hat + z**2 / (2 * total)
        margin = z * math.sqrt(p_hat * (1 - p_hat) / total + z**2 / (4 * total**2))
        return max(0.0, (center - margin) / denominator)

    def get_specializations(
        self, category: str | None = None, min_tasks: int = 3
    ) -> list[AgentSpecialization]:
        """Get agent specializations, optionally filtered by category."""
        try:
            with sqlite3.connect(self._db_path) as conn:
                if category:
                    rows = conn.execute("""
                        SELECT agent_name, category, wins, total, sum_quality, last_task_at
                        FROM agent_specializations
                        WHERE category=? AND total >= ?
                        ORDER BY wins*1.0/total DESC
                    """, (category, min_tasks)).fetchall()
                else:
                    rows = conn.execute("""
                        SELECT agent_name, category, wins, total, sum_quality, last_task_at
                        FROM agent_specializations
                        WHERE total >= ?
                        ORDER BY category, wins*1.0/total DESC
                    """, (min_tasks,)).fetchall()

            return [AgentSpecialization(
                agent_name=r[0],
                category=r[1],
                wins=r[2],
                total=r[3],
                avg_quality=r[4] / r[3] if r[3] > 0 else 0,
                wilson_score=self._wilson_score(r[2], r[3]),
                last_task_at=r[5],
            ) for r in rows]
        except Exception:
            return []

    async def classify_task(self, task: str) -> str:
        """Classify a task into a category using AI."""
        import anthropic

        client = anthropic.Anthropic(api_key=config.api_key)
        try:
            response = client.messages.create(
                model=config.fast_model,
                max_tokens=100,
                messages=[{"role": "user", "content": TASK_CLASSIFIER_PROMPT.format(
                    task=task[:500]
                )}],
            )
            raw = response.content[0].text
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start >= 0 and end > start:
                parsed = json.loads(raw[start:end])
                return parsed.get("category", "other")
        except Exception:
            pass
        return "other"

    async def get_routing_recommendation(
        self, task: str, candidate_agents: list[str]
    ) -> RoutingRecommendation:
        """Recommend the best agent for a task based on track records."""
        import anthropic

        category = await self.classify_task(task)
        specs = self.get_specializations(category=category)

        # Build track record dict for candidates
        spec_by_agent = {s.agent_name: s for s in specs}
        track_records: list[dict] = []
        for agent in candidate_agents:
            if agent in spec_by_agent:
                s = spec_by_agent[agent]
                track_records.append({
                    "agent": agent,
                    "category": category,
                    "win_rate": f"{s.wins}/{s.total}",
                    "avg_quality": round(s.avg_quality, 1),
                    "wilson_score": round(s.wilson_score, 3),
                })
            else:
                track_records.append({
                    "agent": agent, "category": category,
                    "win_rate": "no data", "avg_quality": "unknown",
                    "wilson_score": 0.0,
                })

        # If we have enough data, use AI to recommend
        if len([r for r in track_records if r["win_rate"] != "no data"]) >= 2:
            client = anthropic.Anthropic(api_key=config.api_key)
            try:
                response = client.messages.create(
                    model=config.fast_model,
                    max_tokens=400,
                    messages=[{"role": "user", "content": ROUTING_ADVISOR_PROMPT.format(
                        task=task[:500],
                        category=category,
                        track_records=json.dumps(track_records, indent=2),
                    )}],
                )
                raw = response.content[0].text
                start = raw.find("{")
                end = raw.rfind("}") + 1
                if start >= 0 and end > start:
                    parsed = json.loads(raw[start:end])
                    return RoutingRecommendation(
                        task=task,
                        category=category,
                        recommended_agent=parsed.get("recommendation", candidate_agents[0]),
                        ranking=parsed.get("ranking", []),
                        confidence=float(parsed.get("confidence", 0.5)),
                    )
            except Exception:
                pass

        # Fallback: pick by wilson score
        ranked = sorted(track_records, key=lambda r: r.get("wilson_score", 0), reverse=True)
        return RoutingRecommendation(
            task=task,
            category=category,
            recommended_agent=ranked[0]["agent"] if ranked else candidate_agents[0],
            ranking=ranked,
            confidence=0.5,
        )

    def format_leaderboard(self) -> str:
        """Show top agents per category."""
        try:
            with sqlite3.connect(self._db_path) as conn:
                rows = conn.execute("""
                    SELECT agent_name, category, wins, total,
                           ROUND(sum_quality/total, 1) as avg_q
                    FROM agent_specializations
                    WHERE total >= 3
                    ORDER BY category, wins*1.0/total DESC
                """).fetchall()
        except Exception:
            return "No specialization data yet. Needs at least 3 tasks per agent/category."

        if not rows:
            return "No specialization data yet. Needs at least 3 tasks per agent/category."

        current_cat = None
        lines = ["\nAgent Specialization Leaderboard"]
        for agent, cat, wins, total, avg_q in rows:
            if cat != current_cat:
                current_cat = cat
                lines.append(f"\n  [{cat.upper()}]")
            win_rate = wins / total if total else 0
            bar = "█" * int(win_rate * 10) + "░" * (10 - int(win_rate * 10))
            lines.append(f"    {agent:<20} [{bar}] {win_rate:.0%} win ({total} tasks, avg q={avg_q})")

        return "\n".join(lines)


specialization_tracker = SpecializationTracker()
