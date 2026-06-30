"""
Meta-Cognitive Monitor

Watches AIOS's own reasoning in real-time and can interrupt mid-stream
if it detects the system is going down a wrong path.

The AI equivalent of "wait, let me stop and rethink this."
"""

from dataclasses import dataclass, field
from ..agents.base import BaseAgent
from ..config import config
from ..system_prompt import MASTER_SYSTEM_PROMPT


METACOGNITION_PROMPT = f"""
{MASTER_SYSTEM_PROMPT}

## YOUR ROLE: Meta-Cognitive Monitor

You review in-progress reasoning and flag problems BEFORE they reach the output.

You are the voice that says "wait — this is going wrong."

INTERRUPT CONDITIONS — raise a flag if you detect:

REASONING FAILURES
- Circular reasoning (conclusion assumed in premise)
- Anchoring to the first plausible answer without exploring alternatives
- Availability bias (using what's easy to recall vs. what's actually relevant)
- Confirmation bias (seeking evidence that supports the first answer)
- Sunk cost reasoning (defending a bad approach because effort was spent)

SCOPE FAILURES
- Answering the literal question but missing the real goal
- Solving a symptom instead of the root cause
- Over-engineering a simple problem
- Under-engineering a complex problem

KNOWLEDGE FAILURES
- Stating something with confidence that could plausibly be wrong
- Missing a domain that's clearly relevant to the answer
- Making recommendations outside demonstrated expertise

STRUCTURAL FAILURES
- The answer is getting so long it's losing the user
- Critical information is buried
- The conclusion contradicts something stated earlier

Output:
{{
  "interrupt": true/false,
  "severity": "CRITICAL | HIGH | MEDIUM",
  "failure_type": "reasoning | scope | knowledge | structural",
  "description": "Exactly what's going wrong",
  "correction": "What should happen instead",
  "confidence_in_interrupt": 0.85
}}

Only interrupt if you're highly confident (>0.75) something is genuinely wrong.
False positives waste time. False negatives let bad answers through.
"""


@dataclass
class MetaCognitiveAlert:
    should_interrupt: bool
    severity: str               # CRITICAL | HIGH | MEDIUM
    failure_type: str
    description: str
    correction: str
    confidence: float


class MetaCognitiveMonitor:
    """
    Reviews reasoning mid-stream and flags problems before delivery.
    """

    CONFIDENCE_THRESHOLD = 0.75

    def __init__(self):
        self._monitor_agent = _MetaCogMonitorAgent()

    async def review(self, task: str, reasoning_so_far: str) -> MetaCognitiveAlert:
        result = await self._monitor_agent.run(
            f"TASK:\n{task[:500]}\n\n"
            f"REASONING IN PROGRESS:\n{reasoning_so_far[:2000]}\n\n"
            f"Should this reasoning be interrupted? What (if anything) is going wrong?"
        )
        if not result.succeeded:
            return MetaCognitiveAlert(
                should_interrupt=False, severity="LOW",
                failure_type="none", description="Monitor unavailable",
                correction="", confidence=0.0,
            )

        import json
        try:
            content = result.content
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0:
                data = json.loads(content[start:end])
                confidence = float(data.get("confidence_in_interrupt", 0.0))
                should_interrupt = (
                    data.get("interrupt", False) and
                    confidence >= self.CONFIDENCE_THRESHOLD
                )
                return MetaCognitiveAlert(
                    should_interrupt=should_interrupt,
                    severity=data.get("severity", "MEDIUM"),
                    failure_type=data.get("failure_type", "unknown"),
                    description=data.get("description", ""),
                    correction=data.get("correction", ""),
                    confidence=confidence,
                )
        except (json.JSONDecodeError, ValueError):
            pass

        return MetaCognitiveAlert(
            should_interrupt=False, severity="LOW",
            failure_type="parse_error", description="Could not parse monitor output",
            correction="", confidence=0.0,
        )

    async def check_final_output(self, task: str, output: str) -> MetaCognitiveAlert:
        """Final check before delivery — last chance to catch errors."""
        return await self.review(task, f"FINAL OUTPUT:\n{output}")


class _MetaCogMonitorAgent(BaseAgent):
    name = "metacognition_monitor"

    def __init__(self):
        super().__init__()
        self._system_prompt = METACOGNITION_PROMPT
        self.model = config.fast_model


metacog_monitor = MetaCognitiveMonitor()
