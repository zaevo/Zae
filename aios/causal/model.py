"""
Causal World Model
Goes beyond correlation. Understands interventions:
"If I CHANGE X, what actually happens to Y?"
Uses do-calculus principles: observational vs interventional queries.
"""

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from ..config import config

CAUSAL_EXTRACTOR_PROMPT = """You are a Causal Graph Builder. Extract cause-effect relationships from this text.

Text: {text}

Identify causal links — not just correlations. A causal link exists when X *produces* or *prevents* Y,
not just when X and Y happen together.

Return JSON array:
[
  {{
    "cause": "variable or event A",
    "effect": "variable or event B",
    "mechanism": "how A produces B",
    "strength": 0.8,
    "confidence": 0.9,
    "direction": "positive",
    "conditions": ["only when C is true"],
    "domain": "economics|health|technology|business|social|other"
  }}
]

strength: 0.0=very weak, 1.0=deterministic
direction: "positive"=A increases B, "negative"=A decreases B, "nonlinear"=complex

Extract 1-6 links. Only real causal relationships — not associations."""

DO_QUERY_PROMPT = """You are reasoning about causal interventions using do-calculus principles.

Causal Graph (existing knowledge):
{causal_graph}

Question: If we INTERVENE and SET '{intervention_variable}' to '{intervention_value}',
what happens to '{target_variable}'?

This is an INTERVENTIONAL query (do-calculus), not observational.
The intervention breaks any incoming causal arrows to '{intervention_variable}'.

Reason step by step:
1. What paths exist from {intervention_variable} to {target_variable}?
2. What confounders exist that the intervention blocks?
3. What is the predicted effect and magnitude?
4. What assumptions does this rely on?

Return JSON:
{{
  "predicted_effect": "what happens to {target_variable}",
  "direction": "increases|decreases|unclear|none",
  "magnitude": "large|moderate|small|negligible",
  "confidence": 0.75,
  "causal_path": ["A -> B -> C"],
  "blocked_confounders": ["variables whose influence is blocked by intervention"],
  "key_assumptions": ["assumption1"],
  "reasoning": "step by step explanation"
}}"""

ROOT_CAUSE_PROMPT = """Trace the root causes of this effect through the causal graph.

Effect to explain: {effect}

Causal Graph:
{causal_graph}

Work backwards from the effect. Find:
1. Direct causes
2. Root causes (causes with no parents in the graph)
3. The most actionable lever (what you can intervene on to prevent this)

Return JSON:
{{
  "direct_causes": ["immediate cause 1", "immediate cause 2"],
  "root_causes": ["fundamental cause"],
  "most_actionable_lever": "what to change",
  "causal_chain": ["root -> intermediate -> effect"],
  "confidence": 0.7
}}"""


@dataclass
class CausalLink:
    cause: str
    effect: str
    mechanism: str
    strength: float
    confidence: float
    direction: str
    conditions: list[str]
    domain: str


@dataclass
class DoQueryResult:
    intervention_variable: str
    intervention_value: str
    target_variable: str
    predicted_effect: str
    direction: str
    magnitude: str
    confidence: float
    causal_path: list[str]
    blocked_confounders: list[str]
    key_assumptions: list[str]
    reasoning: str


@dataclass
class RootCauseResult:
    effect: str
    direct_causes: list[str]
    root_causes: list[str]
    most_actionable_lever: str
    causal_chain: list[str]
    confidence: float


