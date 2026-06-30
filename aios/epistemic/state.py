"""
Epistemic State Machine
Explicit tracking of WHAT the AI knows, believes, suspects,
and crucially — what it doesn't know it doesn't know.
Transforms confidence from a number into a structured knowledge map.

States:
  KNOWN          — verified fact, high confidence, strong evidence
  BELIEVED       — strong evidence, likely true, could be wrong
  SUSPECTED      — weak evidence, uncertain, needs verification
  UNKNOWN_KNOWN  — we know we don't know this (documented gap)
  UNKNOWN_UNKNOWN — discovered blind spot we didn't know existed
"""

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path

from ..config import config

ASSESSOR_PROMPT = """You are an Epistemic Assessor. Evaluate the knowledge status of claims in this content.

Content: {content}
Task it was generated for: {task}

For each significant claim or assertion, determine its epistemic status:
- KNOWN: verified fact with strong evidence, high confidence
- BELIEVED: well-supported but not certain, could be challenged
- SUSPECTED: weakly supported, uncertain, requires validation
- UNKNOWN_KNOWN: we know this is a gap in our knowledge
- UNKNOWN_UNKNOWN: a blind spot that we didn't even realize existed until now

Return JSON array:
[
  {{
    "claim": "The specific claim or assertion",
    "status": "BELIEVED",
    "confidence": 0.85,
    "supporting_evidence": ["evidence 1"],
    "challenging_evidence": ["what could prove this wrong"],
    "domain": "the knowledge domain",
    "importance": 7.0
  }}
]

Focus on the most important claims. Return 3-8 assessments."""

BLIND_SPOT_PROMPT = """You are a Blind Spot Detector. Find UNKNOWN_UNKNOWNS in this domain.

Domain: {domain}
What we currently know/believe about it:
{current_knowledge}

Identify things that are:
1. NOT mentioned but probably important
2. Assumptions we're implicitly making without realizing it
3. Questions we haven't thought to ask
4. Perspectives we haven't considered

These are things we don't know we don't know — genuine blind spots.

Return JSON:
[
  {{
    "blind_spot": "Description of what we're missing",
    "why_matters": "Why this missing knowledge could change our thinking",
    "investigation_hint": "How to explore this blind spot",
    "estimated_importance": 7.5
  }}
]

Return 3-6 genuine blind spots. Be creative and non-obvious."""


class EpistemicStatus(str, Enum):
    KNOWN = "KNOWN"
    BELIEVED = "BELIEVED"
    SUSPECTED = "SUSPECTED"
    UNKNOWN_KNOWN = "UNKNOWN_KNOWN"
    UNKNOWN_UNKNOWN = "UNKNOWN_UNKNOWN"


@dataclass
class EpistemicClaim:
    claim_id: int
    claim: str
    status: str
    confidence: float
    supporting_evidence: list[str]
    challenging_evidence: list[str]
    domain: str
    importance: float
    source_task: str
    recorded_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class BlindSpot:
    blind_spot: str
    why_matters: str
    investigation_hint: str
    estimated_importance: float
    domain: str


