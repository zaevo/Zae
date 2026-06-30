"""
Theory of Mind Layer
Models the user's expertise, beliefs, intentions, emotional state, and
communication preferences. Calibrates every final response to the actual
human on the other end — not a generic average user.
"""

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from ..config import config

OBSERVER_PROMPT = """You observe human-AI interactions to build a model of the human user.

Analyze this interaction and extract signals about the user:

Task the user gave: {task}
AI Response: {response}

Return JSON:
{{
  "expertise_signals": {{
    "domain": "what domain this task was in",
    "level": "novice|intermediate|expert|unknown",
    "evidence": "what in their phrasing suggests this level"
  }},
  "communication_preferences": {{
    "verbosity": "brief|moderate|detailed",
    "style": "technical|plain|mixed",
    "format": "prose|bullets|structured|code"
  }},
  "cognitive_state": {{
    "apparent_urgency": "low|medium|high",
    "apparent_stress": "low|medium|high",
    "focus": "exploratory|decisive|uncertain"
  }},
  "implicit_goals": ["what they probably really want beyond what they asked"],
  "likely_misconceptions": ["things they might believe that are wrong"],
  "what_not_to_explain": ["things they clearly already understand"]
}}"""

CALIBRATION_PROMPT = """You are calibrating a response to a specific human user.

User Model:
{user_model}

Original Response (draft):
{draft}

User's Task:
{task}

Rewrite the response to perfectly fit this specific user:
- Match their expertise level (don't over-explain what they know; don't assume what they don't)
- Match their preferred communication style
- Address their implicit goals, not just their explicit question
- Avoid explaining things they clearly already know
- Use their vocabulary level

Return the calibrated response directly — no meta-commentary."""


@dataclass
class UserModel:
    user_id: str
    expertise_by_domain: dict[str, str] = field(default_factory=dict)
    communication_style: str = "moderate"
    verbosity_preference: str = "moderate"
    format_preference: str = "mixed"
    apparent_goals: list[str] = field(default_factory=list)
    known_misconceptions: list[str] = field(default_factory=list)
    interaction_count: int = 0
    model_confidence: float = 0.0
    last_updated: str = field(default_factory=lambda: datetime.utcnow().isoformat())


