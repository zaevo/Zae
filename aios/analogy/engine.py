"""
Analogical Leap Engine
Finds deep structural isomorphisms between completely different domains.
Most breakthroughs in history (DNA helix → spiral staircase, evolution → economics)
came from analogical transfer. This engine does it systematically.
"""

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from ..config import config

ANALOGY_FINDER_PROMPT = """You are an Analogical Leap Engine. Your superpower is finding
DEEP STRUCTURAL SIMILARITIES between completely different domains.

Not surface similarities — structural ones. The same underlying pattern expressed in different materials.

Problem/Concept: {problem}
Domain of the problem: {source_domain}

Search these domains for structural isomorphisms:
{target_domains}

For each analogy you find, ask:
"Does this domain have the SAME STRUCTURE as the problem — the same relationships,
constraints, and dynamics — even though the surface looks completely different?"

Classic examples of great analogies:
- Evolution ↔ Economics (selection pressure = competition, fitness = profit, mutation = innovation)
- Fluid dynamics ↔ Electrical circuits (flow = current, pressure = voltage, resistance = resistance)
- Immune system ↔ Software security (antibodies = signatures, memory cells = threat intelligence)
- Neural networks ↔ Corporate hierarchy (layers = management levels, weights = influence)

Return JSON array:
[
  {{
    "source_domain": "the problem domain",
    "target_domain": "the domain where you found the analogy",
    "structural_mapping": {{
      "problem_element": "analogous_element",
      "constraint_in_source": "constraint_in_target",
      "dynamic_in_source": "dynamic_in_target"
    }},
    "insight": "The key insight this analogy reveals about the original problem",
    "solution_transfer": "How a solution from the target domain could be adapted",
    "strength": 0.85,
    "surprising_factor": 0.9,
    "historical_precedent": "Has this analogy been used before? Where?"
  }}
]

Find 2-5 analogies. Prefer SURPRISING ones with HIGH structural validity."""

SOLUTION_TRANSFER_PROMPT = """You found a powerful structural analogy. Now transfer the solution.

Original Problem: {problem}
Analogous Domain: {target_domain}

Structural Mapping:
{mapping}

Known solutions in the {target_domain} domain:
Think about what approaches are known to work for problems with this structure in {target_domain}.

Now adapt those solutions to the original problem:
1. What is the direct analog of each known solution?
2. What needs to be modified for the transfer to work?
3. What new approach does this analogy suggest that nobody in {source_domain} has tried?

Return your proposed solution approach directly."""


@dataclass
class Analogy:
    source_domain: str
    target_domain: str
    structural_mapping: dict[str, str]
    insight: str
    solution_transfer: str
    strength: float
    surprising_factor: float
    historical_precedent: str
    analogy_id: int = 0
    discovered_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class AnalogyResult:
    problem: str
    analogies: list[Analogy]
    best_analogy: Analogy | None
    transferred_solution: str


