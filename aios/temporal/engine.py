"""
Temporal Vantage Point Reasoning Engine

Solves problems from multiple future vantage points simultaneously:
- 6 months from now, looking back: what would we wish we'd done?
- 5 years from now: does this decision even matter?
- Worst-case future: what went wrong and when?
- Best-case future: what unlocked everything?

Most AI only thinks about NOW. This engine thinks in time.
"""

from dataclasses import dataclass, field
from datetime import datetime

from ..agents.base import BaseAgent
from ..config import config
from ..system_prompt import MASTER_SYSTEM_PROMPT


TEMPORAL_REASONING_PROMPT = f"""
{MASTER_SYSTEM_PROMPT}

## YOUR ROLE: Temporal Reasoning Agent

You reason about problems across multiple time horizons simultaneously.
You don't just answer the question — you answer it from the future.

TEMPORAL VANTAGE POINTS to consider for every significant decision:

VANTAGE 1 — Tomorrow (1-7 days)
"What will we wish we had thought of today when tomorrow arrives?"
Focus: Immediate dependencies, quick wins, things that will block progress

VANTAGE 2 — This Quarter (90 days)
"Standing at the end of this quarter, did this decision help or hurt?"
Focus: Short-term ROI, resource allocation, momentum

VANTAGE 3 — One Year Out
"A year from now, will we be grateful for this decision?"
Focus: Compounding effects, technical debt, market position

VANTAGE 4 — Five Years Out
"Does this matter at all in 5 years? Or are we optimizing the irrelevant?"
Focus: Structural importance, survivorship bias, what truly compounds

VANTAGE 5 — Worst-Case Future
"Walk me through exactly how this fails. When? Why? What were the early warning signs?"
Focus: Failure mode identification, early warning signals, red flags to watch

VANTAGE 6 — Best-Case Future
"What would have to be true for this to turn out dramatically better than expected?"
Focus: Upside unlocks, optionality, positive black swans

TEMPORAL SYNTHESIS
After examining all vantage points:
- What decisions look different across time horizons?
- Where are the short-term/long-term tradeoffs?
- What must be done NOW because of future constraints?
- What seems urgent but doesn't matter long-term?
- What seems non-urgent but has massive long-term consequences?

This synthesis is the most valuable part. It reveals the decisions that
most people get backwards.
"""

PREMORTEM_PROMPT = f"""
{MASTER_SYSTEM_PROMPT}

## YOUR ROLE: Pre-Mortem Analyst

You specialize in the pre-mortem technique: assume the plan has ALREADY FAILED.
Your job is to explain in detail exactly how and why it failed.

You are reporting from a future where the project failed. What happened?

Structure your pre-mortem:
1. Time of failure: When did it become clear it was failing?
2. Proximate cause: What was the immediate cause of failure?
3. Root causes: What underlying factors made failure inevitable?
4. Early warning signs: What signals were visible earlier but ignored?
5. The decision that sealed the outcome: The single most consequential wrong choice
6. What would have saved it: The minimal change that would have reversed the outcome
7. Who saw it coming: What would a skeptic have said at the start?

Be specific. Use concrete hypothetical details.
The goal is to identify risks so they can be prevented.
"""

FUTURE_BACK_PROMPT = f"""
{MASTER_SYSTEM_PROMPT}

## YOUR ROLE: Future-Back Strategic Reasoner

You practice "future-back" thinking: start from a specific desired future state,
then work backwards to identify the exact decisions and actions needed today.

Given a goal, you:
1. Vividly describe the desired state (5 years out)
2. Identify what would have to be true 3 years out to make that possible
3. Identify what would have to be true 1 year out to be on track
4. Identify what would have to be true 90 days out
5. Identify what must be decided or done THIS WEEK

This reveals the critical path from now to the desired future.
It also reveals whether the desired future is actually achievable given current constraints.
"""


@dataclass
class TemporalVantage:
    horizon: str                # "1_week", "90_days", "1_year", "5_years", "worst_case", "best_case"
    label: str
    analysis: str
    key_insight: str
    action_implications: list[str]


@dataclass
class TemporalAnalysisResult:
    task: str
    vantages: list[TemporalVantage]
    synthesis: str
    short_vs_long_tensions: list[str]
    do_now_because_of_future: list[str]
    seems_urgent_but_isnt: list[str]
    seems_unurgent_but_critical: list[str]
    premortem: str
    overall_temporal_recommendation: str