class TheoryOfMindModeler:
    """
    Maintains a persistent mental model of the user.
    Calibrates responses to match who the user actually is.
    """

    def __init__(self):
        self._db_path = Path(config.db_path).parent / "theory_of_mind.db"

    def initialize(self) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_observations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    task TEXT NOT NULL,
                    expertise_domain TEXT,
                    expertise_level TEXT,
                    communication_style TEXT,
                    verbosity TEXT,
                    format_pref TEXT,
                    urgency TEXT,
                    implicit_goals TEXT,
                    misconceptions TEXT,
                    observed_at TEXT DEFAULT (datetime('now'))
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_model (
                    user_id TEXT PRIMARY KEY,
                    expertise_json TEXT DEFAULT '{}',
                    communication_style TEXT DEFAULT 'moderate',
                    verbosity TEXT DEFAULT 'moderate',
                    format_pref TEXT DEFAULT 'mixed',
                    goals_json TEXT DEFAULT '[]',
                    misconceptions_json TEXT DEFAULT '[]',
                    interaction_count INTEGER DEFAULT 0,
                    model_confidence REAL DEFAULT 0.0,
                    last_updated TEXT DEFAULT (datetime('now'))
                )
            """)

    async def observe(self, task: str, response: str, user_id: str = "default") -> None:
        """Observe an interaction and update the user model."""
        import anthropic

        client = anthropic.Anthropic(api_key=config.anthropic_api_key)
        try:
            obs_response = client.messages.create(
                model=config.fast_model,
                max_tokens=800,
                messages=[{"role": "user", "content": OBSERVER_PROMPT.format(
                    task=task[:1000],
                    response=response[:1000],
                )}],
            )
            obs_text = obs_response.content[0].text
            start = obs_text.find("{")
            end = obs_text.rfind("}") + 1
            if start < 0 or end <= start:
                return

            obs = json.loads(obs_text[start:end])
            expertise = obs.get("expertise_signals", {})
            comm = obs.get("communication_preferences", {})
            cog = obs.get("cognitive_state", {})
            implicit = obs.get("implicit_goals", [])
            misconceptions = obs.get("likely_misconceptions", [])

            # Store raw observation
            with sqlite3.connect(self._db_path) as conn:
                conn.execute("""
                    INSERT INTO user_observations
                    (user_id, task, expertise_domain, expertise_level,
                     communication_style, verbosity, format_pref, urgency,
                     implicit_goals, misconceptions)
                    VALUES (?,?,?,?,?,?,?,?,?,?)
                """, (
                    user_id, task[:300],
                    expertise.get("domain", ""),
                    expertise.get("level", "unknown"),
                    comm.get("style", ""),
                    comm.get("verbosity", ""),
                    comm.get("format", ""),
                    cog.get("apparent_urgency", ""),
                    json.dumps(implicit),
                    json.dumps(misconceptions),
                ))

                # Update aggregated model
                row = conn.execute(
                    "SELECT * FROM user_model WHERE user_id=?", (user_id,)
                ).fetchone()

                if row:
                    existing_expertise = json.loads(row[1] or "{}")
                    domain = expertise.get("domain", "general")
                    if domain:
                        existing_expertise[domain] = expertise.get("level", "unknown")
                    existing_goals = json.loads(row[5] or "[]")
                    existing_goals = list(set(existing_goals + implicit))[-20:]
                    existing_misc = json.loads(row[6] or "[]")
                    existing_misc = list(set(existing_misc + misconceptions))[-20:]
                    count = (row[7] or 0) + 1
                    confidence = min(1.0, count / 20)

                    conn.execute("""
                        UPDATE user_model SET
                        expertise_json=?, communication_style=?, verbosity=?,
                        format_pref=?, goals_json=?, misconceptions_json=?,
                        interaction_count=?, model_confidence=?, last_updated=datetime('now')
                        WHERE user_id=?
                    """, (
                        json.dumps(existing_expertise),
                        comm.get("style", row[2]),
                        comm.get("verbosity", row[3]),
                        comm.get("format", row[4]),
                        json.dumps(existing_goals),
                        json.dumps(existing_misc),
                        count, confidence, user_id,
                    ))
                else:
                    expertise_json = {}
                    if expertise.get("domain"):
                        expertise_json[expertise["domain"]] = expertise.get("level", "unknown")
                    conn.execute("""
                        INSERT INTO user_model
                        (user_id, expertise_json, communication_style, verbosity, format_pref,
                         goals_json, misconceptions_json, interaction_count, model_confidence)
                        VALUES (?,?,?,?,?,?,?,1,0.05)
                    """, (
                        user_id,
                        json.dumps(expertise_json),
                        comm.get("style", "mixed"),
                        comm.get("verbosity", "moderate"),
                        comm.get("format", "mixed"),
                        json.dumps(implicit),
                        json.dumps(misconceptions),
                    ))
        except Exception:
            pass

    def get_model(self, user_id: str = "default") -> UserModel | None:
        """Retrieve the current user model."""
        try:
            with sqlite3.connect(self._db_path) as conn:
                row = conn.execute(
                    "SELECT * FROM user_model WHERE user_id=?", (user_id,)
                ).fetchone()
                if not row:
                    return None
                return UserModel(
                    user_id=row[0],
                    expertise_by_domain=json.loads(row[1] or "{}"),
                    communication_style=row[2] or "moderate",
                    verbosity_preference=row[3] or "moderate",
                    format_preference=row[4] or "mixed",
                    apparent_goals=json.loads(row[5] or "[]"),
                    known_misconceptions=json.loads(row[6] or "[]"),
                    interaction_count=row[7] or 0,
                    model_confidence=row[8] or 0.0,
                )
        except Exception:
            return None

    async def calibrate_response(
        self, task: str, draft: str, user_id: str = "default"
    ) -> str:
        """Rewrite draft response to fit the user's mental model."""
        model = self.get_model(user_id)
        if not model or model.model_confidence < 0.15 or len(draft) < 100:
            return draft  # not enough data yet to calibrate

        import anthropic

        user_model_str = json.dumps({
            "expertise_by_domain": model.expertise_by_domain,
            "communication_style": model.communication_style,
            "verbosity_preference": model.verbosity_preference,
            "format_preference": model.format_preference,
            "apparent_goals": model.apparent_goals[:5],
            "things_they_know": list(model.expertise_by_domain.keys()),
            "model_confidence": f"{model.model_confidence:.0%}",
            "interactions_observed": model.interaction_count,
        }, indent=2)

        try:
            client = anthropic.Anthropic(api_key=config.anthropic_api_key)
            cal_response = client.messages.create(
                model=config.fast_model,
                max_tokens=len(draft.split()) * 2 + 200,
                messages=[{"role": "user", "content": CALIBRATION_PROMPT.format(
                    user_model=user_model_str,
                    draft=draft[:4000],
                    task=task[:500],
                )}],
            )
            calibrated = cal_response.content[0].text.strip()
            return calibrated if len(calibrated) > 100 else draft
        except Exception:
            return draft

    def summarize_model(self, user_id: str = "default") -> str:
        model = self.get_model(user_id)
        if not model:
            return "No user model built yet. More interactions needed."
        lines = [
            f"Interactions observed: {model.interaction_count}",
            f"Model confidence: {model.model_confidence:.0%}",
            f"Communication style: {model.communication_style} / {model.verbosity_preference} verbosity / {model.format_preference} format",
        ]
        if model.expertise_by_domain:
            lines.append("Expertise: " + ", ".join(
                f"{d}={l}" for d, l in model.expertise_by_domain.items()
            ))
        if model.apparent_goals:
            lines.append("Apparent goals: " + "; ".join(model.apparent_goals[:3]))
        return "\n".join(lines)


tom_modeler = TheoryOfMindModeler()
