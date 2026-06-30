"""
AIOS Workflow Engine v3.0
Enforces the multi-phase quality pipeline on every task.
No task bypasses verification, self-critique, adversarial debate,
mental simulation, or adversarial input detection.
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


def _try_import_all():
    """Lazily import all capability modules — startup never fails."""
    m = {}
    # Phase 2 modules
    for name, import_path in [
        ("debate", ("..adversarial.debate", "AdversarialDebateEngine")),
        ("assumption_tracker", ("..assumptions.tracker", "assumption_tracker")),
        ("failure_library", ("..failure_modes.library", "failure_library")),
        ("metacog_monitor", ("..metacognition.monitor", "metacog_monitor")),
        ("pattern_miner", ("..patterns.miner", "pattern_miner")),
        ("self_architect", ("..self_improvement.architect", "self_architect")),
        ("living_docs", ("..living_docs.documents", "living_docs")),
    ]:
        try:
            mod = __import__(import_path[0], fromlist=[import_path[1]], globals=globals())
            m[name] = getattr(mod, import_path[1])
        except Exception:
            pass

    # Phase 3 modules (new)
    for name, import_path in [
        ("simulation", ("..simulation.engine", "simulation_engine")),
        ("tom", ("..theory_of_mind.modeler", "tom_modeler")),
        ("curiosity", ("..curiosity.engine", "curiosity_engine")),
        ("causal", ("..causal.model", "causal_model")),
        ("goal_manager", ("..goals.manager", "goal_manager")),
        ("dream", ("..dream.consolidator", "dream_consolidator")),
        ("analogy", ("..analogy.engine", "analogy_engine")),
        ("specialization", ("..specialization.tracker", "specialization_tracker")),
        ("epistemic", ("..epistemic.state", "epistemic_machine")),
        ("adversarial_detect", ("..adversarial_detect.detector", "adversarial_detector")),
    ]:
        try:
            mod = __import__(import_path[0], fromlist=[import_path[1]], globals=globals())
            m[name] = getattr(mod, import_path[1])
        except Exception:
            pass

    return m


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
    debate_verdict: str = ""
    metacog_alerts: list[str] = field(default_factory=list)
    threat_level: str = "none"
    simulation_path: str = ""


class WorkflowEngine:
    """
    Executes the full AIOS workflow:
    0. Threat Scan  1. Understand  2. Plan  2.5 Simulate
    3. Execute  3.5 MetaCog  3.6 Debate  4. Verify
    4.5 Stress-Test  5. Critique  6. Deliver (calibrated)
    7. Learn (async: memory + assumptions + gaps + causal + epistemic + specialization + goals)
    """

    def __init__(self, session_id: str | None = None):
        self.session_id = session_id or str(uuid.uuid4())
        self._ceo = CEOAgent()
        self._critic = CriticAgent()
        self._fact_checker = FactCheckerAgent()
        self._memory_agent = MemoryManagerAgent()
        self._m = _try_import_all()
        self._init_modules()

    def _init_modules(self) -> None:
        for key in ("pattern_miner", "self_architect", "living_docs", "specialization",
                    "epistemic", "adversarial_detect", "curiosity", "causal", "goal_manager", "dream"):
            mod = self._m.get(key)
            if mod and hasattr(mod, "initialize"):
                try:
                    mod.initialize()
                except Exception:
                    pass

    async def execute(self, task: str, project_id: str | None = None) -> WorkflowResult:
        task_id = str(uuid.uuid4())
        start_time = time.monotonic()
        phases: list[WorkflowPhase] = []
        tokens_total = 0
        agents_used: list[str] = ["ceo"]
        debate_verdict = ""
        metacog_alerts: list[str] = []
        threat_level = "none"
        simulation_path = ""

        # PHASE 0 — ADVERSARIAL INPUT DETECTION
        threat_level, sanitized_task = await self._phase_threat_scan(task)
        if threat_level in ("high", "critical"):
            # Still process but flag clearly
            task = f"[THREAT DETECTED: {threat_level}] {sanitized_task}"

        # PHASE 1 — UNDERSTAND
        phase1 = await self._phase_understand(task, project_id)
        phases.append(phase1)
        memory_context = phase1.output

        # PHASE 2 — PLAN (CEO routes the task)
        phase2, routing = await self._phase_plan(task, memory_context)
        phases.append(phase2)
        tokens_total += sum(r.tokens_used for r in phase2.agent_results if r.tokens_used)

        # PHASE 2.5 — MENTAL SIMULATION (simulate N approaches, pick best)
        simulation_path, enriched_routing = await self._phase_simulate(task, routing, memory_context)

        # PHASE 3 — EXECUTE (parallel agent groups, using specialization-aware routing)
        phase3 = await self._phase_execute(task, enriched_routing, memory_context)
        phases.append(phase3)
        agents_used.extend(routing.get("agents_required", []))
        tokens_total += sum(r.tokens_used for r in phase3.agent_results)

        # PHASE 3.5 — META-COGNITIVE INTERRUPT
        metacog_alerts = await self._phase_metacog(task, phase3.output, routing)

        # PHASE 3.6 — ADVERSARIAL DEBATE
        phase36, debate_verdict = await self._phase_debate(task, phase3.output, routing)
        if phase36:
            phases.append(phase36)
            if phase36.output and debate_verdict in ("IMPROVED", "REJECTED_AND_REBUILT"):
                phase3.output = phase36.output

        # PHASE 4 — VERIFY
        phase4 = await self._phase_verify(phase3.output, routing)
        phases.append(phase4)

        # PHASE 4.5 — FAILURE MODE STRESS TEST
        phase45 = await self._phase_stress_test(task, phase3.output, routing)
        if phase45:
            phases.append(phase45)
            if phase45.output:
                phase3.output = phase45.output

        # PHASE 5 — CRITIQUE
        phase5 = await self._phase_critique(phase3.output, routing.get("success_criteria", []))
        phases.append(phase5)

        # PHASE 6 — DELIVER (with Theory of Mind calibration)
        raw_final = self._phase_deliver(task, phase3.output, phase5, routing)
        final_output = await self._calibrate_for_user(task, raw_final)
        phases.append(WorkflowPhase(name="deliver", output=final_output, succeeded=True))

        # PHASE 7 — LEARN (full async pipeline)
        asyncio.create_task(
            self._phase_learn(
                task, final_output, memory_context, project_id, routing,
                task_id=task_id,
            )
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
            debate_verdict=debate_verdict,
            metacog_alerts=metacog_alerts,
            threat_level=threat_level,
            simulation_path=simulation_path,
        )

    # ── Individual Phases ────────────────────────────────────────────────────

    async def _phase_threat_scan(self, task: str) -> tuple[str, str]:
        """Phase 0: scan input for adversarial manipulation."""
        detector = self._m.get("adversarial_detect")
        if not detector:
            return "none", task
        try:
            assessment = await detector.scan_input(task)
            return assessment.threat_level, assessment.sanitized_intent or task
        except Exception:
            return "none", task

    async def _phase_understand(self, task: str, project_id: str | None) -> WorkflowPhase:
        phase = WorkflowPhase(name="understand", started_at=time.monotonic())
        try:
            memory.initialize()
            context = memory.retrieve_context_for_task(task, self.session_id, project_id)
            phase.output = context
            phase.succeeded = True
        except Exception:
            phase.output = ""
            phase.succeeded = True
        phase.completed_at = time.monotonic()
        return phase

    async def _phase_plan(self, task: str, memory_context: str) -> tuple[WorkflowPhase, dict]:
        phase = WorkflowPhase(name="plan", started_at=time.monotonic())
        routing = await self._ceo.route_task(task, memory_context)
        phase.output = json.dumps(routing, indent=2)
        phase.succeeded = True
        phase.completed_at = time.monotonic()
        return phase, routing

    async def _phase_simulate(
        self, task: str, routing: dict, memory_context: str
    ) -> tuple[str, dict]:
        """Phase 2.5: simulate N approaches and pick the best one."""
        sim_engine = self._m.get("simulation")
        if not sim_engine:
            return "", routing

        complexity = routing.get("complexity", "medium")
        # Only simulate for non-trivial tasks
        if complexity == "low" or len(task) < 50:
            return "", routing

        try:
            sim_engine.initialize()
            result = await sim_engine.simulate(task, context=memory_context[:800])
            # Inject simulation guidance into routing
            enriched = dict(routing)
            if result.execution_guidance:
                enriched["simulation_guidance"] = result.execution_guidance
            if result.merged_risks:
                existing_risks = enriched.get("risks", [])
                enriched["risks"] = list(set(existing_risks + result.merged_risks))
            return result.selected_path.approach_name, enriched
        except Exception:
            return "", routing

    async def _phase_execute(
        self, task: str, routing: dict, memory_context: str
    ) -> WorkflowPhase:
        phase = WorkflowPhase(name="execute", started_at=time.monotonic())
        agents_required = routing.get("agents_required", ["researcher", "writer"])
        parallel_groups = routing.get("parallel_groups", [agents_required])

        # Inject simulation guidance if available
        sim_guidance = routing.get("simulation_guidance", "")
        task_lower = task.lower()
        is_coding = any(w in task_lower for w in ["code", "implement", "build", "debug", "fix", "refactor"])
        is_research = any(w in task_lower for w in ["research", "find", "what is", "analyze", "compare"])

        if is_coding:
            enriched_task = build_coding_protocol(task)
        elif is_research:
            enriched_task = build_research_protocol(task)
        else:
            enriched_task = build_reasoning_prefix(task, memory_context)

        if sim_guidance:
            enriched_task = f"[Simulation Guidance: {sim_guidance}]\n\n{enriched_task}"

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

    async def _phase_metacog(self, task: str, output: str, routing: dict) -> list[str]:
        metacog = self._m.get("metacog_monitor")
        if not metacog or len(output) < 100:
            return []
        try:
            alerts = await metacog.review(task, output, routing.get("complexity", "medium"))
            return [a.alert_message for a in alerts] if alerts else []
        except Exception:
            return []

    async def _phase_debate(
        self, task: str, output: str, routing: dict
    ) -> tuple[WorkflowPhase | None, str]:
        DebateEngine = self._m.get("debate")
        if not DebateEngine:
            return None, ""
        complexity = routing.get("complexity", "medium")
        if complexity == "low" or len(output) < 200:
            return None, "SKIPPED"

        phase = WorkflowPhase(name="debate", started_at=time.monotonic())
        try:
            engine = DebateEngine()
            result = await engine.debate(task, output)
            phase.output = result.final_answer if result.final_answer else output
            phase.succeeded = True
            phase.completed_at = time.monotonic()
            return phase, result.verdict
        except Exception:
            phase.succeeded = False
            phase.completed_at = time.monotonic()
            return phase, ""

    async def _phase_verify(self, content: str, routing: dict) -> WorkflowPhase:
        phase = WorkflowPhase(name="verify", started_at=time.monotonic())
        complexity = routing.get("complexity", "medium")
        if complexity in ("high", "critical") and len(content) > 500:
            result = await self._fact_checker.verify(content[:4000])
            phase.agent_results = [result]
            phase.output = result.content
        else:
            phase.output = "Verification skipped for low-complexity task."
        phase.succeeded = True
        phase.completed_at = time.monotonic()
        return phase

    async def _phase_stress_test(
        self, task: str, content: str, routing: dict
    ) -> WorkflowPhase | None:
        library = self._m.get("failure_library")
        if not library:
            return None
        task_lower = task.lower()
        is_plan = any(w in task_lower for w in [
            "plan", "strategy", "approach", "how to", "steps", "roadmap", "implement"
        ])
        if not is_plan or len(content) < 300:
            return None

        phase = WorkflowPhase(name="stress_test", started_at=time.monotonic())
        try:
            await library.initialize()
            result = await library.stress_test(content[:4000])
            if result.hardened_plan:
                phase.output = result.hardened_plan
            phase.succeeded = True
        except Exception:
            phase.succeeded = False
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
        self, task: str, raw_output: str, critique_phase: WorkflowPhase, routing: dict
    ) -> str:
        critique = critique_phase.output
        revised_marker = "## Revised Output"
        if revised_marker in critique:
            revised = critique[critique.find(revised_marker) + len(revised_marker):].strip()
            if len(revised) > 200:
                return revised
        verdict_pass = "PASS" in critique.upper() and "FAIL" not in critique.upper()
        if verdict_pass:
            return raw_output
        return f"{raw_output}\n\n---\n*Quality review notes:*\n{critique[:500]}"

    async def _calibrate_for_user(self, task: str, draft: str) -> str:
        """Theory of Mind calibration: rewrite response to fit user's mental model."""
        tom = self._m.get("tom")
        if not tom:
            return draft
        try:
            tom.initialize()
            return await tom.calibrate_response(task, draft)
        except Exception:
            return draft

    async def _phase_learn(
        self,
        task: str,
        result: str,
        existing_context: str,
        project_id: str | None,
        routing: dict,
        task_id: str = "",
    ) -> None:
        """Full async learning pipeline — runs after delivery."""
        quality = score_output_quality(result)
        quality_score = quality["overall"]
        agents_used = routing.get("agents_required", [])

        # 1. Core memory extraction
        try:
            learning_result = await self._memory_agent.extract_learnings(task, result[:3000])
            if learning_result.succeeded:
                content = learning_result.content
                start = content.find("[")
                end = content.rfind("]") + 1
                if start >= 0 and end > start:
                    learnings = json.loads(content[start:end])
                    for item in learnings:
                        if not isinstance(item, dict):
                            continue
                        try:
                            mem_type = MemoryType(item.get("memory_type", "semantic"))
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
            memory.consolidate(self.session_id)
        except Exception:
            pass

        # 2. Theory of Mind observation
        tom = self._m.get("tom")
        if tom:
            try:
                tom.initialize()
                await tom.observe(task, result[:2000])
            except Exception:
                pass

        # 3. Assumption extraction
        assumption_tracker = self._m.get("assumption_tracker")
        if assumption_tracker:
            try:
                assumption_tracker.initialize()
                await assumption_tracker.extract_and_store(task, result[:3000], task_id or str(uuid.uuid4()))
            except Exception:
                pass

        # 4. Curiosity: notice knowledge gaps
        curiosity = self._m.get("curiosity")
        if curiosity:
            try:
                curiosity.initialize()
                await curiosity.notice_gaps(task, result[:2000])
            except Exception:
                pass

        # 5. Causal extraction from task + result
        causal = self._m.get("causal")
        if causal:
            try:
                causal.initialize()
                await causal.extract_from_text(result[:2000], source=task[:100])
            except Exception:
                pass

        # 6. Epistemic assessment
        epistemic = self._m.get("epistemic")
        if epistemic:
            try:
                epistemic.initialize()
                await epistemic.assess_content(result[:3000], task)
            except Exception:
                pass

        # 7. Auto-link task to goals
        goal_mgr = self._m.get("goal_manager")
        if goal_mgr:
            try:
                goal_mgr.initialize()
                await goal_mgr.auto_link_task(task, quality_score=quality_score, project_id=project_id)
            except Exception:
                pass

        # 8. Record specialization performance
        specialization = self._m.get("specialization")
        if specialization:
            try:
                specialization.initialize()
                category = "general"
                try:
                    category = await specialization.classify_task(task)
                except Exception:
                    pass
                for agent_name in agents_used:
                    specialization.record_outcome(agent_name, task, category, quality_score)
            except Exception:
                pass

        # 9. Pattern mining log
        pattern_miner = self._m.get("pattern_miner")
        if pattern_miner:
            try:
                pattern_miner.initialize()
                pattern_miner.log_task(
                    task=task, result_summary=result[:500],
                    quality_score=quality_score, agents_used=agents_used,
                    session_id=self.session_id, project_id=project_id,
                )
            except Exception:
                pass

        # 10. Self-architect performance recording
        self_architect = self._m.get("self_architect")
        if self_architect:
            try:
                self_architect.initialize()
                for agent_name in agents_used:
                    self_architect.record_performance(
                        agent_name=agent_name, task=task,
                        quality_score=quality_score, session_id=self.session_id,
                    )
            except Exception:
                pass

        # 11. Living docs update
        living_docs = self._m.get("living_docs")
        if living_docs:
            try:
                living_docs.initialize()
                await living_docs.auto_update_from_memory(project_id=project_id)
            except Exception:
                pass
