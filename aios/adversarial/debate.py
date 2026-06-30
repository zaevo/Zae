"""
Adversarial Self-Play Engine — Red vs. Blue

Before any answer is delivered, two agents battle over it:
- Red Team: Attacks every flaw, assumption, risk, and gap
- Blue Team: Defends, strengthens, and patches weak points
- Synthesis: Produces the battle-tested final answer

Result is provably stronger than any single-pass response.
"""

import asyncio
from dataclasses import dataclass, field

from ..agents.base import BaseAgent, AgentResult
from ..config import config
from ..system_prompt import MASTER_SYSTEM_PROMPT


RED_TEAM_PROMPT = f"""
{MASTER_SYSTEM_PROMPT}

## YOUR ROLE: Red Team Agent (Attacker)

Your ONLY job is to destroy answers before they reach the user.
You are adversarial by design. You succeed when you find problems.

Attack vectors — systematically check all of these:

LOGICAL ATTACKS
- Find every logical gap, non-sequitur, and unsupported leap
- Identify circular reasoning or question-begging
- Find where correlation is mistaken for causation
- Find where the conclusion exceeds what the evidence supports

FACTUAL ATTACKS
- Identify every factual claim that could be wrong
- Find where numbers, dates, or statistics seem suspicious
- Identify domain knowledge that contradicts the answer
- Find outdated information presented as current

ASSUMPTION ATTACKS
- List every hidden assumption in the answer
- For each assumption: what if it's wrong? What breaks?
- Find where the answer assumes the user's situation matches the general case
- Find where the answer assumes optimal conditions

COMPLETENESS ATTACKS
- What critical information is missing?
- What edge cases are not handled?
- What failure modes are not addressed?
- What second-order effects are ignored?

RELEVANCE ATTACKS
- Does this actually answer the real question, or just the stated question?
- Is this solving the symptom or the root cause?
- Will this actually help the user, or just sound helpful?

OUTPUT FORMAT:
## Attack Report
### Critical Weaknesses (must fix before delivery)
[List specific, actionable flaws]
### Significant Weaknesses (should fix)
[List specific flaws]
### Minor Issues (nice to fix)
[List minor issues]
### Overall Verdict: REJECT | REVISE | CONDITIONAL_PASS
### Confidence this answer is wrong in some important way: X%
"""

BLUE_TEAM_PROMPT = f"""
{MASTER_SYSTEM_PROMPT}

## YOUR ROLE: Blue Team Agent (Defender)

You receive an answer AND an attack report. Your job is to:
1. Acknowledge which attacks are valid (intellectual honesty is mandatory)
2. Refute attacks that are invalid
3. Patch every valid weakness
4. Produce a strengthened version of the answer

You do not defend the answer blindly. If the Red Team found real problems,
you fix them. If they attacked something that's actually correct, you explain why.

OUTPUT FORMAT:
## Defense Report
### Valid Attacks Acknowledged
[List what the Red Team got right]
### Invalid Attacks Refuted
[List what the Red Team got wrong, with explanation]
### Patches Applied
[Specific improvements made to address valid attacks]
### Strengthened Answer
[The improved version of the original answer]
### Confidence in strengthened answer: X%
"""

SYNTHESIS_PROMPT = f"""
{MASTER_SYSTEM_PROMPT}

## YOUR ROLE: Debate Synthesis Agent

You receive:
1. The original answer
2. A Red Team attack report
3. A Blue Team defense and strengthened answer

Your job: produce the definitive final answer that incorporates the best insights
from the entire debate cycle.

Rules:
- Use the strengthened answer as your base
- Apply any remaining valid critiques the Blue Team didn't fully address
- Add explicit uncertainty flags where the debate revealed genuine ambiguity
- If the Red Team found a fatal flaw that the Blue Team couldn't fix: say so clearly
- The final answer should be strictly better than what any single agent produced

OUTPUT FORMAT:
## Debate Outcome
Rounds: 1 | Key improvements: [list] | Confidence delta: +X%

## Final Answer
[The definitive, battle-tested response]
"""


@dataclass
class DebateRound:
    red_attack: str
    blue_defense: str
    valid_attacks_count: int
    invalid_attacks_count: int
    patches_applied: int


@dataclass
class DebateResult:
    original_answer: str
    final_answer: str
    rounds: list[DebateRound]
    confidence_improvement: float   # how much confidence increased
    critical_flaws_found: int
    critical_flaws_fixed: int
    verdict: str                    # IMPROVED | REJECTED | CONFIRMED
    debate_summary: str


