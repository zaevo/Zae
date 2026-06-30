"""
Cognitive Fingerprinting

Builds a model of HOW the user thinks — their blind spots, reasoning patterns,
what they consistently underestimate, what they over-optimize for.

AIOS uses this to automatically compensate for the user's cognitive biases
before delivering any answer.
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


PATTERN_ANALYZER_PROMPT = f"""
{MASTER_SYSTEM_PROMPT}

## YOUR ROLE: Cognitive Pattern Analyzer

You observe how a person asks questions and makes decisions over time.
Your job: identify patterns in their thinking — strengths, blind spots, biases.

Analyze this interaction and extract cognitive patterns:

PATTERNS TO LOOK FOR:
- Optimism/pessimism bias (do they consistently over/underestimate?)
- Risk tolerance (do they avoid risk or embrace it even when costly?)
- Detail orientation (do they miss the forest for the trees, or vice versa?)
- Decision style (quick and intuitive, or slow and analytical?)
- Domain blind spots (where do they consistently lack knowledge?)
- Communication preferences (how do they prefer to receive information?)
- Common logical errors (what reasoning mistakes do they make repeatedly?)
- Urgency patterns (do they treat everything as urgent, or under-prioritize?)

Output as JSON:
{{
  "patterns": [
    {{
      "type": "bias",
      "name": "Timeline optimism bias",
      "description": "Consistently underestimates time for technical tasks by 50-100%",
      "evidence": "Asked for '2-hour fix' on a problem that took 3 days",
      "compensation": "Multiply technical timeline estimates by 2x automatically",
      "confidence": 0.8
    }}
  ],
  "cognitive_style": "analytical | intuitive | mixed",
  "risk_tolerance": "low | medium | high",
  "communication_preference": "brief | detailed | structured",
  "primary_blind_spots": ["technical complexity", "market validation"]
}}
"""

COMPENSATION_PROMPT = f"""
{MASTER_SYSTEM_PROMPT}

## YOUR ROLE: Cognitive Compensation Engine

You know the user's cognitive fingerprint — their known biases, blind spots, and patterns.
Your job: review any response BEFORE delivery and apply compensations.

For each known bias: has this response already accounted for it?
If not: add the compensation automatically.

