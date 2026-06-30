"""
Mental Simulation Engine
Before executing any task, internally simulates N candidate approaches,
models their likely outcomes, and selects the path with the best expected result.
Like AlphaGo's tree search — but for language and reasoning.
"""

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from ..config import config

SIMULATION_PROMPT = """You are a Mental Simulation Engine. Your job is to think ahead.

Given a task and context, generate {n_paths} distinct candidate approaches.
For each approach, mentally simulate what would happen if you took that path:
- What would the output look like?
- What could go wrong?
- What assumptions does it rely on?
- How confident are you it achieves the goal?

Return a JSON array of simulation objects:
[
  {{
    "approach_id": 1,
    "approach_name": "Short name",
    "approach_description": "How this approach works",
    "simulated_outcome": "What the output would look like and why",
    "risks": ["risk1", "risk2"],
    "assumptions": ["assumption1"],
    "confidence": 0.85,
    "expected_quality": 0.80,
    "reasoning": "Why this is or isn't the best path"
  }}
]

Task: {task}
Context: {context}

Think carefully. Simulate each path as if you were actually running it. Be honest about risks."""

SELECTOR_PROMPT = """You have simulated {n} candidate approaches to a task.
Review all simulations and select the BEST approach considering:
1. Highest expected quality × confidence
2. Fewest critical risks
3. Most realistic assumptions

Simulations:
{simulations}

Return JSON:
{{
  "selected_approach_id": 1,
  "rationale": "Why this is the best path",
  "execution_guidance": "Key things to do/avoid when executing this approach",
  "merged_risks": ["risk to watch for"],
  "confidence": 0.85
}}"""


@dataclass
class SimulatedPath:
    approach_id: int
    approach_name: str
    approach_description: str
    simulated_outcome: str
    risks: list[str]
    assumptions: list[str]
    confidence: float
    expected_quality: float
    reasoning: str


@dataclass
class SimulationResult:
    task: str
    paths: list[SimulatedPath]
    selected_path: SimulatedPath
    execution_guidance: str
    merged_risks: list[str]
    overall_confidence: float
    simulated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


class MentalSimulationEngine:
    """
    Runs forward simulation of N approaches before executing any task.
    Selects the path with best expected outcome.
    """

    N_PATHS = 3

    def __init__(self):
        self._db_path = Path(config.db_path).parent / "simulation.db"

    def initialize(self) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS simulations (
                    id TEXT PRIMARY KEY,
                    task TEXT NOT NULL,
                    selected_approach TEXT,
                    confidence REAL,
                    execution_guidance TEXT,
                    created_at TEXT DEFAULT (datetime('now'))
                )
            """)

    async def simulate(self, task: str, context: str = "", n_paths: int | None = None) -> SimulationResult:
        """Simulate N approaches and return the best one with execution guidance."""
        import anthropic
        import uuid

        n = n_paths or self.N_PATHS
        client = anthropic.Anthropic(api_key=config.anthropic_api_key)

        # Step 1: Generate N simulated paths
        sim_prompt = SIMULATION_PROMPT.format(
            n_paths=n,
            task=task[:2000],
            context=context[:1000] if context else "No prior context.",
        )

        sim_response = client.messages.create(
            model=config.worker_model,
            max_tokens=3000,
            messages=[{"role": "user", "content": sim_prompt}],
        )
        sim_text = sim_response.content[0].text

        paths: list[SimulatedPath] = []
        try:
            start = sim_text.find("[")
            end = sim_text.rfind("]") + 1
            if start >= 0 and end > start:
                raw_paths = json.loads(sim_text[start:end])
                for p in raw_paths:
                    paths.append(SimulatedPath(
                        approach_id=p.get("approach_id", 0),
                        approach_name=p.get("approach_name", ""),
                        approach_description=p.get("approach_description", ""),
                        simulated_outcome=p.get("simulated_outcome", ""),
                        risks=p.get("risks", []),
                        assumptions=p.get("assumptions", []),
                        confidence=float(p.get("confidence", 0.5)),
                        expected_quality=float(p.get("expected_quality", 0.5)),
                        reasoning=p.get("reasoning", ""),
                    ))
        except Exception:
            pass

        if not paths:
            # Fallback: single default path
            paths = [SimulatedPath(
                approach_id=1,
                approach_name="Direct approach",
                approach_description="Execute the task directly",
                simulated_outcome="Standard output",
                risks=[],
                assumptions=[],
                confidence=0.7,
                expected_quality=0.7,
                reasoning="Default path",
            )]

        # Step 2: Select the best path
        sim_summaries = json.dumps([{
            "approach_id": p.approach_id,
            "name": p.approach_name,
            "confidence": p.confidence,
            "expected_quality": p.expected_quality,
            "risks": p.risks[:3],
            "reasoning": p.reasoning[:300],
        } for p in paths], indent=2)

        sel_response = client.messages.create(
            model=config.fast_model,
            max_tokens=800,
            messages=[{"role": "user", "content": SELECTOR_PROMPT.format(
                n=len(paths), simulations=sim_summaries
            )}],
        )
        sel_text = sel_response.content[0].text

        selected = paths[0]
        execution_guidance = ""
        merged_risks: list[str] = []
        overall_confidence = paths[0].confidence

        try:
            start = sel_text.find("{")
            end = sel_text.rfind("}") + 1
            if start >= 0 and end > start:
                sel = json.loads(sel_text[start:end])
                sel_id = sel.get("selected_approach_id", 1)
                for p in paths:
                    if p.approach_id == sel_id:
                        selected = p
                        break
                execution_guidance = sel.get("execution_guidance", "")
                merged_risks = sel.get("merged_risks", [])
                overall_confidence = float(sel.get("confidence", selected.confidence))
        except Exception:
            pass

        result = SimulationResult(
            task=task,
            paths=paths,
            selected_path=selected,
            execution_guidance=execution_guidance,
            merged_risks=merged_risks,
            overall_confidence=overall_confidence,
        )

        # Persist simulation record
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO simulations VALUES (?,?,?,?,?,?)",
                    (
                        str(uuid.uuid4()),
                        task[:300],
                        selected.approach_name,
                        overall_confidence,
                        execution_guidance[:500],
                        datetime.utcnow().isoformat(),
                    ),
                )
        except Exception:
            pass

        return result

    def format_simulation(self, result: SimulationResult) -> str:
        lines = [
            f"Selected path: {result.selected_path.approach_name} (confidence: {result.overall_confidence:.0%})",
            f"Approach: {result.selected_path.approach_description}",
        ]
        if result.execution_guidance:
            lines.append(f"Guidance: {result.execution_guidance}")
        if result.merged_risks:
            lines.append("Risks: " + "; ".join(result.merged_risks[:3]))
        return "\n".join(lines)


simulation_engine = MentalSimulationEngine()
