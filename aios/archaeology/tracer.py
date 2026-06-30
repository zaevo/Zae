"""
Decision Archaeology

When something goes wrong, trace the full reasoning chain backward to find
exactly where and why the decision diverged from reality.

"The chain of causation is clearer in hindsight than in prospect." — Taleb
"""

import json
from dataclasses import dataclass, field
from datetime import datetime

from ..agents.base import BaseAgent
from ..config import config
from ..memory.manager import memory
from ..memory.types import MemoryType
from ..system_prompt import MASTER_SYSTEM_PROMPT


ARCHAEOLOGY_PROMPT = f"""
{MASTER_SYSTEM_PROMPT}

## YOUR ROLE: Decision Archaeologist

You investigate why decisions went wrong by tracing back through the reasoning chain.

Given: a description of what went wrong and a history of related decisions and facts.

Your analysis:

1. TIMELINE RECONSTRUCTION
   Build a chronological timeline of decisions, assumptions, and facts.
   Mark when each piece of information was known vs. when it became relevant.

2. DECISION POINT IDENTIFICATION
   Identify the specific decision points where the outcome was determined.
   Which single decision, if made differently, would have changed the outcome?

3. INFORMATION ANALYSIS
   - What was known at decision time vs. what should have been known?
   - What was unknown that turned out to be critical?
   - Were there warning signs that were ignored or not seen?

4. ROOT CAUSE
   Distinguish between:
   - Bad luck (couldn't have known)
   - Bad process (should have checked something)
   - Bad reasoning (had the information but concluded wrong)
   - Bad assumptions (built on false premise)

5. PREVENTION PROTOCOL
   Given the root cause, what specific change would prevent this category of error?

Output format:
## Decision Archaeology Report

### Timeline
[Chronological reconstruction]

### Critical Decision Point
[The specific moment where the outcome was determined]

### Root Cause
[What actually caused the failure]

### Warning Signs Available at the Time
[What was visible but not acted on]

### Prevention Protocol
[Specific change to prevent this class of error]
"""


@dataclass
class ArchaeologyFinding:
    critical_decision_point: str
    root_cause: str
    root_cause_type: str         # bad_luck | bad_process | bad_reasoning | bad_assumption
    warning_signs_missed: list[str]
    prevention_protocol: str
    timeline: list[dict]
    confidence: float


class DecisionArchaeologist:
    """
    Traces failed decisions back to their root cause.
    Builds institutional memory of how things go wrong.
    """

    def __init__(self):
        self._agent = _ArchaeologyAgent()

    async def investigate(
        self,
        what_went_wrong: str,
        project_id: str | None = None,
        context: str = "",
    ) -> ArchaeologyFinding:
        # Pull relevant memory
        mem_context = memory.retrieve_context_for_task(
            what_went_wrong, project_id=project_id
        )
        combined_context = f"{context}\n\n{mem_context}".strip()

        result = await self._agent.run(
            f"WHAT WENT WRONG:\n{what_went_wrong}\n\n"
            f"HISTORICAL CONTEXT:\n{combined_context[:3000]}\n\n"
            f"Conduct a full decision archaeology investigation.",
        )

        if not result.succeeded:
            return ArchaeologyFinding(
                critical_decision_point="Investigation failed",
                root_cause="", root_cause_type="unknown",
                warning_signs_missed=[], prevention_protocol="",
                timeline=[], confidence=0.0,
            )

        return ArchaeologyFinding(
            critical_decision_point=self._extract_section(result.content, "Critical Decision Point"),
            root_cause=self._extract_section(result.content, "Root Cause"),
            root_cause_type=self._classify_root_cause(result.content),
            warning_signs_missed=self._extract_list(result.content, "Warning Signs"),
            prevention_protocol=self._extract_section(result.content, "Prevention Protocol"),
            timeline=self._extract_timeline(result.content),
            confidence=0.7,
        )

    def _extract_section(self, text: str, section: str) -> str:
        idx = text.find(f"### {section}")
        if idx < 0:
            idx = text.find(section)
        if idx < 0:
            return ""
        start = text.find("\n", idx) + 1
        end = text.find("\n###", start)
        return text[start:end if end > 0 else start + 500].strip()

    def _extract_list(self, text: str, section: str) -> list[str]:
        section_text = self._extract_section(text, section)
        lines = section_text.split("\n")
        return [l.strip("- •*").strip() for l in lines if l.strip().startswith(("-", "•", "*"))][:5]

    def _extract_timeline(self, text: str) -> list[dict]:
        section = self._extract_section(text, "Timeline")
        items = []
        for line in section.split("\n"):
            if line.strip():
                items.append({"event": line.strip()[:150]})
        return items[:10]

    def _classify_root_cause(self, text: str) -> str:
        text_lower = text.lower()
        if "couldn't have known" in text_lower or "bad luck" in text_lower:
            return "bad_luck"
        if "should have checked" in text_lower or "process" in text_lower:
            return "bad_process"
        if "false premise" in text_lower or "assumption" in text_lower:
            return "bad_assumption"
        return "bad_reasoning"


class _ArchaeologyAgent(BaseAgent):
    name = "decision_archaeologist"

    def __init__(self):
        super().__init__()
        self._system_prompt = ARCHAEOLOGY_PROMPT
        self.model = config.worker_model


archaeologist = DecisionArchaeologist()