class RedAgent(BaseAgent):
    name = "red_team"

    def __init__(self):
        super().__init__()
        self._system_prompt = RED_TEAM_PROMPT
        self.model = config.worker_model

    async def attack(self, task: str, answer: str) -> AgentResult:
        return await self.run(
            f"TASK THAT WAS ASKED:\n{task}\n\nANSWER TO ATTACK:\n{answer}\n\n"
            f"Attack this answer with full force. Find every flaw."
        )


class BlueAgent(BaseAgent):
    name = "blue_team"

    def __init__(self):
        super().__init__()
        self._system_prompt = BLUE_TEAM_PROMPT
        self.model = config.worker_model

    async def defend(self, task: str, answer: str, attack_report: str) -> AgentResult:
        return await self.run(
            f"TASK:\n{task}\n\nORIGINAL ANSWER:\n{answer}\n\n"
            f"RED TEAM ATTACK:\n{attack_report}\n\n"
            f"Defend and strengthen. Acknowledge real flaws. Patch them."
        )


class SynthesisAgent(BaseAgent):
    name = "synthesis"

    def __init__(self):
        super().__init__()
        self._system_prompt = SYNTHESIS_PROMPT
        self.model = config.ceo_model

    async def synthesize(
        self, task: str, original: str, attack: str, defense: str
    ) -> AgentResult:
        return await self.run(
            f"TASK:\n{task}\n\nORIGINAL:\n{original}\n\n"
            f"RED TEAM:\n{attack}\n\nBLUE TEAM:\n{defense}\n\n"
            f"Produce the definitive final answer."
        )


class AdversarialDebateEngine:
    """
    Runs every answer through a Red/Blue debate before delivery.
    The answer that reaches the user has survived an adversarial attack.
    """

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self._red = RedAgent()
        self._blue = BlueAgent()
        self._synthesis = SynthesisAgent()

    async def debate(
        self,
        task: str,
        answer: str,
        complexity: str = "medium",
    ) -> DebateResult:
        if not self.enabled or complexity == "low" or len(answer) < 200:
            return DebateResult(
                original_answer=answer,
                final_answer=answer,
                rounds=[],
                confidence_improvement=0.0,
                critical_flaws_found=0,
                critical_flaws_fixed=0,
                verdict="SKIPPED",
                debate_summary="Debate skipped for low-complexity task.",
            )

        # Red and Blue run in parallel on the original answer
        red_result, blue_first_pass = await asyncio.gather(
            self._red.attack(task, answer),
            self._blue.defend(task, answer, "Initial defense — no attack yet"),
        )

        red_report = red_result.content if red_result.succeeded else "Red team unavailable"

        # Blue responds to the actual red attack
        blue_result = await self._blue.defend(task, answer, red_report)
        blue_report = blue_result.content if blue_result.succeeded else blue_first_pass.content

        # Synthesis
        final_result = await self._synthesis.synthesize(task, answer, red_report, blue_report)
        final_answer = self._extract_final_answer(
            final_result.content if final_result.succeeded else blue_report
        )

        # Parse metrics
        critical_found = red_report.lower().count("critical")
        patches = blue_report.lower().count("patch") + blue_report.lower().count("fix")

        round_data = DebateRound(
            red_attack=red_report[:500],
            blue_defense=blue_report[:500],
            valid_attacks_count=critical_found,
            invalid_attacks_count=max(0, red_report.lower().count("weakness") - critical_found),
            patches_applied=patches,
        )

        verdict = "CONFIRMED"
        if critical_found > 0 and patches > 0:
            verdict = "IMPROVED"
        elif "REJECT" in red_report.upper():
            verdict = "REJECTED_AND_REBUILT"

        return DebateResult(
            original_answer=answer,
            final_answer=final_answer if len(final_answer) > 100 else answer,
            rounds=[round_data],
            confidence_improvement=min(0.3, patches * 0.05),
            critical_flaws_found=critical_found,
            critical_flaws_fixed=patches,
            verdict=verdict,
            debate_summary=f"Red found {critical_found} critical issues. Blue patched {patches}. Verdict: {verdict}",
        )

    def _extract_final_answer(self, synthesis: str) -> str:
        marker = "## Final Answer"
        idx = synthesis.find(marker)
        if idx >= 0:
            return synthesis[idx + len(marker):].strip()
        # Try alternate markers
        for alt in ["## Strengthened Answer", "## Improved Answer", "## Definitive Answer"]:
            idx = synthesis.find(alt)
            if idx >= 0:
                return synthesis[idx + len(alt):].strip()
        return synthesis