class TemporalReasoningEngine:
    """
    Multi-horizon temporal analysis engine.
    Makes time-blind decisions impossible.
    """

    def __init__(self):
        self._temporal_agent = _TemporalAgent()
        self._premortem_agent = _PremortemAgent()
        self._future_back_agent = _FutureBackAgent()

    async def analyze(
        self,
        task: str,
        context: str = "",
        depth: str = "standard",   # "quick" | "standard" | "deep"
    ) -> TemporalAnalysisResult:
        # Quick: just synthesis + premortem
        # Standard: all vantages + synthesis
        # Deep: all vantages + premortem + future-back

        horizons = ["tomorrow", "this quarter (90 days)", "one year", "five years"]
        if depth == "deep":
            horizons += ["worst-case future", "best-case future"]

        horizon_analyses = []
        for horizon in horizons:
            result = await self._temporal_agent.run(
                f"TASK/DECISION:\n{task}\n\n"
                f"ANALYZE FROM THIS TEMPORAL VANTAGE POINT: {horizon.upper()}\n\n"
                f"What do you see from here? What should we know?",
                context=context,
            )
            if result.succeeded:
                horizon_analyses.append(TemporalVantage(
                    horizon=horizon.replace(" ", "_").lower(),
                    label=horizon,
                    analysis=result.content,
                    key_insight=result.content[:200],
                    action_implications=self._extract_actions(result.content),
                ))

        # Synthesis
        vantage_text = "\n\n".join([
            f"## {v.label.upper()}\n{v.analysis[:800]}"
            for v in horizon_analyses
        ])
        synthesis_result = await self._temporal_agent.run(
            f"TASK:\n{task}\n\nTEMPORAL ANALYSES:\n{vantage_text}\n\n"
            f"Now synthesize: What tensions exist between time horizons? "
            f"What must be done NOW because of future consequences? "
            f"What seems urgent but doesn't matter long-term? "
            f"What is your overall temporal recommendation?"
        )

        # Pre-mortem (always run for standard+)
        premortem = ""
        if depth in ("standard", "deep"):
            pm_result = await self._premortem_agent.run(
                f"Plan/Decision:\n{task}\n\nConduct a pre-mortem. "
                f"This has already failed. Explain how and why."
            )
            premortem = pm_result.content if pm_result.succeeded else ""

        synthesis = synthesis_result.content if synthesis_result.succeeded else vantage_text[:500]
        tensions = self._extract_tensions(synthesis)

        return TemporalAnalysisResult(
            task=task,
            vantages=horizon_analyses,
            synthesis=synthesis,
            short_vs_long_tensions=tensions,
            do_now_because_of_future=self._extract_do_now(synthesis),
            seems_urgent_but_isnt=self._extract_false_urgency(synthesis),
            seems_unurgent_but_critical=self._extract_underrated(synthesis),
            premortem=premortem,
            overall_temporal_recommendation=self._extract_recommendation(synthesis),
        )

    async def premortem(self, plan: str, context: str = "") -> str:
        result = await self._premortem_agent.run(
            f"Plan:\n{plan}\n\nThis has already failed. Explain exactly how.",
            context=context,
        )
        return result.content if result.succeeded else ""

    async def future_back(self, goal: str, context: str = "") -> str:
        result = await self._future_back_agent.run(
            f"Goal:\n{goal}\n\nWork backwards from the desired future to what must be done this week.",
            context=context,
        )
        return result.content if result.succeeded else ""

    def format_for_inclusion(self, result: TemporalAnalysisResult, brief: bool = True) -> str:
        if brief:
            lines = ["\n## Temporal Analysis\n"]
            if result.do_now_because_of_future:
                lines.append("**Do NOW because of future consequences:**")
                for item in result.do_now_because_of_future[:3]:
                    lines.append(f"  • {item}")
            if result.short_vs_long_tensions:
                lines.append("\n**Short vs. Long-term tensions:**")
                for t in result.short_vs_long_tensions[:2]:
                    lines.append(f"  • {t}")
            if result.premortem:
                lines.append(f"\n**Pre-mortem (how this fails):** {result.premortem[:300]}")
            return "\n".join(lines)

        return (
            f"\n## Multi-Horizon Temporal Analysis\n{result.synthesis}\n\n"
            f"## Pre-Mortem\n{result.premortem}"
        )

    def _extract_actions(self, text: str) -> list[str]:
        lines = text.split("\n")
        return [l.strip("- •").strip() for l in lines if l.strip().startswith(("-", "•", "*")) and len(l) > 20][:3]

    def _extract_tensions(self, text: str) -> list[str]:
        tensions = []
        for line in text.split("\n"):
            if any(w in line.lower() for w in ["tension", "vs", "tradeoff", "trade-off", "short-term", "long-term"]):
                if len(line.strip()) > 20:
                    tensions.append(line.strip()[:150])
        return tensions[:3]

    def _extract_do_now(self, text: str) -> list[str]:
        items = []
        lines = text.split("\n")
        for i, line in enumerate(lines):
            if any(w in line.lower() for w in ["must do now", "do now", "immediately", "this week", "today"]):
                items.append(line.strip()[:150])
        return items[:3]

    def _extract_false_urgency(self, text: str) -> list[str]:
        items = []
        for line in text.split("\n"):
            if any(w in line.lower() for w in ["seems urgent", "doesn't matter long", "not actually urgent"]):
                items.append(line.strip()[:150])
        return items[:2]

    def _extract_underrated(self, text: str) -> list[str]:
        items = []
        for line in text.split("\n"):
            if any(w in line.lower() for w in ["underrated", "non-urgent but", "quiet importance", "overlooked"]):
                items.append(line.strip()[:150])
        return items[:2]

    def _extract_recommendation(self, text: str) -> str:
        lines = text.split("\n")
        for i, line in enumerate(lines):
            if any(w in line.lower() for w in ["recommend", "conclusion", "overall", "bottom line"]):
                for l in lines[i+1:i+4]:
                    if l.strip():
                        return l.strip()[:300]
        return text[-300:].strip() if text else ""


class _TemporalAgent(BaseAgent):
    name = "temporal_reasoner"

    def __init__(self):
        super().__init__()
        self._system_prompt = TEMPORAL_REASONING_PROMPT
        self.model = config.worker_model


class _PremortemAgent(BaseAgent):
    name = "premortem_analyst"

    def __init__(self):
        super().__init__()
        self._system_prompt = PREMORTEM_PROMPT
        self.model = config.worker_model


class _FutureBackAgent(BaseAgent):
    name = "future_back_reasoner"

    def __init__(self):
        super().__init__()
        self._system_prompt = FUTURE_BACK_PROMPT
        self.model = config.worker_model
