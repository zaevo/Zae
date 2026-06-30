"""
Goal Hierarchy Manager
Maintains a living tree of goals from 5-year strategic objectives
down to today's immediate tasks. Every task gets linked to a goal.
The AI reprioritizes automatically when goals conflict.
"""

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from enum import Enum

from ..config import config

GOAL_LINKER_PROMPT = """You are a Goal Linker. Given a task and a list of active goals,
determine which goal(s) this task most directly serves.

Task: {task}

Active Goals:
{goals}

Return JSON:
{{
  "primary_goal_id": 1,
  "supporting_goal_ids": [2, 3],
  "contribution": "How this task moves the primary goal forward",
  "goal_confidence": 0.85
}}

If no existing goal fits, return {{"primary_goal_id": null, "new_goal_suggestion": "suggested goal this task implies"}}"""

PRIORITIZER_PROMPT = """You are a Strategic Prioritizer. Review this goal tree and recommend reprioritization.

Current Goals:
{goals}

Recent Task History:
{recent_tasks}

Identify:
1. Goals that are being neglected (no tasks linked recently)
2. Goals that conflict with each other
3. Goals that have become irrelevant
4. Goals whose priority should be raised based on recent activity

Return JSON:
{{
  "priority_changes": [
    {{"goal_id": 1, "new_priority": 9.5, "reason": "why"}},
  ],
  "conflicts": [
    {{"goal_ids": [1, 2], "conflict_description": "what conflicts"}}
  ],
  "neglected_goals": [1, 3],
  "obsolete_goals": [],
  "insight": "overall strategic observation"
}}"""

PROGRESS_ASSESSOR_PROMPT = """Assess progress toward this goal based on linked tasks.

Goal: {goal_title}
Description: {goal_description}
Horizon: {horizon}

Tasks linked to this goal:
{linked_tasks}

Return JSON:
{{
  "completion_percentage": 0.35,
  "momentum": "accelerating|steady|stalling|blocked",
  "key_achievements": ["achievement 1"],
  "blockers": ["what's in the way"],
  "next_action": "most important next step",
  "on_track": true
}}"""


class GoalStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    PAUSED = "paused"
    ABANDONED = "abandoned"


class GoalHorizon(str, Enum):
    IMMEDIATE = "immediate"    # today / this week
    TACTICAL = "tactical"      # this month / quarter
    STRATEGIC = "strategic"    # this year
    VISIONARY = "visionary"    # 3-5 years


@dataclass
class Goal:
    goal_id: int
    title: str
    description: str
    horizon: str
    priority: float
    status: str
    parent_id: int | None
    project_id: str | None
    completion_pct: float
    created_at: str
    children: list["Goal"] = field(default_factory=list)


@dataclass
class GoalProgress:
    goal_id: int
    completion_percentage: float
    momentum: str
    key_achievements: list[str]
    blockers: list[str]
    next_action: str
    on_track: bool


