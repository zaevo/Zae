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


def _try_import_advanced():
    """Lazily import Phase 2 advanced modules to avoid hard startup failures."""
    m = {}
    try:
        from .temporal.engine import TemporalReasoningEngine
        m["temporal"] = TemporalReasoningEngine
    except Exception:
        pass
    try:
        from .archaeology.tracer import DecisionArchaeologist
        m["archaeology"] = DecisionArchaeologist
    except Exception:
        pass
    try:
        from .patterns.miner import pattern_miner
        m["pattern_miner"] = pattern_miner
    except Exception:
        pass
    try:
        from .proactive.monitor import proactive_monitor
        m["proactive_monitor"] = proactive_monitor
    except Exception:
        pass
    try:
        from .bayesian.network import belief_network
        m["belief_network"] = belief_network
    except Exception:
        pass
    try:
        from .self_improvement.architect import self_architect
        m["self_architect"] = self_architect
    except Exception:
        pass
    try:
        from .living_docs.documents import living_docs
        m["living_docs"] = living_docs
    except Exception:
        pass
    try:
        from .cognitive.fingerprint import CognitiveFingerprintEngine
        m["cognitive"] = CognitiveFingerprintEngine
    except Exception:
        pass
    try:
        from .bayesian.network import belief_network
        m["belief_network"] = belief_network
    except Exception:
        pass
    return m


