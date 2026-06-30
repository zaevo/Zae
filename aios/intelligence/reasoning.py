"""
Intelligence layer: reasoning protocols, confidence estimation, self-critique,
and alternative solution generation.
"""

import json
import re
from dataclasses import dataclass
from typing import Any


@dataclass
class ReasoningResult:
    primary_answer: str
    alternatives: list[str]
    confidence: float
    assumptions: list[str]
    uncertainties: list[str]
    reasoning_chain: list[str]
    flags: list[str]   # [~], [?], [HYPOTHESIS] markers found


@dataclass
class CritiqueResult:
    original: str
    issues: list[str]
    improvements: list[str]
    revised: str
    quality_score: float       # 0–100
    passed: bool


def extract_confidence(text: str) -> float:
    """Parse confidence mentions from agent output."""
    patterns = [
        r"confidence[:\s]+(\d+(?:\.\d+)?)[%]",
        r"(\d+(?:\.\d+)?)[%]\s+confident",
        r"confidence[:\s]+(0\.\d+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = float(match.group(1))
            return value / 100.0 if value > 1.0 else value
    # Infer from hedging language
    if any(w in text.lower() for w in ["certain", "definitively", "confirmed"]):
        return 0.92
    if any(w in text.lower() for w in ["likely", "probably", "appears"]):
        return 0.72
    if any(w in text.lower() for w in ["possibly", "might", "uncertain", "unclear"]):
        return 0.45
    return 0.75  # default moderate confidence


def extract_flags(text: str) -> list[str]:
    """Extract uncertainty flags from agent output."""
    flags = []
    flag_patterns = {
        "[~]": "moderate uncertainty",
        "[?]": "high uncertainty",
        "[HYPOTHESIS]": "speculative",
        "[VERIFIED]": "verified claim",
        "[UNVERIFIED]": "unverified claim",
        "[CONTESTED]": "contested claim",
        "[HALLUCINATION_RISK]": "hallucination risk",
    }
    for marker, description in flag_patterns.items():
        if marker in text:
            flags.append(f"{marker}: {description}")
    return flags


def build_reasoning_prefix(task: str, memory_context: str = "") -> str:
    """
    Inject before any task to trigger the full reasoning protocol.
    This is what separates AIOS from a raw LLM call.
    """
    context_block = ""
    if memory_context:
        context_block = f"\n## Retrieved Context\n{memory_context}\n"

    return f"""
{context_block}

## REASONING PROTOCOL — Execute Before Answering

**Task**: {task}

Before producing any output, work through these steps:

### Step 1 — Decode the Real Objective
- Stated request: [restate it]
- Actual goal behind the request: [what success looks like]
- Success criteria: [how to know when done]

### Step 2 — Inventory Current Knowledge
- What I know with high confidence (>85%): [list]
- What I'm uncertain about (<85%): [list]
- What I need to figure out: [list]

### Step 3 — Assumption Audit
List every assumption embedded in this task, then stress-test each:
- Assumption: [X] → Is this true? What if it's wrong?

### Step 4 — Multi-Perspective Analysis
- Technical/logical angle: [...]
- Strategic/second-order angle: [...]
- Adversarial angle (how could this be wrong?): [...]
- User's actual need angle: [...]

### Step 5 — Approach Selection
Selected reasoning method: [deductive/inductive/abductive/analogical]
Why this method fits: [...]

---

## EXECUTION

Now execute the task with full rigor. Apply all relevant AIOS protocols.

---

## SELF-CRITIQUE (after completing response)

Before finalizing, answer:
- What did I miss that a domain expert would catch?
- What claim am I making that could be wrong?
- Is the output actually actionable?
- Confidence in this response: [X]%
- Anything that should be flagged as uncertain: [list]
"""


def build_research_protocol(question: str) -> str:
    """Research protocol prompt injection for Researcher agent."""
    return f"""
Research Question: {question}

## Research Protocol

STEP 1 — Approach from multiple angles:
- Angle 1: [...]
- Angle 2: [...]
- Angle 3: [...]

STEP 2 — Source assessment (for each major claim):
- Source type: primary / secondary / anecdotal
- Reliability rating: high / medium / low
- Recency: [date or era]
- Potential bias: [...]

STEP 3 — Evidence synthesis:
- High-confidence findings (>85%): [...]
- Contested findings (evidence on both sides): [...]
- Unknown / not enough data: [...]

STEP 4 — Conclusion with confidence scores:
For each major conclusion: [claim] — Confidence: X%

STEP 5 — Explicit uncertainty statement:
What is NOT known, and why it matters for this question.

---

Now execute this research protocol fully.
"""


def build_coding_protocol(task: str, repo_context: str = "") -> str:
    """Coding protocol prompt injection for Coder agent."""
    repo_block = f"\n## Repository Context\n{repo_context}\n" if repo_context else ""
    return f"""
Software Engineering Task: {task}
{repo_block}

## Engineering Protocol

### Phase 1 — Understand Before Building
- True objective: [what success looks like]
- Affected files: [list all files that need changes]
- Architectural patterns in use: [from repo context]
- Dependencies to be aware of: [...]

### Phase 2 — Plan Before Coding
Architecture plan:
- Data flow: [...]
- New interfaces/types: [...]
- Changes to existing interfaces: [...]
- File-by-file change plan: [...]

### Phase 3 — Implementation
Write production-quality code following AIOS coding standards.
Priority order: correct → secure → readable → efficient

### Phase 4 — Verification Checklist
After writing code, verify:
- [ ] Handles all edge cases
- [ ] No SQL injection or injection vulnerabilities
- [ ] No hardcoded secrets
- [ ] Input validation at system boundaries
- [ ] Error handling for all external calls
- [ ] Tests cover critical logic paths
- [ ] Documentation explains WHY, not just what

### Phase 5 — Security Audit
Review against OWASP Top 10:
- [ ] Injection (SQL, command, LDAP)
- [ ] Authentication and session management
- [ ] Sensitive data exposure
- [ ] Access control
- [ ] Security misconfiguration

---

Now execute this engineering protocol.
"""


def score_output_quality(output: str) -> dict[str, Any]:
    """
    Heuristic quality scoring without an LLM call.
    Used for quick pre-critique assessment.
    """
    scores: dict[str, float] = {}

    # Length check (too short = incomplete, too long = verbose)
    words = len(output.split())
    scores["length"] = min(1.0, words / 200) if words < 200 else max(0.5, 1.0 - (words - 2000) / 10000)

    # Actionability signals
    action_signals = ["next step", "recommend", "should", "action", "implement", "do ", "run "]
    scores["actionability"] = min(1.0, sum(1 for s in action_signals if s in output.lower()) / 3)

    # Uncertainty flagging (good sign — means the model is calibrated)
    uncertainty_signals = ["uncertain", "unclear", "unknown", "~]", "[?]", "confidence", "approximately"]
    scores["calibration"] = min(1.0, sum(1 for s in uncertainty_signals if s in output.lower()) / 2)

    # Structure signals
    structure_signals = ["##", "###", "1.", "2.", "-", "*", "**"]
    scores["structure"] = min(1.0, sum(1 for s in structure_signals if s in output) / 4)

    # Evidence signals
    evidence_signals = ["because", "since", "therefore", "data shows", "evidence", "source"]
    scores["evidence"] = min(1.0, sum(1 for s in evidence_signals if s in output.lower()) / 3)

    overall = sum(scores.values()) / len(scores)
    return {"component_scores": scores, "overall": round(overall * 100, 1)}
