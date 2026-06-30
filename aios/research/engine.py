"""
Research Engine
Multi-source evidence synthesis with source reliability ranking and confidence scoring.
"""

from dataclasses import dataclass, field
from typing import Any

from ..agents.specializations import ResearcherAgent, FactCheckerAgent, AnalystAgent
from ..intelligence.reasoning import build_research_protocol, extract_confidence


@dataclass
class Source:
    content: str
    source_type: str       # "primary", "secondary", "anecdotal"
    reliability: float     # 0–1
    recency: str           # "current", "recent", "dated"
    url: str | None = None
    title: str | None = None


@dataclass
class ResearchFinding:
    claim: str
    confidence: float
    evidence: list[str]
    sources: list[Source]
    contested: bool = False
    flag: str = ""  # [VERIFIED], [UNVERIFIED], [CONTESTED]


@dataclass
class ResearchResult:
    question: str
    executive_summary: str
    high_confidence_findings: list[ResearchFinding]
    contested_findings: list[ResearchFinding]
    unknowns: list[str]
    overall_confidence: float
    recommendation: str
    raw_output: str


class ResearchEngine:
    """
    Deep research engine that enforces multi-source evidence gathering,
    conflict detection, and confidence-weighted synthesis.
    """

    def __init__(self):
        self._researcher = ResearcherAgent()
        self._fact_checker = FactCheckerAgent()
        self._analyst = AnalystAgent()

    async def research(self, question: str, context: str = "", depth: str = "standard") -> ResearchResult:
        """
        depth: "quick" | "standard" | "deep"
        """
        protocol = build_research_protocol(question)

        # Run researcher
        research_result = await self._researcher.run(protocol, context=context)

        # Fact-check for standard+ depth
        fact_check_output = ""
        if depth in ("standard", "deep") and research_result.succeeded:
            fc_result = await self._fact_checker.verify(
                research_result.content[:5000], context=context
            )
            fact_check_output = fc_result.content if fc_result.succeeded else ""

        # Analyst synthesis for deep research
        analyst_output = ""
        if depth == "deep" and research_result.succeeded:
            analyst_prompt = f"""
Synthesize and analyze these research findings:

RESEARCH:
{research_result.content[:4000]}

FACT CHECK:
{fact_check_output[:2000]}

Produce:
1. Pattern analysis across findings
2. Conflicting evidence assessment
3. Confidence-weighted conclusions
4. Second-order implications
"""
            analyst_result = await self._analyst.run(analyst_prompt, context=context)
            analyst_output = analyst_result.content if analyst_result.succeeded else ""

        # Assemble final output
        raw = research_result.content
        if fact_check_output:
            raw += f"\n\n---\n**Fact Check:**\n{fact_check_output}"
        if analyst_output:
            raw += f"\n\n---\n**Analysis:**\n{analyst_output}"

        confidence = extract_confidence(raw)
        summary = self._extract_summary(raw)

        return ResearchResult(
            question=question,
            executive_summary=summary,
            high_confidence_findings=[],
            contested_findings=[],
            unknowns=[],
            overall_confidence=confidence,
            recommendation=self._extract_recommendation(raw),
            raw_output=raw,
        )

    def _extract_summary(self, text: str) -> str:
        """Extract or generate a 2-3 sentence summary."""
        lines = text.split("\n")
        for i, line in enumerate(lines):
            if any(marker in line.lower() for marker in ["summary", "bottom line", "key finding", "executive"]):
                summary_lines = []
                for l in lines[i+1:i+6]:
                    if l.strip() and not l.startswith("#"):
                        summary_lines.append(l.strip())
                if summary_lines:
                    return " ".join(summary_lines[:3])
        # Fallback: first substantial paragraph
        for line in lines:
            if len(line) > 100:
                return line[:300]
        return text[:300]

    def _extract_recommendation(self, text: str) -> str:
        lines = text.split("\n")
        for i, line in enumerate(lines):
            if any(marker in line.lower() for marker in ["recommend", "next step", "conclusion", "action"]):
                for l in lines[i+1:i+4]:
                    if l.strip():
                        return l.strip()
        return ""