class AnalogicalLeapEngine:
    """
    Finds structural isomorphisms across domains to generate
    novel solutions by analogy transfer.
    """

    DEFAULT_TARGET_DOMAINS = [
        "biology/evolution", "physics/thermodynamics", "economics/markets",
        "military strategy", "ecology/ecosystems", "fluid dynamics",
        "electrical engineering", "game theory", "architecture",
        "music theory", "linguistics", "urban planning", "immunology",
        "sports strategy", "geology/tectonic plates",
    ]

    def __init__(self):
        self._db_path = Path(config.db_path).parent / "analogy.db"

    def initialize(self) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS analogies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_domain TEXT NOT NULL,
                    target_domain TEXT NOT NULL,
                    problem TEXT NOT NULL,
                    structural_mapping TEXT DEFAULT '{}',
                    insight TEXT DEFAULT '',
                    solution_transfer TEXT DEFAULT '',
                    transferred_solution TEXT DEFAULT '',
                    strength REAL DEFAULT 0.5,
                    surprising_factor REAL DEFAULT 0.5,
                    historical_precedent TEXT DEFAULT '',
                    times_used INTEGER DEFAULT 0,
                    discovered_at TEXT DEFAULT (datetime('now'))
                )
            """)

    async def find_analogies(
        self,
        problem: str,
        source_domain: str = "general",
        target_domains: list[str] | None = None,
        n_domains: int = 8,
    ) -> AnalogyResult:
        """Find structural analogies for a problem across multiple domains."""
        import anthropic

        domains = target_domains or self.DEFAULT_TARGET_DOMAINS[:n_domains]
        domains_str = "\n".join(f"  - {d}" for d in domains)

        client = anthropic.Anthropic(api_key=config.api_key)

        try:
            response = client.messages.create(
                model=config.worker_model,
                max_tokens=3000,
                messages=[{"role": "user", "content": ANALOGY_FINDER_PROMPT.format(
                    problem=problem[:2000],
                    source_domain=source_domain,
                    target_domains=domains_str,
                )}],
            )
            raw = response.content[0].text
            start = raw.find("[")
            end = raw.rfind("]") + 1
            if start < 0 or end <= start:
                return AnalogyResult(problem=problem, analogies=[], best_analogy=None, transferred_solution="")

            raw_analogies = json.loads(raw[start:end])
            analogies: list[Analogy] = []

            with sqlite3.connect(self._db_path) as conn:
                for ra in raw_analogies:
                    cursor = conn.execute("""
                        INSERT INTO analogies
                        (source_domain, target_domain, problem, structural_mapping,
                         insight, solution_transfer, strength, surprising_factor, historical_precedent)
                        VALUES (?,?,?,?,?,?,?,?,?)
                    """, (
                        ra.get("source_domain", source_domain),
                        ra.get("target_domain", ""),
                        problem[:300],
                        json.dumps(ra.get("structural_mapping", {})),
                        ra.get("insight", ""),
                        ra.get("solution_transfer", ""),
                        float(ra.get("strength", 0.5)),
                        float(ra.get("surprising_factor", 0.5)),
                        ra.get("historical_precedent", ""),
                    ))
                    analogies.append(Analogy(
                        source_domain=ra.get("source_domain", source_domain),
                        target_domain=ra.get("target_domain", ""),
                        structural_mapping=ra.get("structural_mapping", {}),
                        insight=ra.get("insight", ""),
                        solution_transfer=ra.get("solution_transfer", ""),
                        strength=float(ra.get("strength", 0.5)),
                        surprising_factor=float(ra.get("surprising_factor", 0.5)),
                        historical_precedent=ra.get("historical_precedent", ""),
                        analogy_id=cursor.lastrowid,
                    ))

            # Sort by strength × surprise (most novel + valid analogy first)
            analogies.sort(key=lambda a: a.strength * a.surprising_factor, reverse=True)
            best = analogies[0] if analogies else None

            # Generate a full transferred solution for the best analogy
            transferred = ""
            if best:
                transferred = await self._transfer_solution(problem, source_domain, best)

            return AnalogyResult(
                problem=problem,
                analogies=analogies,
                best_analogy=best,
                transferred_solution=transferred,
            )
        except Exception:
            return AnalogyResult(problem=problem, analogies=[], best_analogy=None, transferred_solution="")

    async def _transfer_solution(
        self, problem: str, source_domain: str, analogy: Analogy
    ) -> str:
        """Generate a full solution by transferring approaches from the analogous domain."""
        import anthropic

        client = anthropic.Anthropic(api_key=config.api_key)
        try:
            response = client.messages.create(
                model=config.worker_model,
                max_tokens=2000,
                messages=[{"role": "user", "content": SOLUTION_TRANSFER_PROMPT.format(
                    problem=problem[:1500],
                    target_domain=analogy.target_domain,
                    mapping=json.dumps(analogy.structural_mapping, indent=2),
                    source_domain=source_domain,
                )}],
            )
            solution = response.content[0].text.strip()

            # Store the transferred solution
            with sqlite3.connect(self._db_path) as conn:
                conn.execute(
                    "UPDATE analogies SET transferred_solution=? WHERE id=?",
                    (solution[:3000], analogy.analogy_id)
                )
            return solution
        except Exception:
            return ""

    def format_analogy_result(self, result: AnalogyResult) -> str:
        if not result.analogies:
            return "No structural analogies found for this problem."

        lines = [f"Found {len(result.analogies)} analogies for: {result.problem[:100]}"]

        for i, a in enumerate(result.analogies[:3], 1):
            lines.append(f"\n{'─'*50}")
            lines.append(f"Analogy {i}: {a.source_domain} ↔ {a.target_domain}")
            lines.append(f"  Strength: {a.strength:.0%} | Surprise: {a.surprising_factor:.0%}")
            lines.append(f"  Insight: {a.insight}")
            if a.historical_precedent:
                lines.append(f"  Precedent: {a.historical_precedent}")
            if a.structural_mapping:
                lines.append("  Structure:")
                for k, v in list(a.structural_mapping.items())[:3]:
                    lines.append(f"    {k} → {v}")

        if result.transferred_solution:
            lines.append(f"\n{'━'*50}")
            lines.append("Transferred Solution:")
            lines.append(result.transferred_solution[:1000])

        return "\n".join(lines)

    def get_library_stats(self) -> dict:
        try:
            with sqlite3.connect(self._db_path) as conn:
                total = conn.execute("SELECT COUNT(*) FROM analogies").fetchone()[0]
                domains = conn.execute(
                    "SELECT DISTINCT target_domain FROM analogies ORDER BY target_domain"
                ).fetchall()
            return {
                "total_analogies": total,
                "domains_explored": [d[0] for d in domains],
            }
        except Exception:
            return {"total_analogies": 0, "domains_explored": []}


analogy_engine = AnalogicalLeapEngine()