Output: The cognitively-compensated version of the response, with a brief note
on what compensations were applied.
"""


@dataclass
class CognitivePattern:
    id: str
    pattern_type: str           # bias | strength | blind_spot | preference | error
    name: str
    description: str
    evidence: str
    compensation: str
    confidence: float
    observation_count: int = 1
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_observed: datetime = field(default_factory=datetime.utcnow)


@dataclass
class CognitiveProfile:
    user_id: str
    patterns: list[CognitivePattern]
    cognitive_style: str        # analytical | intuitive | mixed
    risk_tolerance: str         # low | medium | high
    communication_preference: str  # brief | detailed | structured
    primary_blind_spots: list[str]
    primary_strengths: list[str]
    interaction_count: int
    profile_confidence: float   # how confident we are in this profile


@dataclass
class CompensationResult:
    original: str
    compensated: str
    compensations_applied: list[str]
    biases_detected: list[str]


class CognitiveFingerprintEngine:
    """
    Builds and applies a cognitive model of the user.
    Every interaction makes the model more accurate.
    Every response is compensated for known biases before delivery.
    """

    def __init__(self, user_id: str = "default"):
        self.user_id = user_id
        self._conn: sqlite3.Connection | None = None
        self._analyzer = _PatternAnalyzerAgent()
        self._compensator = _CompensationAgent()
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
            CREATE TABLE IF NOT EXISTS cognitive_patterns (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                pattern_type TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT NOT NULL,
                evidence TEXT,
                compensation TEXT,
                confidence REAL DEFAULT 0.5,
                observation_count INTEGER DEFAULT 1,
                created_at TEXT NOT NULL,
                last_observed TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS cognitive_profile (
                user_id TEXT PRIMARY KEY,
                cognitive_style TEXT DEFAULT 'mixed',
                risk_tolerance TEXT DEFAULT 'medium',
                communication_preference TEXT DEFAULT 'detailed',
                primary_blind_spots TEXT DEFAULT '[]',
                primary_strengths TEXT DEFAULT '[]',
                interaction_count INTEGER DEFAULT 0,
                profile_confidence REAL DEFAULT 0.0,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_cp_user ON cognitive_patterns(user_id);
            CREATE INDEX IF NOT EXISTS idx_cp_type ON cognitive_patterns(pattern_type);
        """)
        conn.commit()
        self._initialized = True

    async def observe_interaction(
        self, task: str, response: str, feedback: str | None = None
    ) -> list[CognitivePattern]:
        if not self._initialized:
            self.initialize()

        existing_profile = self._get_profile_summary()
        result = await self._analyzer.run(
            f"USER INTERACTION:\nTask asked: {task[:500]}\n\n"
            f"EXISTING PROFILE:\n{existing_profile}\n\n"
            f"FEEDBACK (if any): {feedback or 'None'}\n\n"
            f"Extract cognitive patterns from this interaction."
        )
        if not result.succeeded:
            return []

        patterns = []
        try:
            content = result.content
            start = content.find("{")
            end = content.rfind("}") + 1
            if start < 0:
                return []
            data = json.loads(content[start:end])
            conn = self._get_conn()

            for p in data.get("patterns", []):
                # Check if this pattern already exists
                existing = conn.execute(
                    "SELECT * FROM cognitive_patterns WHERE user_id = ? AND name = ?",
                    (self.user_id, p.get("name", "")),
                ).fetchone()

                if existing:
                    # Reinforce existing pattern
                    new_confidence = min(0.99, existing["confidence"] + 0.05)
                    conn.execute(
                        """UPDATE cognitive_patterns SET confidence = ?,
                           observation_count = observation_count + 1,
                           last_observed = ? WHERE id = ?""",
                        (new_confidence, datetime.utcnow().isoformat(), existing["id"]),
                    )
                    patterns.append(self._row_to_pattern(existing))
                else:
                    # New pattern discovered
                    pattern = CognitivePattern(
                        id=str(uuid.uuid4()),
                        pattern_type=p.get("type", "bias"),
                        name=p.get("name", ""),
                        description=p.get("description", ""),
                        evidence=p.get("evidence", ""),
                        compensation=p.get("compensation", ""),
                        confidence=float(p.get("confidence", 0.5)),
                    )
                    conn.execute(
                        """INSERT INTO cognitive_patterns
                           (id, user_id, pattern_type, name, description, evidence,
                            compensation, confidence, observation_count, created_at, last_observed)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                        (
                            pattern.id, self.user_id, pattern.pattern_type,
                            pattern.name, pattern.description, pattern.evidence,
                            pattern.compensation, pattern.confidence,
                            pattern.observation_count,
                            pattern.created_at.isoformat(),
                            pattern.last_observed.isoformat(),
                        ),
                    )
                    patterns.append(pattern)

            # Update profile
            self._update_profile(data)
            conn.commit()
        except (json.JSONDecodeError, ValueError):
            pass
        return patterns

    async def compensate(self, task: str, response: str) -> CompensationResult:
        """Apply cognitive compensations to a response before delivery."""
        if not self._initialized:
            self.initialize()

        profile = self.get_profile()
        if not profile or profile.profile_confidence < 0.3:
            return CompensationResult(
                original=response, compensated=response,
                compensations_applied=[], biases_detected=[],
            )

        high_confidence_patterns = [
            p for p in profile.patterns
            if p.confidence >= 0.6 and p.pattern_type in ("bias", "blind_spot")
        ]
        if not high_confidence_patterns:
            return CompensationResult(
                original=response, compensated=response,
                compensations_applied=[], biases_detected=[],
            )

        patterns_text = "\n".join([
            f"- {p.name}: {p.description}\n  Compensation: {p.compensation}"
            for p in high_confidence_patterns[:5]
        ])

        result = await self._compensator.run(
            f"TASK THE USER ASKED:\n{task[:500]}\n\n"
            f"KNOWN USER BIASES TO COMPENSATE FOR:\n{patterns_text}\n\n"
            f"RESPONSE TO COMPENSATE:\n{response[:3000]}\n\n"
            f"Apply compensations and return improved response."
        )

        if not result.succeeded or len(result.content) < 100:
            return CompensationResult(
                original=response, compensated=response,
                compensations_applied=[], biases_detected=[],
            )

        compensations = [p.compensation for p in high_confidence_patterns[:5]]
        biases = [p.name for p in high_confidence_patterns[:5]]

        return CompensationResult(
            original=response,
            compensated=result.content,
            compensations_applied=compensations,
            biases_detected=biases,
        )

    def get_profile(self) -> CognitiveProfile | None:
        if not self._initialized:
            self.initialize()
        conn = self._get_conn()
        profile_row = conn.execute(
            "SELECT * FROM cognitive_profile WHERE user_id = ?", (self.user_id,)
        ).fetchone()
        pattern_rows = conn.execute(
            "SELECT * FROM cognitive_patterns WHERE user_id = ? ORDER BY confidence DESC",
            (self.user_id,),
        ).fetchall()

        if not profile_row and not pattern_rows:
            return None

        patterns = [self._row_to_pattern(r) for r in pattern_rows]
        if profile_row:
            return CognitiveProfile(
                user_id=self.user_id,
                patterns=patterns,
                cognitive_style=profile_row["cognitive_style"],
                risk_tolerance=profile_row["risk_tolerance"],
                communication_preference=profile_row["communication_preference"],
                primary_blind_spots=json.loads(profile_row["primary_blind_spots"] or "[]"),
                primary_strengths=json.loads(profile_row["primary_strengths"] or "[]"),
                interaction_count=profile_row["interaction_count"],
                profile_confidence=profile_row["profile_confidence"],
            )
        return CognitiveProfile(
            user_id=self.user_id, patterns=patterns,
            cognitive_style="mixed", risk_tolerance="medium",
            communication_preference="detailed",
            primary_blind_spots=[], primary_strengths=[],
            interaction_count=len(patterns), profile_confidence=0.3,
        )

    def _get_profile_summary(self) -> str:
        profile = self.get_profile()
        if not profile:
            return "No profile yet. First interaction."
        known = "\n".join([f"- {p.name} ({p.confidence:.0%} confidence)" for p in profile.patterns[:5]])
        return (
            f"Cognitive style: {profile.cognitive_style}\n"
            f"Risk tolerance: {profile.risk_tolerance}\n"
            f"Communication preference: {profile.communication_preference}\n"
            f"Known patterns:\n{known}"
        )

    def _update_profile(self, data: dict) -> None:
        conn = self._get_conn()
        now = datetime.utcnow().isoformat()
        existing = conn.execute(
            "SELECT * FROM cognitive_profile WHERE user_id = ?", (self.user_id,)
        ).fetchone()

        if existing:
            conn.execute(
                """UPDATE cognitive_profile SET
                   interaction_count = interaction_count + 1,
                   profile_confidence = MIN(0.95, profile_confidence + 0.03),
                   updated_at = ? WHERE user_id = ?""",
                (now, self.user_id),
            )
        else:
            conn.execute(
                """INSERT INTO cognitive_profile
                   (user_id, cognitive_style, risk_tolerance, communication_preference,
                    primary_blind_spots, primary_strengths, interaction_count,
                    profile_confidence, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (
                    self.user_id,
                    data.get("cognitive_style", "mixed"),
                    data.get("risk_tolerance", "medium"),
                    data.get("communication_preference", "detailed"),
                    json.dumps(data.get("primary_blind_spots", [])),
                    json.dumps(data.get("primary_strengths", [])),
                    1, 0.1, now,
                ),
            )

    def _row_to_pattern(self, row: sqlite3.Row) -> CognitivePattern:
        return CognitivePattern(
            id=row["id"],
            pattern_type=row["pattern_type"],
            name=row["name"],
            description=row["description"],
            evidence=row["evidence"] or "",
            compensation=row["compensation"] or "",
            confidence=row["confidence"],
            observation_count=row["observation_count"],
        )


class _PatternAnalyzerAgent(BaseAgent):
    name = "pattern_analyzer"

    def __init__(self):
        super().__init__()
        self._system_prompt = PATTERN_ANALYZER_PROMPT
        self.model = config.worker_model


class _CompensationAgent(BaseAgent):
    name = "compensation_engine"

    def __init__(self):
        super().__init__()
        self._system_prompt = COMPENSATION_PROMPT
        self.model = config.worker_model