class CausalWorldModel:
    """
    Builds and queries a causal graph of the world.
    Distinguishes observation from intervention (do-calculus).
    """

    def __init__(self):
        self._db_path = Path(config.db_path).parent / "causal.db"

    def initialize(self) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS causal_nodes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    variable TEXT UNIQUE NOT NULL,
                    domain TEXT DEFAULT 'general',
                    description TEXT DEFAULT '',
                    added_at TEXT DEFAULT (datetime('now'))
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS causal_edges (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cause TEXT NOT NULL,
                    effect TEXT NOT NULL,
                    mechanism TEXT DEFAULT '',
                    strength REAL DEFAULT 0.5,
                    confidence REAL DEFAULT 0.5,
                    direction TEXT DEFAULT 'positive',
                    conditions TEXT DEFAULT '[]',
                    domain TEXT DEFAULT 'general',
                    source TEXT DEFAULT '',
                    added_at TEXT DEFAULT (datetime('now')),
                    UNIQUE(cause, effect)
                )
            """)

    def add_causal_link(
        self,
        cause: str,
        effect: str,
        mechanism: str = "",
        strength: float = 0.5,
        confidence: float = 0.5,
        direction: str = "positive",
        conditions: list[str] | None = None,
        domain: str = "general",
        source: str = "",
    ) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO causal_nodes (variable, domain) VALUES (?,?)",
                (cause, domain)
            )
            conn.execute(
                "INSERT OR IGNORE INTO causal_nodes (variable, domain) VALUES (?,?)",
                (effect, domain)
            )
            conn.execute("""
                INSERT INTO causal_edges
                (cause, effect, mechanism, strength, confidence, direction, conditions, domain, source)
                VALUES (?,?,?,?,?,?,?,?,?)
                ON CONFLICT(cause, effect) DO UPDATE SET
                    strength=(strength + excluded.strength)/2,
                    confidence=MAX(confidence, excluded.confidence),
                    mechanism=excluded.mechanism
            """, (
                cause, effect, mechanism, strength, confidence,
                direction, json.dumps(conditions or []), domain, source,
            ))

    async def extract_from_text(self, text: str, source: str = "") -> list[CausalLink]:
        """Extract causal relationships from any text and store them."""
        import anthropic

        client = anthropic.Anthropic(api_key=config.api_key)
        try:
            response = client.messages.create(
                model=config.fast_model,
                max_tokens=1500,
                messages=[{"role": "user", "content": CAUSAL_EXTRACTOR_PROMPT.format(
                    text=text[:3000]
                )}],
            )
            raw = response.content[0].text
            start = raw.find("[")
            end = raw.rfind("]") + 1
            if start < 0 or end <= start:
                return []

            links = json.loads(raw[start:end])
            result: list[CausalLink] = []
            for link in links:
                cl = CausalLink(
                    cause=link.get("cause", ""),
                    effect=link.get("effect", ""),
                    mechanism=link.get("mechanism", ""),
                    strength=float(link.get("strength", 0.5)),
                    confidence=float(link.get("confidence", 0.5)),
                    direction=link.get("direction", "positive"),
                    conditions=link.get("conditions", []),
                    domain=link.get("domain", "general"),
                )
                if cl.cause and cl.effect:
                    self.add_causal_link(
                        cl.cause, cl.effect, cl.mechanism,
                        cl.strength, cl.confidence, cl.direction,
                        cl.conditions, cl.domain, source,
                    )
                    result.append(cl)
            return result
        except Exception:
            return []

    def _get_graph_summary(self, domain: str | None = None, limit: int = 50) -> str:
        """Return causal graph as readable text for prompting."""
        with sqlite3.connect(self._db_path) as conn:
            if domain:
                rows = conn.execute("""
                    SELECT cause, effect, mechanism, strength, direction
                    FROM causal_edges WHERE domain=? ORDER BY strength DESC LIMIT ?
                """, (domain, limit)).fetchall()
            else:
                rows = conn.execute("""
                    SELECT cause, effect, mechanism, strength, direction
                    FROM causal_edges ORDER BY strength DESC LIMIT ?
                """, (limit,)).fetchall()

        if not rows:
            return "No causal relationships stored yet."

        lines = []
        for cause, effect, mechanism, strength, direction in rows:
            arrow = "-->" if direction == "positive" else "-/->"
            mech = f" (via: {mechanism})" if mechanism else ""
            lines.append(f"  {cause} {arrow} {effect}{mech} [strength={strength:.1f}]")
        return "\n".join(lines)

    async def do_query(
        self, intervention_variable: str, intervention_value: str, target_variable: str
    ) -> DoQueryResult:
        """
        Interventional causal query (do-calculus).
        'If I SET X to value, what happens to Y?'
        """
        import anthropic

        graph = self._get_graph_summary()
        client = anthropic.Anthropic(api_key=config.api_key)

        response = client.messages.create(
            model=config.worker_model,
            max_tokens=1500,
            messages=[{"role": "user", "content": DO_QUERY_PROMPT.format(
                causal_graph=graph,
                intervention_variable=intervention_variable,
                intervention_value=intervention_value,
                target_variable=target_variable,
            )}],
        )
        raw = response.content[0].text
        try:
            start = raw.find("{")
            end = raw.rfind("}") + 1
            parsed = json.loads(raw[start:end])
            return DoQueryResult(
                intervention_variable=intervention_variable,
                intervention_value=intervention_value,
                target_variable=target_variable,
                predicted_effect=parsed.get("predicted_effect", ""),
                direction=parsed.get("direction", "unclear"),
                magnitude=parsed.get("magnitude", "unknown"),
                confidence=float(parsed.get("confidence", 0.5)),
                causal_path=parsed.get("causal_path", []),
                blocked_confounders=parsed.get("blocked_confounders", []),
                key_assumptions=parsed.get("key_assumptions", []),
                reasoning=parsed.get("reasoning", ""),
            )
        except Exception:
            return DoQueryResult(
                intervention_variable=intervention_variable,
                intervention_value=intervention_value,
                target_variable=target_variable,
                predicted_effect="Could not determine.",
                direction="unclear",
                magnitude="unknown",
                confidence=0.0,
                causal_path=[],
                blocked_confounders=[],
                key_assumptions=[],
                reasoning=raw[:500],
            )

    async def find_root_causes(self, effect: str) -> RootCauseResult:
        """Trace root causes of an effect through the causal graph."""
        import anthropic

        graph = self._get_graph_summary()
        client = anthropic.Anthropic(api_key=config.api_key)

        response = client.messages.create(
            model=config.worker_model,
            max_tokens=1200,
            messages=[{"role": "user", "content": ROOT_CAUSE_PROMPT.format(
                effect=effect, causal_graph=graph
            )}],
        )
        raw = response.content[0].text
        try:
            start = raw.find("{")
            end = raw.rfind("}") + 1
            parsed = json.loads(raw[start:end])
            return RootCauseResult(
                effect=effect,
                direct_causes=parsed.get("direct_causes", []),
                root_causes=parsed.get("root_causes", []),
                most_actionable_lever=parsed.get("most_actionable_lever", ""),
                causal_chain=parsed.get("causal_chain", []),
                confidence=float(parsed.get("confidence", 0.5)),
            )
        except Exception:
            return RootCauseResult(
                effect=effect,
                direct_causes=[],
                root_causes=[],
                most_actionable_lever="",
                causal_chain=[],
                confidence=0.0,
            )

    def get_graph_stats(self) -> dict:
        try:
            with sqlite3.connect(self._db_path) as conn:
                nodes = conn.execute("SELECT COUNT(*) FROM causal_nodes").fetchone()[0]
                edges = conn.execute("SELECT COUNT(*) FROM causal_edges").fetchone()[0]
                domains = conn.execute(
                    "SELECT DISTINCT domain FROM causal_edges"
                ).fetchall()
            return {
                "nodes": nodes,
                "edges": edges,
                "domains": [d[0] for d in domains],
            }
        except Exception:
            return {"nodes": 0, "edges": 0, "domains": []}


causal_model = CausalWorldModel()
