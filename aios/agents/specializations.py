"""
All specialized AIOS agents.
Each agent has its own model tier, system prompt, and optional tool definitions.
"""

import json
from ..config import config
from .base import BaseAgent, AgentResult, AgentMessage


class CEOAgent(BaseAgent):
    name = "ceo"
    description = "Orchestrator. Analyzes tasks, routes to agents, enforces quality gates."

    def __init__(self):
        super().__init__()
        self.model = config.ceo_model

    async def route_task(self, task: str, context: str = "") -> dict:
        from ..system_prompt import CEO_ROUTING_PROMPT
        self._system_prompt = CEO_ROUTING_PROMPT
        result = await self.run(
            f"Analyze this task and produce a routing plan:\n\n{task}",
            context=context,
            max_tokens=config.max_tokens_ceo,
        )
        try:
            # Extract JSON from response
            content = result.content
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(content[start:end])
        except (json.JSONDecodeError, ValueError):
            pass
        return {
            "task_analysis": task[:200],
            "complexity": "medium",
            "agents_required": ["researcher", "writer"],
            "parallel_groups": [["researcher"], ["writer"]],
            "success_criteria": ["Addresses the objective", "Actionable output"],
            "estimated_phases": 3,
            "risks": [],
            "confidence": 0.7,
        }


class PlannerAgent(BaseAgent):
    name = "planner"
    description = "Decomposes tasks into subtask trees with dependencies and effort estimates."

    async def decompose(self, task: str, routing: dict, context: str = "") -> dict:
        prompt = f"""
Task: {task}

CEO Routing Plan:
{json.dumps(routing, indent=2)}

Produce a detailed execution plan as JSON:
{{
  "subtasks": [
    {{
      "id": "st1",
      "title": "...",
      "description": "...",
      "agent": "researcher",
      "effort": "medium",
      "depends_on": [],
      "output_format": "..."
    }}
  ],
  "critical_path": ["st1", "st2"],
  "parallel_opportunities": [["st1", "st2"]],
  "risks": [{{ "description": "...", "mitigation": "..." }}],
  "total_effort": "medium"
}}
"""
        return await self.run(prompt, context=context)


class ResearcherAgent(BaseAgent):
    name = "researcher"
    description = "Multi-source research, evidence synthesis, confidence-weighted conclusions."


class CoderAgent(BaseAgent):
    name = "coder"
    description = "Production-quality software engineering with security auditing and test generation."
    model = ""  # uses worker_model default

    TOOLS = [
        {
            "name": "read_file",
            "description": "Read a file from the repository",
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path relative to project root"}
                },
                "required": ["path"],
            },
        },
        {
            "name": "list_files",
            "description": "List files in a directory",
            "input_schema": {
                "type": "object",
                "properties": {
                    "directory": {"type": "string", "description": "Directory path"},
                    "pattern": {"type": "string", "description": "Glob pattern"},
                },
                "required": ["directory"],
            },
        },
    ]

    async def plan_implementation(self, task: str, context: str = "") -> AgentResult:
        prompt = f"""
Software Engineering Task: {task}

Before writing any code, produce an implementation plan:
1. Files to be created or modified
2. Architecture decisions
3. Interfaces and data flow
4. Security considerations
5. Test strategy
6. Potential failure modes

Then implement the solution with production-quality code.
"""
        return await self.run(prompt, context=context)


class WriterAgent(BaseAgent):
    name = "writer"
    description = "Executive-quality written deliverables across all formats."


class AnalystAgent(BaseAgent):
    name = "analyst"
    description = "Data interpretation, pattern recognition, quantitative reasoning."


class ScientistAgent(BaseAgent):
    name = "scientist"
    description = "Hypothesis generation, experimental design, causal inference."


class CriticAgent(BaseAgent):
    name = "critic"
    description = "Quality control. Reviews all outputs before delivery. Never lets mediocrity pass."
    model = ""

    async def review(self, content: str, success_criteria: list[str], context: str = "") -> AgentResult:
        criteria_text = "\n".join(f"- {c}" for c in success_criteria)
        prompt = f"""
Review this output against the success criteria. Be rigorous — your job is to find problems.

SUCCESS CRITERIA:
{criteria_text}

OUTPUT TO REVIEW:
{content}

Produce your review in this format:
## Completeness Score: X/100
## Issues Found
[List specific issues — logical gaps, unsupported claims, missing components]
## Specific Improvements
[List concrete improvements]
## Verdict: PASS | NEEDS_REVISION | FAIL
## Revised Output (if NEEDS_REVISION)
[Your improved version]
"""
        return await self.run(prompt, context=context)