class AIOS:
    """
    AI Operating System — top-level interface.

    Usage:
        aios = AIOS()
        result = await aios.run("Analyze the competitive landscape for restaurant SaaS in Atlanta")
        print(result.final_output)
    """

    VERSION = "2.0.0"

    def __init__(self, session_id: str | None = None, project_id: str | None = None):
        config.validate()
        self.session_id = session_id or str(uuid.uuid4())
        self.project_id = project_id
        self._engine = WorkflowEngine(session_id=self.session_id)
        self._started_at = datetime.utcnow()
        self._task_count = 0
        self._adv = _try_import_advanced()
        memory.initialize()
        self._init_advanced_modules()

    def _init_advanced_modules(self) -> None:
        """Initialize SQLite-backed modules on startup."""
        for key in ("pattern_miner", "belief_network", "self_architect", "living_docs"):
            mod = self._adv.get(key)
            if mod and hasattr(mod, "initialize"):
                try:
                    mod.initialize()
                except Exception:
                    pass

    async def run(self, task: str) -> WorkflowResult:
        """Execute a task through the full AIOS workflow."""
        self._task_count += 1
        result = await self._engine.execute(task, project_id=self.project_id)

        # Store episodic memory
        memory.store(
            content=f"Task: {task[:200]}\nResult summary: {result.final_output[:300]}",
            memory_type=MemoryType.EPISODIC,
            importance=6.0,
            tags=["task_execution"],
            session_id=self.session_id,
            project_id=self.project_id,
            source_agent="orchestrator",
        )

        # Update cognitive fingerprint (learn user patterns)
        cognitive_cls = self._adv.get("cognitive")
        if cognitive_cls:
            try:
                engine = cognitive_cls()
                engine.initialize()
                await engine.observe_interaction(task, result.final_output)
            except Exception:
                pass

        # Update Bayesian network beliefs from task results
        bn = self._adv.get("belief_network")
        if bn and result.confidence > 0:
            try:
                confidence_node = f"task_success_{self.session_id[:8]}"
                bn.add_belief(confidence_node, result.confidence, f"Task: {task[:80]}")
            except Exception:
                pass

        return result

    async def run_stream(self, task: str) -> AsyncIterator[str]:
        """Stream phase-by-phase progress."""
        yield f"[AIOS] Starting task #{self._task_count + 1}\n"
        yield "[UNDERSTAND] Retrieving memory context...\n"

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
        debate = f" | Debate: {result.debate_verdict}" if result.debate_verdict else ""
        yield f"[COMPLETE] Quality: {result.quality_score:.0f}/100 | "
        yield f"Confidence: {result.confidence:.0%} | "
        yield f"Agents: {len(result.agents_used)} | "
        yield f"Tokens: {result.tokens_used:,}{debate}\n\n"
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

    # ── Phase 2 Advanced Capabilities ────────────────────────────────────────

    async def temporal(self, topic: str, depth: str = "standard") -> str:
        """
        Run temporal vantage-point analysis on a topic.
        Examines the topic from 6 time horizons + pre-mortem.
        depth: 'quick' | 'standard' | 'deep'
        """
        TemporalEngine = self._adv.get("temporal")
        if not TemporalEngine:
            return "Temporal reasoning module not available."
        engine = TemporalEngine()
        result = await engine.analyze(topic, depth=depth)
        return result.synthesis

    async def premortem(self, plan: str) -> str:
        """
        Run a pre-mortem on a plan: imagine it failed and trace why.
        Returns a structured failure analysis with mitigation recommendations.
        """
        TemporalEngine = self._adv.get("temporal")
        if not TemporalEngine:
            return "Temporal reasoning module not available."
        engine = TemporalEngine()
        result = await engine.premortem(plan)
        return result

    async def investigate(self, topic: str) -> str:
        """
        Decision archaeology: trace root causes of outcomes.
        Returns a structured finding with timeline, root cause, and lessons.
        """
        ArchaeologyClass = self._adv.get("archaeology")
        if not ArchaeologyClass:
            return "Decision archaeology module not available."
        archaeologist = ArchaeologyClass()
        finding = await archaeologist.investigate(
            topic, session_id=self.session_id, project_id=self.project_id
        )
        return (
            f"Root Cause: {finding.root_cause_classification}\n"
            f"Summary: {finding.summary}\n\n"
            f"Timeline:\n" + "\n".join(f"  - {e}" for e in finding.timeline) +
            f"\n\nDecision Points:\n" + "\n".join(f"  - {d}" for d in finding.key_decision_points) +
            f"\n\nLessons Learned:\n" + "\n".join(f"  - {l}" for l in finding.lessons_learned)
        )

    async def mine_patterns(self) -> str:
        """Mine cross-session behavioral patterns and return insights."""
        pm = self._adv.get("pattern_miner")
        if not pm:
            return "Pattern mining module not available."
        try:
            pm.initialize()
            result = await pm.mine(session_id=self.session_id)
            return pm.format_insights(result)
        except Exception as e:
            return f"Pattern mining failed: {e}"

    async def check_alerts(self) -> list[dict]:
        """
        Check proactive monitor for pending alerts about your projects.
        Returns a list of alert dicts with type, urgency, and message.
        """
        monitor = self._adv.get("proactive_monitor")
        if not monitor:
            return []
        try:
            monitor.initialize()
            alerts = monitor.get_pending_alerts()
            return [
                {
                    "type": a.alert_type,
                    "urgency": a.urgency,
                    "message": a.message,
                    "project_id": a.project_id,
                }
                for a in alerts
            ]
        except Exception:
            return []

    async def start_monitoring(self, interval_minutes: int = 30) -> None:
        """Start background proactive monitoring for your projects."""
        monitor = self._adv.get("proactive_monitor")
        if not monitor:
            return
        monitor.initialize()
        asyncio.create_task(
            monitor.start_background_monitoring(
                interval_seconds=interval_minutes * 60,
                project_ids=[self.project_id] if self.project_id else None,
                session_id=self.session_id,
            )
        )

    def add_belief(self, label: str, probability: float, evidence: str = "") -> None:
        """Add or update a belief node in the Bayesian network."""
        bn = self._adv.get("belief_network")
        if not bn:
            return
        try:
            bn.initialize()
            bn.add_belief(label, probability, evidence)
        except Exception:
            pass

    def link_beliefs(self, cause: str, effect: str, strength: float = 0.5, direction: int = 1) -> None:
        """Link two beliefs in the Bayesian network (direction: 1=positive, -1=inverse)."""
        bn = self._adv.get("belief_network")
        if not bn:
            return
        try:
            bn.link_beliefs(cause, effect, strength, direction)
        except Exception:
            pass

    def get_uncertain_beliefs(self) -> list[dict]:
        """Return beliefs with high uncertainty (probability near 0.5)."""
        bn = self._adv.get("belief_network")
        if not bn:
            return []
        try:
            bn.initialize()
            nodes = bn.get_high_uncertainty_beliefs()
            return [{"label": n.label, "probability": n.probability, "evidence": n.evidence} for n in nodes]
        except Exception:
            return []

    async def trigger_improvement(self) -> str:
        """
        Trigger recursive self-architecture: analyze agent performance
        and rewrite underperforming agent prompts.
        Returns a summary of what was improved.
        """
        sa = self._adv.get("self_architect")
        if not sa:
            return "Self-architect module not available."
        try:
            sa.initialize()
            updates = await sa.analyze_and_improve()
            if not updates:
                return "No improvements triggered yet. Need more task data (minimum 5 tasks per agent)."
            return "\n".join(
                f"Agent '{u.agent_name}': {u.improvement_summary}" for u in updates
            )
        except Exception as e:
            return f"Self-improvement failed: {e}"

    def list_living_docs(self) -> list[dict]:
        """List all living documents (self-updating documentation)."""
        ld = self._adv.get("living_docs")
        if not ld:
            return []
        try:
            ld.initialize()
            docs = ld.list_documents()
            return [
                {
                    "doc_id": d.doc_id,
                    "title": d.title,
                    "version": d.version,
                    "last_updated": d.last_updated,
                }
                for d in docs
            ]
        except Exception:
            return []

    async def create_living_doc(self, title: str, content: str, update_triggers: list[str] | None = None) -> str:
        """Create a new living document that auto-updates based on memory changes."""
        ld = self._adv.get("living_docs")
        if not ld:
            return "Living docs module not available."
        try:
            ld.initialize()
            doc = ld.create(
                title=title,
                content=content,
                update_triggers=update_triggers or [],
                project_id=self.project_id,
            )
            return f"Created living doc: {doc.doc_id} — '{doc.title}'"
        except Exception as e:
            return f"Failed to create living doc: {e}"

    @property
    def stats(self) -> dict:
        return {
            "session_id": self.session_id,
            "project_id": self.project_id,
            "tasks_completed": self._task_count,
            "session_duration_minutes": round(
                (datetime.utcnow() - self._started_at).total_seconds() / 60, 1
            ),
            "version": self.VERSION,
            "advanced_modules": list(self._adv.keys()),
        }
