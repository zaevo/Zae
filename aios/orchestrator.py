"""
AIOS Orchestrator
The top-level entry point for all task execution.
Routes tasks through the workflow engine and manages sessions.
"""

import asyncio
import uuid
from datetime import datetime
from typing import AsyncIterator

from .config import config
from .memory.manager import memory
from .memory.types import MemoryType
from .workflow.engine import WorkflowEngine, WorkflowResult


class AIOS:
    """
    AI Operating System — top-level interface.

    Usage:
        aios = AIOS()
        result = await aios.run("Analyze the competitive landscape for restaurant SaaS in Atlanta")
        print(result.final_output)
    """

    VERSION = "1.0.0"

    def __init__(self, session_id: str | None = None, project_id: str | None = None):
        config.validate()
        self.session_id = session_id or str(uuid.uuid4())
        self.project_id = project_id
        self._engine = WorkflowEngine(session_id=self.session_id)
        self._started_at = datetime.utcnow()
        self._task_count = 0
        memory.initialize()

    async def run(self, task: str) -> WorkflowResult:
        """
        Execute a task through the full 7-phase AIOS workflow.
        Returns the final result with quality scoring, confidence, and flags.
        """
        self._task_count += 1
        result = await self._engine.execute(task, project_id=self.project_id)

        # Store episodic memory for this task
        memory.store(
            content=f"Task: {task[:200]}\nResult summary: {result.final_output[:300]}",
            memory_type=MemoryType.EPISODIC,
            importance=6.0,
            tags=["task_execution"],
            session_id=self.session_id,
            project_id=self.project_id,
            source_agent="orchestrator",
        )
        return result

    async def run_stream(self, task: str) -> AsyncIterator[str]:
        """
        Streaming interface — yields phase-by-phase progress.
        Useful for long-running tasks where the user needs visibility.
        """
        yield f"[AIOS] Starting task #{self._task_count + 1}\n"
        yield f"[UNDERSTAND] Retrieving memory context...\n"

        context = memory.retrieve_context_for_task(task, self.session_id, self.project_id)
        if context:
            yield f"[MEMORY] {context.count(chr(10))} relevant memories retrieved\n"
        else:
            yield "[MEMORY] No prior context found for this task\n"

        yield "[CEO] Analyzing task and routing to agents...\n"
        from .agents.specializations import CEOAgent
        ceo = CEOAgent()
        routing = await ceo.route_task(task, context)

        agents = routing.get("agents_required", [])
        yield f"[CEO] Activating agents: {', '.join(agents)}\n"
        yield f"[CEO] Complexity: {routing.get('complexity', 'unknown')}\n"
        yield "[EXECUTE] Running agents...\n"

        result = await self.run(task)
        yield f"[COMPLETE] Quality: {result.quality_score:.0f}/100 | "
        yield f"Confidence: {result.confidence:.0%} | "
        yield f"Agents: {len(result.agents_used)} | "
        yield f"Tokens: {result.tokens_used:,}\n\n"
        yield "━" * 60 + "\n\n"
        yield result.final_output

    def set_project(self, project_id: str, description: str = "") -> None:
        """Set the active project for memory scoping."""
        self.project_id = project_id
        if description:
            memory.store(
                content=f"Project: {project_id}\nDescription: {description}",
                memory_type=MemoryType.PROJECT,
                importance=8.0,
                tags=["project_setup"],
                project_id=project_id,
                session_id=self.session_id,
                source_agent="orchestrator",
            )

    def remember(self, content: str, importance: float = 7.0, tags: list[str] | None = None) -> None:
        """Manually store something to memory."""
        memory.store(
            content=content,
            memory_type=MemoryType.SEMANTIC,
            importance=importance,
            tags=tags or [],
            session_id=self.session_id,
            project_id=self.project_id,
            source_agent="user",
        )

    def recall(self, query: str, top_k: int = 5) -> list[str]:
        """Query memory and return relevant content."""
        results = memory.query(query, top_k=top_k)
        return [r.memory.content for r in results]

    @property
    def stats(self) -> dict:
        return {
            "session_id": self.session_id,
            "project_id": self.project_id,
            "tasks_completed": self._task_count,
            "session_duration_minutes": (
                datetime.utcnow() - self._started_at
            ).total_seconds() / 60,
            "version": self.VERSION,
        }
