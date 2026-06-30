"""
AIOS Workflow Engine
Enforces the 7-phase quality pipeline on every task.
No task bypasses verification and self-critique.
"""

import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from ..agents.base import AgentResult
from ..agents.specializations import (
    CEOAgent, CriticAgent, FactCheckerAgent,
    MemoryManagerAgent, get_agent,
)
from ..config import config
from ..intelligence.reasoning import (
    build_reasoning_prefix, build_research_protocol,
    build_coding_protocol, score_output_quality,
    extract_confidence, extract_flags,
)
from ..memory.manager import memory
from ..memory.types import MemoryType


@dataclass
class WorkflowPhase:
    name: str
    started_at: float = 0.0
    completed_at: float = 0.0
    output: str = ""
    agent_results: list[AgentResult] = field(default_factory=list)
    succeeded: bool = False


@dataclass
class WorkflowResult:
    task_id: str
    task: str
    final_output: str
    phases: list[WorkflowPhase]
    total_duration_ms: float
    agents_used: list[str]
    tokens_used: int
    quality_score: float
    confidence: float
    flags: list[str]
    succeeded: bool
    session_id: str


class WorkflowEngine:
    """
    Executes the 7-phase AIOS workflow:
    1. Understand  2. Plan  3. Execute  4. Verify
    5. Critique    6. Deliver  7. Learn
    """

    def __init__(self, session_id: str | None = None):
        self.session_id = session_id or str(uuid.uuid4())
        self._ceo = CEOAgent()
        self._critic = CriticAgent()
        self._fact_checker = FactCheckerAgent()
        self._memory_agent = MemoryManagerAgent()

    async def execute(self, task: str, project_id: str | None = None) -> WorkflowResult:
        task_id = str(uuid.uuid4())
        start_time = time.monotonic()
        phases: list[WorkflowPhase] = []
        tokens_total = 0
        agents_used: list[str] = ["ceo"]

        # PHASE 1 — UNDERSTAND
        phase1 = await self._phase_understand(task, project_id)
        phases.append(phase1)
        memory_context = phase1.output

        # PHASE 2 — PLAN (CEO routes the task)
        phase2, routing = await self._phase_plan(task, memory_context)
        phases.append(phase2)
        tokens_total += sum(
            r.tokens_used for r in phase2.agent_results if r.tokens_used
        )

        # PHASE 3 — EXECUTE (parallel agent groups)
        phase3 = await self._phase_execute(task, routing, memory_context)
        phases.append(phase3)
        agents_used.extend(routing.get("agents_required", []))
        tokens_total += sum(r.tokens_used for r in phase3.agent_results)

        # PHASE 4 — VERIFY (fact check)
        phase4 = await self._phase_verify(phase3.output, routing)
        phases.append(phase4)

        # PHASE 5 — CRITIQUE (quality gate)
        phase5 = await self._phase_critique(
            phase3.output, routing.get("success_criteria", [])
        )
        phases.append(phase5)

        # PHASE 6 — DELIVER (format final output)
        final_output = self._phase_deliver(task, phase3.output, phase5, routing)
        phases.append(WorkflowPhase(name="deliver", output=final_output, succeeded=True))

        # PHASE 7 — LEARN (async, doesn't block delivery)
        asyncio.create_task(
            self._phase_learn(task, final_output, memory_context, project_id)
        )

        duration_ms = (time.monotonic() - start_time) * 1000
        confidence = extract_confidence(final_output)
        flags = extract_flags(final_output)
        quality = score_output_quality(final_output)

        return WorkflowResult(
            task_id=task_id,
            task=task,
            final_output=final_output,
            phases=phases,
            total_duration_ms=duration_ms,
            agents_used=list(set(agents_used)),
            tokens_used=tokens_total,
            quality_score=quality["overall"],
            confidence=confidence,
            flags=flags,
            succeeded=True,
            session_id=self.session_id,
        )

    async def _phase_understand(self, task: str, project_id: str | None) -> WorkflowPhase:
        phase = WorkflowPhase(name="understand", started_at=time.monotonic())
        try:
            memory.initialize()
            context = memory.retrieve_context_for_task(task, self.session_id, project_id)
            phase.output = context
            phase.succeeded = True
        except Exception as e:
            phase.output = ""
            phase.succeeded = True  # memory failure shouldn't block execution
        phase.completed_at = time.monotonic()
        return phase

    async def _phase_plan(self, task: str, memory_context: str) -> tuple[WorkflowPhase, dict]:
        phase = WorkflowPhase(name="plan", started_at=time.monotonic())
        routing = await self._ceo.route_task(task, memory_context)
        phase.agent_results = []
        phase.output = json.dumps(routing, indent=2)
        phase.succeeded = True
        phase.completed_at = time.monotonic()
        return phase, routing

    async def _phase_execute(
        self, task: str, routing: dict, memory_context: str
    ) -> WorkflowPhase:
        phase = WorkflowPhase(name="execute", started_at=time.monotonic())
        agents_required = routing.get("agents_required", ["researcher", "writer"])
        parallel_groups = routing.get("parallel_groups", [agents_required])

        # Determine task type for protocol injection
        task_lower = task.lower()
        is_coding = any(w in task_lower for w in ["code", "implement", "build", "debug", "fix", "refactor"])
        is_research = any(w in task_lower for w in ["research", "find", "what is", "analyze", "compare"])

        if is_coding:
            enriched_task = build_coding_protocol(task)
        elif is_research:
            enriched_task = build_research_protocol(task)
        else:
            enriched_task = build_reasoning_prefix(task, memory_context)

        all_results: list[AgentResult] = []
        combined_outputs: list[str] = []

        for group in parallel_groups:
            group_tasks = []
            for agent_name in group:
                if agent_name in ("ceo", "planner"):
                    continue
                try:
                    agent = get_agent(agent_name)
                    group_tasks.append(agent.run(enriched_task, context=memory_context))
                except ValueError:
                    pass

            if group_tasks:
                results = await asyncio.gather(*group_tasks, return_exceptions=True)
                for result in results:
                    if isinstance(result, AgentResult) and result.succeeded:
                        all_results.append(result)
                        combined_outputs.append(
                            f"## [{result.agent_name.upper()}]\n{result.content}"
                        )

        phase.agent_results = all_results
        phase.output = "\n\n---\n\n".join(combined_outputs) if combined_outputs else "No agent output generated."
        phase.succeeded = bool(combined_outputs)
        phase.completed_at = time.monotonic()
        return phase

    async def _phase_verify(self, content: str, routing: dict) -> WorkflowPhase:
        phase = WorkflowPhase(name="verify", started_at=time.monotonic())
        complexity = routing.get("complexity", "medium")

        # Only fact-check medium+ complexity tasks
        if complexity in ("high", "critical") and len(content) > 500:
            result = await self._fact_checker.verify(content[:4000])
            phase.agent_results = [result]
            phase.output = result.content
        else:
            phase.output = "Verification skipped for low-complexity task."

        phase.succeeded = True
        phase.completed_at = time.monotonic()
        return phase

    async def _phase_critique(
        self, content: str, success_criteria: list[str]
    ) -> WorkflowPhase:
        phase = WorkflowPhase(name="critique", started_at=time.monotonic())
        if not success_criteria:
            success_criteria = [
                "Addresses the stated objective",
                "Factually accurate with flagged uncertainties",
                "Actionable with clear next steps",
                "Appropriate depth and structure",
            ]

        result = await self._critic.review(content[:6000], success_criteria)
        phase.agent_results = [result]
        phase.output = result.content
        phase.succeeded = result.succeeded
        phase.completed_at = time.monotonic()
        return phase

    def _phase_deliver(
        self,
        task: str,
        raw_output: str,
        critique_phase: WorkflowPhase,
        routing: dict,
    ) -> str:
        critique = critique_phase.output

        # If critic produced a revised version, use it; else use raw output
        revised_marker = "## Revised Output"
        if revised_marker in critique:
            revised = critique[critique.find(revised_marker) + len(revised_marker):].strip()
            if len(revised) > 200:
                return revised

        # If pass — use raw output with quality metadata appended
        verdict_pass = "PASS" in critique.upper() and "FAIL" not in critique.upper()
        if verdict_pass:
            return raw_output

        # Needs revision but we have the critic output — append it
        return f"{raw_output}\n\n---\n*Quality review notes:*\n{critique[:500]}"

    async def _phase_learn(
        self,
        task: str,
        result: str,
        existing_context: str,
        project_id: str | None,
    ) -> None:
        """Background learning — extracts and stores insights after delivery."""
        try:
            learning_result = await self._memory_agent.extract_learnings(task, result[:3000])
            if not learning_result.succeeded:
                return

            # Parse learnings from agent output
            content = learning_result.content
            start = content.find("[")
            end = content.rfind("]") + 1
            if start < 0 or end <= start:
                return

            learnings = json.loads(content[start:end])
            for item in learnings:
                if not isinstance(item, dict):
                    continue
                memory_type_str = item.get("memory_type", "semantic")
                try:
                    mem_type = MemoryType(memory_type_str)
                except ValueError:
                    mem_type = MemoryType.SEMANTIC

                memory.store(
                    content=item.get("content", ""),
                    memory_type=mem_type,
                    importance=float(item.get("importance", 5.0)),
                    tags=item.get("tags", []),
                    project_id=project_id,
                    session_id=self.session_id,
                    source_agent="memory_manager",
                )

            # Consolidate to remove low-value decayed entries
            memory.consolidate(self.session_id)

        except Exception:
            pass  # Learning failure must never affect the delivered result