class GoalHierarchyManager:
    """
    Living tree of goals from strategic (5yr) to immediate (today).
    Every task is linked to a goal. AI reprioritizes autonomously.
    """

    def __init__(self):
        self._db_path = Path(config.db_path).parent / "goals.db"

    def initialize(self) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS goals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    horizon TEXT DEFAULT 'tactical',
                    priority REAL DEFAULT 5.0,
                    status TEXT DEFAULT 'active',
                    parent_id INTEGER REFERENCES goals(id),
                    project_id TEXT,
                    completion_pct REAL DEFAULT 0.0,
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now'))
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS goal_tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    goal_id INTEGER REFERENCES goals(id),
                    task TEXT NOT NULL,
                    contribution TEXT DEFAULT '',
                    quality_score REAL DEFAULT 0.0,
                    linked_at TEXT DEFAULT (datetime('now'))
                )
            """)

    def add_goal(
        self,
        title: str,
        description: str = "",
        horizon: str = "tactical",
        priority: float = 5.0,
        parent_id: int | None = None,
        project_id: str | None = None,
    ) -> int:
        with sqlite3.connect(self._db_path) as conn:
            cursor = conn.execute("""
                INSERT INTO goals (title, description, horizon, priority, parent_id, project_id)
                VALUES (?,?,?,?,?,?)
            """, (title, description, horizon, priority, parent_id, project_id))
            return cursor.lastrowid

    def update_goal_status(self, goal_id: int, status: str, completion_pct: float | None = None) -> None:
        with sqlite3.connect(self._db_path) as conn:
            if completion_pct is not None:
                conn.execute(
                    "UPDATE goals SET status=?, completion_pct=?, updated_at=datetime('now') WHERE id=?",
                    (status, completion_pct, goal_id)
                )
            else:
                conn.execute(
                    "UPDATE goals SET status=?, updated_at=datetime('now') WHERE id=?",
                    (status, goal_id)
                )

    def link_task_to_goal(
        self, goal_id: int, task: str, contribution: str = "", quality_score: float = 0.0
    ) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("""
                INSERT INTO goal_tasks (goal_id, task, contribution, quality_score)
                VALUES (?,?,?,?)
            """, (goal_id, task[:400], contribution[:300], quality_score))

    async def auto_link_task(
        self, task: str, quality_score: float = 0.0, project_id: str | None = None
    ) -> int | None:
        """Automatically link a task to the most relevant active goal."""
        import anthropic

        goals = self.get_active_goals(project_id=project_id)
        if not goals:
            return None

        goals_str = json.dumps([{
            "id": g.goal_id, "title": g.title,
            "horizon": g.horizon, "priority": g.priority
        } for g in goals], indent=2)

        client = anthropic.Anthropic(api_key=config.anthropic_api_key)
        try:
            response = client.messages.create(
                model=config.fast_model,
                max_tokens=400,
                messages=[{"role": "user", "content": GOAL_LINKER_PROMPT.format(
                    task=task[:800], goals=goals_str
                )}],
            )
            raw = response.content[0].text
            start = raw.find("{")
            end = raw.rfind("}") + 1
            parsed = json.loads(raw[start:end])

            goal_id = parsed.get("primary_goal_id")
            if goal_id:
                self.link_task_to_goal(
                    goal_id, task,
                    contribution=parsed.get("contribution", ""),
                    quality_score=quality_score,
                )
                return goal_id

            # Suggest creating a new goal
            suggestion = parsed.get("new_goal_suggestion")
            if suggestion:
                new_id = self.add_goal(
                    title=suggestion,
                    description=f"Auto-created from task: {task[:200]}",
                    horizon="tactical",
                    project_id=project_id,
                )
                self.link_task_to_goal(new_id, task, quality_score=quality_score)
                return new_id
        except Exception:
            pass
        return None

    async def reprioritize(self, project_id: str | None = None) -> dict:
        """Use AI to reprioritize the goal tree based on recent activity."""
        import anthropic

        goals = self.get_active_goals(project_id=project_id)
        if len(goals) < 2:
            return {}

        goals_str = json.dumps([{
            "id": g.goal_id, "title": g.title,
            "horizon": g.horizon, "priority": g.priority,
            "completion_pct": g.completion_pct,
        } for g in goals], indent=2)

        # Get recent linked tasks
        with sqlite3.connect(self._db_path) as conn:
            recent = conn.execute("""
                SELECT g.title, gt.task, gt.quality_score
                FROM goal_tasks gt
                JOIN goals g ON g.id=gt.goal_id
                ORDER BY gt.linked_at DESC LIMIT 20
            """).fetchall()

        recent_str = "\n".join(
            f"  [{title}] {task[:80]} (quality={q:.0f})"
            for title, task, q in recent
        ) or "No recent tasks."

        client = anthropic.Anthropic(api_key=config.anthropic_api_key)
        try:
            response = client.messages.create(
                model=config.worker_model,
                max_tokens=1200,
                messages=[{"role": "user", "content": PRIORITIZER_PROMPT.format(
                    goals=goals_str, recent_tasks=recent_str
                )}],
            )
            raw = response.content[0].text
            start = raw.find("{")
            end = raw.rfind("}") + 1
            parsed = json.loads(raw[start:end])

            # Apply priority changes
            with sqlite3.connect(self._db_path) as conn:
                for change in parsed.get("priority_changes", []):
                    conn.execute(
                        "UPDATE goals SET priority=?, updated_at=datetime('now') WHERE id=?",
                        (change["new_priority"], change["goal_id"])
                    )
            return parsed
        except Exception:
            return {}

    async def assess_progress(self, goal_id: int) -> GoalProgress:
        """Assess progress toward a specific goal."""
        import anthropic

        with sqlite3.connect(self._db_path) as conn:
            goal_row = conn.execute(
                "SELECT title, description, horizon FROM goals WHERE id=?", (goal_id,)
            ).fetchone()
            if not goal_row:
                return GoalProgress(goal_id, 0, "unknown", [], [], "", False)

            tasks = conn.execute("""
                SELECT task, contribution, quality_score, linked_at
                FROM goal_tasks WHERE goal_id=? ORDER BY linked_at DESC LIMIT 20
            """, (goal_id,)).fetchall()

        tasks_str = "\n".join(
            f"  - {t[0][:100]} (quality={t[2]:.0f})"
            for t in tasks
        ) or "No tasks linked yet."

        client = anthropic.Anthropic(api_key=config.anthropic_api_key)
        try:
            response = client.messages.create(
                model=config.fast_model,
                max_tokens=800,
                messages=[{"role": "user", "content": PROGRESS_ASSESSOR_PROMPT.format(
                    goal_title=goal_row[0],
                    goal_description=goal_row[1],
                    horizon=goal_row[2],
                    linked_tasks=tasks_str,
                )}],
            )
            raw = response.content[0].text
            start = raw.find("{")
            end = raw.rfind("}") + 1
            parsed = json.loads(raw[start:end])
            return GoalProgress(
                goal_id=goal_id,
                completion_percentage=float(parsed.get("completion_percentage", 0)),
                momentum=parsed.get("momentum", "unknown"),
                key_achievements=parsed.get("key_achievements", []),
                blockers=parsed.get("blockers", []),
                next_action=parsed.get("next_action", ""),
                on_track=bool(parsed.get("on_track", False)),
            )
        except Exception:
            return GoalProgress(goal_id, 0, "unknown", [], [], "", False)

    def get_active_goals(self, project_id: str | None = None) -> list[Goal]:
        """Return all active goals."""
        try:
            with sqlite3.connect(self._db_path) as conn:
                if project_id:
                    rows = conn.execute("""
                        SELECT id, title, description, horizon, priority, status,
                               parent_id, project_id, completion_pct, created_at
                        FROM goals WHERE status='active' AND (project_id=? OR project_id IS NULL)
                        ORDER BY priority DESC
                    """, (project_id,)).fetchall()
                else:
                    rows = conn.execute("""
                        SELECT id, title, description, horizon, priority, status,
                               parent_id, project_id, completion_pct, created_at
                        FROM goals WHERE status='active'
                        ORDER BY priority DESC
                    """).fetchall()
            return [Goal(
                goal_id=r[0], title=r[1], description=r[2], horizon=r[3],
                priority=r[4], status=r[5], parent_id=r[6], project_id=r[7],
                completion_pct=r[8], created_at=r[9],
            ) for r in rows]
        except Exception:
            return []

    def format_goal_tree(self, project_id: str | None = None) -> str:
        """Render the goal hierarchy as a tree."""
        goals = self.get_active_goals(project_id)
        if not goals:
            return "No active goals. Add one with /goal <title>."

        horizon_order = {"visionary": 0, "strategic": 1, "tactical": 2, "immediate": 3}
        goals.sort(key=lambda g: (horizon_order.get(g.horizon, 9), -g.priority))

        horizon_icons = {
            "visionary": "🌐", "strategic": "🎯",
            "tactical": "📋", "immediate": "⚡",
        }
        lines = []
        current_horizon = None
        for g in goals:
            if g.horizon != current_horizon:
                current_horizon = g.horizon
                icon = horizon_icons.get(g.horizon, "•")
                lines.append(f"\n{icon} {g.horizon.upper()}")
            pct = f" [{g.completion_pct:.0f}%]" if g.completion_pct > 0 else ""
            lines.append(f"  [{g.goal_id}] {g.title}{pct} (priority={g.priority:.1f})")
        return "\n".join(lines)


goal_manager = GoalHierarchyManager()