class FactCheckerAgent(BaseAgent):
    name = "fact_checker"
    description = "Claims verification, source validation, hallucination detection."
    model = ""

    async def verify(self, content: str, context: str = "") -> AgentResult:
        prompt = f"""
Fact-check this content. For each major factual claim, assess:
- Is it verifiable?
- What evidence supports or contradicts it?
- What is your confidence level (0.0–1.0)?

Flag each claim as: [VERIFIED], [UNVERIFIED], [CONTESTED], [OPINION], or [HALLUCINATION_RISK]

CONTENT:
{content}
"""
        return await self.run(prompt, context=context)


class MemoryManagerAgent(BaseAgent):
    name = "memory_manager"
    description = "Memory retrieval, consolidation, and learning extraction."
    model = ""

    async def extract_learnings(self, task: str, result: str, context: str = "") -> AgentResult:
        prompt = f"""
Extract what is worth remembering from this task execution.

TASK: {task}

RESULT: {result}

For each insight worth storing, produce:
{{
  "content": "The specific insight",
  "memory_type": "episodic|semantic|procedural|preference",
  "importance": 7.5,
  "tags": ["tag1", "tag2"]
}}

Focus on:
- Reusable patterns and workflows
- Important facts about the user or their projects
- Mistakes made and how they were corrected
- Effective approaches to similar problems

Output as a JSON array of memory objects.
"""
        return await self.run(prompt, context=context)


class FinanceAgent(BaseAgent):
    name = "finance"
    description = "Financial modeling, unit economics, investment analysis."

    async def analyze(self, task: str, context: str = "") -> AgentResult:
        prompt = f"""
Financial Analysis Task: {task}

Produce analysis covering:
1. Base case / Upside case / Downside case
2. Key assumptions (and their sensitivity)
3. Unit economics if applicable
4. Risk factors
5. Recommendation

Always show your model/calculations, not just conclusions.
"""
        return await self.run(prompt, context=context)


class AssistantAgent(BaseAgent):
    name = "assistant"
    description = "Personal productivity, scheduling, communications drafting."
    model = ""

    def __init__(self):
        super().__init__()
        self.model = config.fast_model


class SecurityAgent(BaseAgent):
    name = "security"
    description = "Security auditing, threat modeling, CVE research, pentest support, defensive hardening."

    def __init__(self):
        super().__init__()
        self.model = config.ceo_model  # Security requires the most capable model
        from ..security.agent import SECURITY_AGENT_PROMPT
        self._system_prompt = SECURITY_AGENT_PROMPT


class VulnResearcherAgent(BaseAgent):
    name = "vuln_researcher"
    description = "Deep vulnerability research, CVE analysis, exploit research for authorized contexts."

    def __init__(self):
        super().__init__()
        self.model = config.ceo_model
        from ..security.agent import VULN_RESEARCHER_PROMPT
        self._system_prompt = VULN_RESEARCHER_PROMPT


# Agent registry — maps name to class
AGENT_REGISTRY: dict[str, type[BaseAgent]] = {
    "ceo": CEOAgent,
    "planner": PlannerAgent,
    "researcher": ResearcherAgent,
    "coder": CoderAgent,
    "writer": WriterAgent,
    "analyst": AnalystAgent,
    "scientist": ScientistAgent,
    "critic": CriticAgent,
    "fact_checker": FactCheckerAgent,
    "memory_manager": MemoryManagerAgent,
    "finance": FinanceAgent,
    "assistant": AssistantAgent,
    "security": SecurityAgent,
    "vuln_researcher": VulnResearcherAgent,
}


def get_agent(name: str) -> BaseAgent:
    cls = AGENT_REGISTRY.get(name)
    if cls is None:
        raise ValueError(f"Unknown agent: {name}. Available: {list(AGENT_REGISTRY)}")
    return cls()
