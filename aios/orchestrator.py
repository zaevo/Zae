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
    """Lazily import all advanced modules to avoid hard startup failures."""
    m = {}
    singletons = [
        ("temporal", ".temporal.engine", "TemporalReasoningEngine"),
        ("archaeology", ".archaeology.tracer", "DecisionArchaeologist"),
        ("pattern_miner", ".patterns.miner", "pattern_miner"),
        ("proactive_monitor", ".proactive.monitor", "proactive_monitor"),
        ("belief_network", ".bayesian.network", "belief_network"),
        ("self_architect", ".self_improvement.architect", "self_architect"),
        ("living_docs", ".living_docs.documents", "living_docs"),
        ("cognitive", ".cognitive.fingerprint", "CognitiveFingerprintEngine"),
        # Phase 3
        ("simulation", ".simulation.engine", "simulation_engine"),
        ("tom", ".theory_of_mind.modeler", "tom_modeler"),
        ("curiosity", ".curiosity.engine", "curiosity_engine"),
        ("causal", ".causal.model", "causal_model"),
        ("goals", ".goals.manager", "goal_manager"),
        ("dream", ".dream.consolidator", "dream_consolidator"),
        ("analogy", ".analogy.engine", "analogy_engine"),
        ("specialization", ".specialization.tracker", "specialization_tracker"),
        ("epistemic", ".epistemic.state", "epistemic_machine"),
        ("adversarial_detect", ".adversarial_detect.detector", "adversarial_detector"),
    ]
    import importlib
    for key, module_path, attr in singletons:
        try:
            mod = importlib.import_module(module_path, package=__name__.rsplit(".", 1)[0])
            m[key] = getattr(mod, attr)
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
        for key in (
            "pattern_miner", "belief_network", "self_architect", "living_docs",
            "curiosity", "causal", "goals", "dream", "analogy",
            "specialization", "epistemic", "adversarial_detect",
        ):
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

    # ── Phase 3 Advanced Capabilities ────────────────────────────────────────

    async def find_analogies(self, problem: str, source_domain: str = "general") -> str:
        """
        Find structural analogies between this problem and other domains.
        Returns the best analogy + a transferred solution approach.
        """
        engine = self._adv.get("analogy")
        if not engine:
            return "Analogical leap engine not available."
        try:
            engine.initialize()
            result = await engine.find_analogies(problem, source_domain=source_domain)
            return engine.format_analogy_result(result)
        except Exception as e:
            return f"Analogy search failed: {e}"

    async def simulate(self, task: str) -> str:
        """
        Run mental simulation on a task: generate N approaches, simulate outcomes,
        return which path is most likely to succeed and why.
        """
        sim = self._adv.get("simulation")
        if not sim:
            return "Mental simulation engine not available."
        try:
            sim.initialize()
            result = await sim.simulate(task, context=memory.retrieve_context_for_task(
                task, self.session_id, self.project_id
            ))
            lines = [
                f"Simulated {len(result.paths)} approaches.",
                f"Best path: {result.selected_path.approach_name} (confidence: {result.overall_confidence:.0%})",
                f"Description: {result.selected_path.approach_description}",
            ]
            if result.execution_guidance:
                lines.append(f"Execution guidance: {result.execution_guidance}")
            if result.merged_risks:
                lines.append("Watch for: " + "; ".join(result.merged_risks[:3]))
            return "\n".join(lines)
        except Exception as e:
            return f"Simulation failed: {e}"

    async def dream(self) -> str:
        """
        Run one dream/consolidation cycle: synthesize recent memories,
        find non-obvious connections, generate new hypotheses.
        Returns a summary of insights generated.
        """
        dreamer = self._adv.get("dream")
        if not dreamer:
            return "Dream consolidator not available."
        try:
            dreamer.initialize()
            result = await dreamer.dream()
            if not result.insights_generated:
                return f"Dream cycle complete. Processed {result.memories_processed} memories. No new insights generated (need more memories)."
            lines = [
                f"Dream cycle: {result.memories_processed} memories → {len(result.insights_generated)} insights in {result.duration_seconds:.1f}s",
                "",
            ]
            for i, ins in enumerate(result.insights_generated[:5], 1):
                lines.append(f"{i}. [{ins.insight_type}] {ins.insight}")
                if ins.actionable and ins.action_hint:
                    lines.append(f"   → {ins.action_hint}")
            if result.hypotheses:
                lines.append(f"\nGenerated {len(result.hypotheses)} hypotheses:")
                for h in result.hypotheses[:3]:
                    lines.append(f"  • {h.get('hypothesis', '')}")
            return "\n".join(lines)
        except Exception as e:
            return f"Dream cycle failed: {e}"

    def get_user_model(self) -> str:
        """Return the current Theory of Mind model of the user."""
        tom = self._adv.get("tom")
        if not tom:
            return "Theory of Mind module not available."
        try:
            tom.initialize()
            return tom.summarize_model()
        except Exception as e:
            return f"User model unavailable: {e}"

    def get_open_questions(self) -> list[dict]:
        """Return the curiosity engine's open knowledge gaps."""
        curiosity = self._adv.get("curiosity")
        if not curiosity:
            return []
        try:
            curiosity.initialize()
            gaps = curiosity.get_open_gaps(limit=10)
            return [{"question": g.question, "priority": g.priority, "domain": g.domain} for g in gaps]
        except Exception:
            return []

    async def investigate_gap(self) -> str:
        """Have the curiosity engine autonomously investigate its top open question."""
        curiosity = self._adv.get("curiosity")
        if not curiosity:
            return "Curiosity engine not available."
        try:
            curiosity.initialize()
            gap = await curiosity.investigate_next()
            if not gap:
                return "No open knowledge gaps to investigate."
            return f"Investigated: {gap.question}\n\nAnswer:\n{gap.answer}"
        except Exception as e:
            return f"Investigation failed: {e}"

    async def causal_query(
        self, intervention: str, value: str, target: str
    ) -> str:
        """
        Causal intervention query: 'If I SET <intervention> to <value>, what happens to <target>?'
        Uses do-calculus to separate correlation from causation.
        """
        causal = self._adv.get("causal")
        if not causal:
            return "Causal world model not available."
        try:
            causal.initialize()
            result = await causal.do_query(intervention, value, target)
            return (
                f"do({intervention}={value}) → {target}\n"
                f"Predicted effect: {result.predicted_effect}\n"
                f"Direction: {result.direction} | Magnitude: {result.magnitude} | Confidence: {result.confidence:.0%}\n"
                f"Path: {' → '.join(result.causal_path) if result.causal_path else 'Direct'}\n"
                f"Reasoning: {result.reasoning}"
            )
        except Exception as e:
            return f"Causal query failed: {e}"

    def add_goal(
        self, title: str, description: str = "",
        horizon: str = "tactical", priority: float = 5.0
    ) -> str:
        """Add a goal to the hierarchy (horizon: immediate|tactical|strategic|visionary)."""
        goals = self._adv.get("goals")
        if not goals:
            return "Goal manager not available."
        try:
            goals.initialize()
            goal_id = goals.add_goal(
                title=title, description=description,
                horizon=horizon, priority=priority, project_id=self.project_id
            )
            return f"Goal #{goal_id} added: '{title}' [{horizon}]"
        except Exception as e:
            return f"Failed to add goal: {e}"

    def get_goals(self) -> str:
        """Show the current goal hierarchy."""
        goals = self._adv.get("goals")
        if not goals:
            return "Goal manager not available."
        try:
            goals.initialize()
            return goals.format_goal_tree(project_id=self.project_id)
        except Exception as e:
            return f"Failed to fetch goals: {e}"

    async def reprioritize_goals(self) -> str:
        """Let AI reprioritize the goal tree based on recent activity."""
        goals = self._adv.get("goals")
        if not goals:
            return "Goal manager not available."
        try:
            goals.initialize()
            result = await goals.reprioritize(project_id=self.project_id)
            if not result:
                return "Need at least 2 goals to reprioritize."
            changes = result.get("priority_changes", [])
            insight = result.get("insight", "")
            lines = [f"Reprioritization complete. {len(changes)} changes."]
            for c in changes[:5]:
                lines.append(f"  Goal #{c['goal_id']}: new priority={c['new_priority']} — {c['reason']}")
            if insight:
                lines.append(f"\nStrategic insight: {insight}")
            return "\n".join(lines)
        except Exception as e:
            return f"Reprioritization failed: {e}"

    def get_epistemic_map(self, domain: str | None = None) -> str:
        """Show the structured knowledge map: what we know vs believe vs suspect vs don't know."""
        epistemic = self._adv.get("epistemic")
        if not epistemic:
            return "Epistemic state machine not available."
        try:
            epistemic.initialize()
            return epistemic.format_knowledge_map(domain=domain)
        except Exception as e:
            return f"Failed to get epistemic map: {e}"

    async def find_blind_spots(self, domain: str) -> str:
        """Find unknown unknowns — things we don't know we don't know — in a domain."""
        epistemic = self._adv.get("epistemic")
        if not epistemic:
            return "Epistemic state machine not available."
        try:
            epistemic.initialize()
            spots = await epistemic.find_blind_spots(domain)
            if not spots:
                return f"No blind spots found in '{domain}'."
            lines = [f"Found {len(spots)} blind spots in '{domain}':"]
            for i, s in enumerate(spots, 1):
                lines.append(f"\n{i}. {s.blind_spot}")
                lines.append(f"   Why it matters: {s.why_matters}")
                lines.append(f"   How to explore: {s.investigation_hint}")
            return "\n".join(lines)
        except Exception as e:
            return f"Blind spot analysis failed: {e}"

    def get_agent_leaderboard(self) -> str:
        """Show which agents are best at which task categories (based on real track records)."""
        spec = self._adv.get("specialization")
        if not spec:
            return "Specialization tracker not available."
        try:
            spec.initialize()
            return spec.format_leaderboard()
        except Exception as e:
            return f"Failed to get leaderboard: {e}"

    def get_dream_insights(self) -> list[dict]:
        """Return recent insights generated during dream/consolidation cycles."""
        dreamer = self._adv.get("dream")
        if not dreamer:
            return []
        try:
            dreamer.initialize()
            return dreamer.get_recent_insights(limit=10)
        except Exception:
            return []

    def get_hypotheses(self) -> list[dict]:
        """Return hypotheses generated during dream cycles."""
        dreamer = self._adv.get("dream")
        if not dreamer:
            return []
        try:
            dreamer.initialize()
            return dreamer.get_hypotheses()
        except Exception:
            return []

    def get_threat_stats(self) -> dict:
        """Return adversarial input detection statistics."""
        detector = self._adv.get("adversarial_detect")
        if not detector:
            return {}
        try:
            detector.initialize()
            return detector.get_detection_stats()
        except Exception:
            return {}

    async def start_background_services(self) -> None:
        """Start all background services: curiosity investigation, dream loop, proactive monitor."""
        # Curiosity background investigation
        curiosity = self._adv.get("curiosity")
        if curiosity:
            try:
                curiosity.initialize()
                asyncio.create_task(curiosity.start_background_investigation(interval_seconds=600))
            except Exception:
                pass

        # Dream consolidation loop
        dreamer = self._adv.get("dream")
        if dreamer:
            try:
                dreamer.initialize()
                asyncio.create_task(dreamer.start_dream_loop(idle_after_seconds=1800))
            except Exception:
                pass

        # Proactive project monitor
        monitor = self._adv.get("proactive_monitor")
        if monitor:
            try:
                monitor.initialize()
                asyncio.create_task(
                    monitor.start_background_monitoring(
                        interval_seconds=1800,
                        project_ids=[self.project_id] if self.project_id else None,
                        session_id=self.session_id,
                    )
                )
            except Exception:
                pass

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
            "active_modules": len(self._adv),
            "module_names": sorted(self._adv.keys()),
        }