class EpistemicStateMachine:
    """
    Maintains a structured map of what the AI knows vs doesn't know.
    Actively hunts for unknown unknowns — the most dangerous knowledge gaps.
    """

    def __init__(self):
        self._db_path = Path(config.db_path).parent / "epistemic.db"

    def initialize(self) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS epistemic_claims (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    claim TEXT NOT NULL,
                    status TEXT NOT NULL,
                    confidence REAL DEFAULT 0.5,
                    supporting_evidence TEXT DEFAULT '[]',
                    challenging_evidence TEXT DEFAULT '[]',
                    domain TEXT DEFAULT 'general',
                    importance REAL DEFAULT 5.0,
                    source_task TEXT DEFAULT '',
                    recorded_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now'))
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS blind_spots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    blind_spot TEXT NOT NULL,
                    why_matters TEXT DEFAULT '',
                    investigation_hint TEXT DEFAULT '',
                    estimated_importance REAL DEFAULT 5.0,
                    domain TEXT DEFAULT 'general',
                    investigated INTEGER DEFAULT 0,
                    discovered_at TEXT DEFAULT (datetime('now'))
                )
            """)

    async def assess_content(self, content: str, task: str) -> list[EpistemicClaim]:
        """Assess epistemic status of claims in a piece of content."""
        import anthropic

        client = anthropic.Anthropic(api_key=config.api_key)
        try:
            response = client.messages.create(
                model=config.fast_model,
                max_tokens=2000,
                messages=[{"role": "user", "content": ASSESSOR_PROMPT.format(
                    content=content[:3000],
                    task=task[:500],
                )}],
            )
            raw = response.content[0].text
            start = raw.find("[")
            end = raw.rfind("]") + 1
            if start < 0 or end <= start:
                return []

            raw_claims = json.loads(raw[start:end])
            claims: list[EpistemicClaim] = []

            with sqlite3.connect(self._db_path) as conn:
                for rc in raw_claims:
                    status = rc.get("status", "SUSPECTED")
                    if status not in [e.value for e in EpistemicStatus]:
                        status = "SUSPECTED"

                    cursor = conn.execute("""
                        INSERT INTO epistemic_claims
                        (claim, status, confidence, supporting_evidence,
                         challenging_evidence, domain, importance, source_task)
                        VALUES (?,?,?,?,?,?,?,?)
                    """, (
                        rc.get("claim", "")[:500],
                        status,
                        float(rc.get("confidence", 0.5)),
                        json.dumps(rc.get("supporting_evidence", [])),
                        json.dumps(rc.get("challenging_evidence", [])),
                        rc.get("domain", "general"),
                        float(rc.get("importance", 5.0)),
                        task[:200],
                    ))
                    claims.append(EpistemicClaim(
                        claim_id=cursor.lastrowid,
                        claim=rc.get("claim", ""),
                        status=status,
                        confidence=float(rc.get("confidence", 0.5)),
                        supporting_evidence=rc.get("supporting_evidence", []),
                        challenging_evidence=rc.get("challenging_evidence", []),
                        domain=rc.get("domain", "general"),
                        importance=float(rc.get("importance", 5.0)),
                        source_task=task[:200],
                    ))
            return claims
        except Exception:
            return []

    async def find_blind_spots(self, domain: str) -> list[BlindSpot]:
        """Actively hunt for unknown unknowns in a domain."""
        import anthropic

        # Get what we currently know about this domain
        try:
            with sqlite3.connect(self._db_path) as conn:
                rows = conn.execute("""
                    SELECT claim, status, confidence FROM epistemic_claims
                    WHERE domain=? AND status IN ('KNOWN', 'BELIEVED')
                    ORDER BY importance DESC LIMIT 20
                """, (domain,)).fetchall()
            current_knowledge = "\n".join(
                f"  [{r[1]}:{r[2]:.0%}] {r[0]}" for r in rows
            ) or "No prior knowledge recorded about this domain."
        except Exception:
            current_knowledge = "No prior knowledge recorded."

        client = anthropic.Anthropic(api_key=config.api_key)
        try:
            response = client.messages.create(
                model=config.worker_model,
                max_tokens=1500,
                messages=[{"role": "user", "content": BLIND_SPOT_PROMPT.format(
                    domain=domain,
                    current_knowledge=current_knowledge,
                )}],
            )
            raw = response.content[0].text
            start = raw.find("[")
            end = raw.rfind("]") + 1
            if start < 0 or end <= start:
                return []

            raw_spots = json.loads(raw[start:end])
            spots: list[BlindSpot] = []

            with sqlite3.connect(self._db_path) as conn:
                for rs in raw_spots:
                    conn.execute("""
                        INSERT INTO blind_spots
                        (blind_spot, why_matters, investigation_hint, estimated_importance, domain)
                        VALUES (?,?,?,?,?)
                    """, (
                        rs.get("blind_spot", "")[:500],
                        rs.get("why_matters", "")[:300],
                        rs.get("investigation_hint", "")[:300],
                        float(rs.get("estimated_importance", 5.0)),
                        domain,
                    ))
                    spots.append(BlindSpot(
                        blind_spot=rs.get("blind_spot", ""),
                        why_matters=rs.get("why_matters", ""),
                        investigation_hint=rs.get("investigation_hint", ""),
                        estimated_importance=float(rs.get("estimated_importance", 5.0)),
                        domain=domain,
                    ))
            return spots
        except Exception:
            return []

    def get_knowledge_map(self, domain: str | None = None) -> dict[str, list[EpistemicClaim]]:
        """Return the current knowledge map grouped by epistemic status."""
        try:
            with sqlite3.connect(self._db_path) as conn:
                if domain:
                    rows = conn.execute("""
                        SELECT id, claim, status, confidence, supporting_evidence,
                               challenging_evidence, domain, importance, source_task
                        FROM epistemic_claims
                        WHERE domain=?
                        ORDER BY importance DESC
                    """, (domain,)).fetchall()
                else:
                    rows = conn.execute("""
                        SELECT id, claim, status, confidence, supporting_evidence,
                               challenging_evidence, domain, importance, source_task
                        FROM epistemic_claims
                        ORDER BY importance DESC LIMIT 100
                    """).fetchall()

            claims_by_status: dict[str, list[EpistemicClaim]] = {
                s.value: [] for s in EpistemicStatus
            }
            for r in rows:
                claim = EpistemicClaim(
                    claim_id=r[0], claim=r[1], status=r[2], confidence=r[3],
                    supporting_evidence=json.loads(r[4] or "[]"),
                    challenging_evidence=json.loads(r[5] or "[]"),
                    domain=r[6], importance=r[7], source_task=r[8] or "",
                )
                if r[2] in claims_by_status:
                    claims_by_status[r[2]].append(claim)
            return claims_by_status
        except Exception:
            return {}

    def format_knowledge_map(self, domain: str | None = None) -> str:
        km = self.get_knowledge_map(domain)
        if not any(km.values()):
            return "No epistemic assessments yet. Claims are assessed during task execution."

        status_icons = {
            "KNOWN": "✓",
            "BELIEVED": "~",
            "SUSPECTED": "?",
            "UNKNOWN_KNOWN": "○",
            "UNKNOWN_UNKNOWN": "⚠",
        }
        lines = [f"Epistemic Map{f' — {domain}' if domain else ''}"]
        for status, icon in status_icons.items():
            claims = km.get(status, [])
            if not claims:
                continue
            lines.append(f"\n{icon} {status} ({len(claims)})")
            for c in claims[:5]:
                lines.append(f"  [{c.confidence:.0%}] {c.claim[:100]}")

        # Add blind spots
        try:
            with sqlite3.connect(self._db_path) as conn:
                spots = conn.execute(
                    "SELECT blind_spot FROM blind_spots WHERE investigated=0 ORDER BY estimated_importance DESC LIMIT 5"
                ).fetchall()
            if spots:
                lines.append(f"\n⚠ UNKNOWN_UNKNOWN — Active Blind Spots")
                for (bs,) in spots:
                    lines.append(f"  ! {bs[:100]}")
        except Exception:
            pass

        return "\n".join(lines)

    def get_stats(self) -> dict:
        try:
            with sqlite3.connect(self._db_path) as conn:
                rows = conn.execute("""
                    SELECT status, COUNT(*) FROM epistemic_claims GROUP BY status
                """).fetchall()
                blind = conn.execute(
                    "SELECT COUNT(*) FROM blind_spots WHERE investigated=0"
                ).fetchone()[0]
            return {
                "by_status": {r[0]: r[1] for r in rows},
                "uninvestigated_blind_spots": blind,
            }
        except Exception:
            return {}


epistemic_machine = EpistemicStateMachine()
