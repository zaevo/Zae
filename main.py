#!/usr/bin/env python3
"""
AIOS — AI Operating System v3.0
22 novel capabilities. The most advanced AI architecture you can run locally.

Usage:
    python main.py                          # Interactive REPL
    python main.py "Your task here"         # Single task
    python main.py --project myproject      # With project scope
    python main.py --stream "Your task"     # Streaming output
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


BANNER = """
╔═══════════════════════════════════════════════════════════════╗
║                                                               ║
║   ████████╗ █████╗ ███████╗                                  ║
║      ███╔═╝██╔══██╗██╔════╝                                  ║
║      ███║  ███████║█████╗                                     ║
║      ███║  ██╔══██║██╔══╝                                    ║
║      ███║  ██║  ██║███████╗                                  ║
║      ╚══╝  ╚═╝  ╚═╝╚══════╝                                 ║
║                                                               ║
║   AI Operating System v3.1                                   ║
║   23 capabilities — including live bug bounty hunting        ║
║                                                               ║
╚═══════════════════════════════════════════════════════════════╝
"""

COMMANDS = """
Core Commands:
  /memory <query>         Search your memory
  /remember <text>        Store something to memory
  /project <id>           Set active project
  /stats                  Show session statistics
  /agents                 List available agents
  /help                   Show this message
  /exit                   Exit AIOS

Intelligence Commands (Phase 2):
  /temporal <topic>       Analyze across 6 time horizons + pre-mortem
  /premortem <plan>       Imagine the plan failed — trace why
  /patterns               Mine cross-session behavioral patterns
  /archaeology <topic>    Trace root causes of past outcomes
  /beliefs                Show high-uncertainty Bayesian beliefs
  /belief <label> <p>     Add a belief node (e.g. /belief market_fit 0.7)
  /alerts                 Check proactive intelligence monitor
  /improve                Trigger recursive self-architecture
  /docs                   List living documents
  /newdoc <title>         Create a living document

Advanced Intelligence Commands (Phase 3):
  /simulate <task>        Run mental simulation — pick best approach
  /analogy <problem>      Find structural analogies in other domains
  /dream                  Run offline consolidation + insight synthesis
  /insights               Show recent dream insights
  /hypotheses             Show hypotheses generated in dream cycles
  /causal <X> <val> <Y>   Causal query: if I set X=val, what happens to Y?
  /blindspots <domain>    Find unknown unknowns in a domain
  /epistemic [domain]     Show structured knowledge map
  /goals                  Show goal hierarchy tree
  /goal <title>           Add a new goal (prompts for horizon)
  /reprioritize           AI reprioritizes goal tree
  /gaps                   Show open knowledge gaps (curiosity engine)
  /investigate            Autonomously investigate top knowledge gap
  /leaderboard            Show agent specialization rankings
  /whoami                 Show your Theory of Mind profile
  /threats                Show adversarial input detection stats
  /services               Start all background services

Bug Bounty Commands:
  /scope <program>        Analyze a program's scope (paste scope after prompt)
  /recon <domain>         Generate targeted recon plan for a domain
  /report                 Draft a professional bug report (describe finding)
  /triage                 Triage and prioritize your current findings list
  /track <sev> <prog>     Track a finding (e.g. /track High HackerOne/Acme)
  /update <id> <status>   Update finding status (submitted/valid/invalid/duplicate)
  /payout <id> <amount>   Record a payout for a finding
  /findings [program]     Show all tracked findings
  /bstats                 Show bug bounty hunting statistics
"""

AGENTS_LIST = """
Active Agents (15 specialized):
  ceo              — Routes and orchestrates all agents
  planner          — Task decomposition and execution planning
  researcher       — Multi-source research and evidence synthesis
  coder            — Production software engineering
  writer           — Executive-quality written deliverables
  analyst          — Data interpretation and quantitative reasoning
  scientist        — Hypothesis generation and causal inference
  critic           — Quality control and output improvement
  fact_checker     — Claims verification and hallucination detection
  memory_manager   — Memory retrieval and learning consolidation
  finance          — Financial analysis and modeling
  assistant        — Personal productivity and communications
  security         — Vulnerability auditing, threat modeling, pentest support
  vuln_researcher  — Deep CVE research, exploit analysis, bug bounty

Auto-Activated Pipeline (every task):
  Phase 0  Adversarial Input Detection — catches injection/manipulation
  Phase 1  Understand — retrieves relevant memory
  Phase 2  Plan — CEO routes to best agents
  Phase 2.5 Mental Simulation — simulates N approaches, picks best
  Phase 3  Execute — parallel agent execution
  Phase 3.5 Meta-Cognitive Monitor — catches reasoning failures
  Phase 3.6 Adversarial Debate — Red/Blue teams stress-test answer
  Phase 4  Verify — fact-checker validates claims
  Phase 4.5 Failure Mode Stress Test — hardens plans
  Phase 5  Critique — quality gate
  Phase 6  Deliver — Theory of Mind calibration for you specifically
  Phase 7  Learn (async) — 11 parallel learning subsystems

22 Novel Capabilities:
  Adversarial Debate       Red/Blue debate on every answer
  Assumption Tracker       Auto-invalidates stale assumptions
  Failure Mode Library     Stress-tests plans before delivery
  Cognitive Fingerprinting Bias detection + compensation
  Temporal Reasoning       6 time horizons + pre-mortem
  Bayesian Belief Network  Live probability propagation
  Self-Architecture        Rewrites agent prompts from perf data
  Pattern Mining           Cross-session behavioral patterns
  Proactive Monitor        Watches projects 24/7
  Meta-Cognitive Monitor   Interrupts bad reasoning
  Decision Archaeology     Root-cause traces outcomes
  Living Documentation     Self-updating docs
  Mental Simulation        N-path forward simulation
  Theory of Mind           Models your expertise + preferences
  Curiosity Engine         Autonomous knowledge gap investigation
  Causal World Model       do-calculus interventional reasoning
  Goal Hierarchy           Strategic-to-immediate goal tree
  Dream Consolidation      Offline synthesis + hypothesis generation
  Analogical Leap          Cross-domain structural isomorphism
  Emergent Specialization  Agents compete on track records
  Epistemic State Machine  KNOWN/BELIEVED/SUSPECTED/UNKNOWN map
  Adversarial Detection    Blocks prompt injection + manipulation
"""


def print_result(result) -> None:
    print("\n" + "━" * 62)
    print(result.final_output)
    print("━" * 62)
    parts = [
        f"Quality: {result.quality_score:.0f}/100",
        f"Confidence: {result.confidence:.0%}",
        f"Agents: {', '.join(result.agents_used)}",
        f"Tokens: {result.tokens_used:,}",
        f"Time: {result.total_duration_ms/1000:.1f}s",
    ]
    if result.debate_verdict and result.debate_verdict not in ("SKIPPED", ""):
        parts.append(f"Debate: {result.debate_verdict}")
    if result.threat_level and result.threat_level != "none":
        parts.append(f"Threat: {result.threat_level.upper()}")
    if result.simulation_path:
        parts.append(f"Path: {result.simulation_path}")
    print("\n[" + "] [".join(parts) + "]")
    if result.flags:
        print(f"[Flags: {', '.join(result.flags)}]")
    if result.metacog_alerts:
        print("[Meta-Cognitive Alerts]")
        for alert in result.metacog_alerts:
            print(f"  ! {alert}")
    print()


async def run_interactive(aios) -> None:
    print(BANNER)
    print("Type your task, or /help for commands. /exit to quit.\n")

    while True:
        try:
            user_input = input("AIOS > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n[AIOS] Session ended.")
            break

        if not user_input:
            continue

        if user_input.startswith("/"):
            parts = user_input[1:].split(maxsplit=1)
            cmd = parts[0].lower()
            arg = parts[1] if len(parts) > 1 else ""

            # ── Core ─────────────────────────────────────────────────────────
            if cmd == "exit":
                print("[AIOS] Session ended.")
                break

            elif cmd == "help":
                print(COMMANDS)

            elif cmd == "agents":
                print(AGENTS_LIST)

            elif cmd == "stats":
                stats = aios.stats
                for k, v in stats.items():
                    if isinstance(v, list):
                        print(f"  {k}: {', '.join(v)}")
                    else:
                        print(f"  {k}: {v}")
                print()

            elif cmd == "memory" and arg:
                results = aios.recall(arg, top_k=5)
                if results:
                    print("\n[Memory Results]")
                    for i, r in enumerate(results, 1):
                        print(f"  {i}. {r[:150]}")
                    print()
                else:
                    print("[MEMORY] No relevant memories found.\n")

            elif cmd == "remember" and arg:
                aios.remember(arg)
                print("[MEMORY] Stored.\n")

            elif cmd == "project" and arg:
                aios.set_project(arg)
                print(f"[PROJECT] Active project: {arg}\n")

            # ── Phase 2 Intelligence ──────────────────────────────────────────
            elif cmd == "temporal":
                if not arg:
                    print("[ERROR] Usage: /temporal <topic>\n")
                else:
                    print("[TEMPORAL] Analyzing across 6 time horizons...\n")
                    print(await aios.temporal(arg))
                    print()

            elif cmd == "premortem":
                if not arg:
                    print("[ERROR] Usage: /premortem <plan description>\n")
                else:
                    print("[PRE-MORTEM] Imagining failure...\n")
                    print(await aios.premortem(arg))
                    print()

            elif cmd == "patterns":
                print("[PATTERNS] Mining cross-session patterns...\n")
                print(await aios.mine_patterns())
                print()

            elif cmd == "archaeology":
                if not arg:
                    print("[ERROR] Usage: /archaeology <topic>\n")
                else:
                    print("[ARCHAEOLOGY] Tracing root causes...\n")
                    print(await aios.investigate(arg))
                    print()

            elif cmd == "beliefs":
                nodes = aios.get_uncertain_beliefs()
                if nodes:
                    print("\n[High-Uncertainty Beliefs]")
                    for n in nodes:
                        bar = "█" * int(n["probability"] * 20) + "░" * (20 - int(n["probability"] * 20))
                        print(f"  {n['label']:<40} [{bar}] {n['probability']:.0%}")
                    print()
                else:
                    print("[BELIEFS] No high-uncertainty beliefs. Add with /belief <label> <p>.\n")

            elif cmd == "belief":
                bp = arg.split(maxsplit=1)
                if len(bp) < 2:
                    print("[ERROR] Usage: /belief <label> <probability 0.0-1.0>\n")
                else:
                    try:
                        aios.add_belief(bp[0], float(bp[1]))
                        print(f"[BELIEF] '{bp[0]}' = {float(bp[1]):.0%}\n")
                    except ValueError:
                        print("[ERROR] Probability must be 0.0–1.0.\n")

            elif cmd == "alerts":
                print("[ALERTS] Checking proactive monitor...\n")
                alerts = await aios.check_alerts()
                if alerts:
                    icons = {"IMMEDIATE": "!", "THIS_WEEK": "~", "THIS_MONTH": "·"}
                    for a in alerts:
                        print(f"  {icons.get(a['urgency'], '?')} [{a['type']}] {a['message']}")
                    print()
                else:
                    print("[ALERTS] No pending alerts.\n")

            elif cmd == "improve":
                print("[SELF-ARCHITECT] Rewriting underperforming agent prompts...\n")
                print(await aios.trigger_improvement())
                print()

            elif cmd == "docs":
                docs = aios.list_living_docs()
                if docs:
                    print("\n[Living Documents]")
                    for d in docs:
                        print(f"  [{d['doc_id'][:8]}] v{d['version']} {d['title']} (updated: {d['last_updated']})")
                    print()
                else:
                    print("[DOCS] No documents. Create with /newdoc <title>\n")

            elif cmd == "newdoc":
                if not arg:
                    print("[ERROR] Usage: /newdoc <title>\n")
                else:
                    print("Enter content (end with '---' on its own line):\n")
                    lines = []
                    while True:
                        try:
                            line = input()
                            if line.strip() == "---":
                                break
                            lines.append(line)
                        except (EOFError, KeyboardInterrupt):
                            break
                    print(await aios.create_living_doc(arg, "\n".join(lines)))
                    print()

            # ── Phase 3 Intelligence ──────────────────────────────────────────
            elif cmd == "simulate":
                topic = arg or "the current task"
                print(f"[SIMULATE] Running mental simulation for: {topic}\n")
                print(await aios.simulate(topic))
                print()

            elif cmd == "analogy":
                if not arg:
                    print("[ERROR] Usage: /analogy <problem description>\n")
                else:
                    print("[ANALOGY] Searching for structural isomorphisms...\n")
                    print(await aios.find_analogies(arg))
                    print()

            elif cmd == "dream":
                print("[DREAM] Running offline consolidation cycle...\n")
                print(await aios.dream())
                print()

            elif cmd == "insights":
                insights = aios.get_dream_insights()
                if insights:
                    print("\n[Dream Insights]")
                    for i, ins in enumerate(insights, 1):
                        print(f"  {i}. [{ins['type']}] {ins['insight'][:120]}")
                        if ins.get("actionable") and ins.get("action_hint"):
                            print(f"     → {ins['action_hint'][:80]}")
                    print()
                else:
                    print("[INSIGHTS] No dream insights yet. Run /dream first.\n")

            elif cmd == "hypotheses":
                hyps = aios.get_hypotheses()
                if hyps:
                    print("\n[Generated Hypotheses]")
                    for i, h in enumerate(hyps, 1):
                        print(f"  {i}. {h['hypothesis'][:120]}")
                        if h.get("how_to_test"):
                            print(f"     Test: {h['how_to_test'][:80]}")
                    print()
                else:
                    print("[HYPOTHESES] No hypotheses generated yet. Run /dream.\n")

            elif cmd == "causal":
                # /causal <X> <value> <Y>
                cparts = arg.split(maxsplit=2)
                if len(cparts) < 3:
                    print("[ERROR] Usage: /causal <variable> <value> <target>\n")
                    print("  Example: /causal ad_spend doubled revenue\n")
                else:
                    print(f"[CAUSAL] Running do-query: do({cparts[0]}={cparts[1]}) → {cparts[2]}\n")
                    print(await aios.causal_query(cparts[0], cparts[1], cparts[2]))
                    print()

            elif cmd == "blindspots":
                if not arg:
                    print("[ERROR] Usage: /blindspots <domain>\n")
                else:
                    print(f"[BLIND SPOTS] Hunting unknown unknowns in '{arg}'...\n")
                    print(await aios.find_blind_spots(arg))
                    print()

            elif cmd == "epistemic":
                domain = arg if arg else None
                label = f" [{domain}]" if domain else ""
                print(f"[EPISTEMIC MAP{label}]\n")
                print(aios.get_epistemic_map(domain=domain))
                print()

            elif cmd == "goals":
                print("\n[Goal Hierarchy]")
                print(aios.get_goals())
                print()

            elif cmd == "goal":
                if not arg:
                    print("[ERROR] Usage: /goal <title>\n")
                else:
                    print(f"Horizon (immediate/tactical/strategic/visionary) [tactical]: ", end="")
                    try:
                        horizon = input().strip() or "tactical"
                    except (EOFError, KeyboardInterrupt):
                        horizon = "tactical"
                    print(aios.add_goal(arg, horizon=horizon))
                    print()

            elif cmd == "reprioritize":
                print("[GOALS] AI reprioritizing goal tree...\n")
                print(await aios.reprioritize_goals())
                print()

            elif cmd == "gaps":
                gaps = aios.get_open_questions()
                if gaps:
                    print("\n[Open Knowledge Gaps]")
                    for i, g in enumerate(gaps, 1):
                        print(f"  {i}. [{g['priority']:.1f}] ({g['domain']}) {g['question'][:100]}")
                    print()
                else:
                    print("[GAPS] No open knowledge gaps. They appear as you use AIOS.\n")

            elif cmd == "investigate":
                print("[CURIOSITY] Investigating top knowledge gap...\n")
                print(await aios.investigate_gap())
                print()

            elif cmd == "leaderboard":
                print(aios.get_agent_leaderboard())
                print()

            elif cmd == "whoami":
                print("\n[Your Theory of Mind Profile]")
                print(aios.get_user_model())
                print()

            elif cmd == "threats":
                stats = aios.get_threat_stats()
                if stats:
                    print("\n[Adversarial Detection Stats]")
                    for k, v in stats.items():
                        print(f"  {k}: {v}")
                    print()
                else:
                    print("[THREATS] No detection data yet.\n")

            elif cmd == "services":
                print("[SERVICES] Starting background services...\n")
                await aios.start_background_services()
                print("  ✓ Curiosity investigation (every 10 min)")
                print("  ✓ Dream consolidation (every 30 min)")
                print("  ✓ Proactive project monitor (every 30 min)\n")

            # ── Bug Bounty ────────────────────────────────────────────────────
            elif cmd == "scope":
                program_name = arg or ""
                print(f"Paste the program's scope policy (end with '---' on its own line):\n")
                lines = []
                while True:
                    try:
                        line = input()
                        if line.strip() == "---":
                            break
                        lines.append(line)
                    except (EOFError, KeyboardInterrupt):
                        break
                scope_text = "\n".join(lines)
                if scope_text.strip():
                    print("\n[BOUNTY] Analyzing scope...\n")
                    print(await aios.bounty_analyze(scope_text, program_name))
                    print()
                else:
                    print("[ERROR] No scope text provided.\n")

            elif cmd == "recon":
                if not arg:
                    print("[ERROR] Usage: /recon <target-domain>\n")
                else:
                    domain = arg.split()[0]
                    print(f"\n[BOUNTY] Generating recon plan for {domain}...\n")
                    print(await aios.bounty_recon(domain))
                    print()

            elif cmd == "report":
                print("Describe the vulnerability you found (end with '---' on its own line):\n")
                lines = []
                while True:
                    try:
                        line = input()
                        if line.strip() == "---":
                            break
                        lines.append(line)
                    except (EOFError, KeyboardInterrupt):
                        break
                finding = "\n".join(lines)
                if finding.strip():
                    prog = input("Program name (or press Enter to skip): ").strip()
                    sev = input("Your severity estimate (Critical/High/Medium/Low, or Enter): ").strip()
                    print("\n[BOUNTY] Drafting professional report...\n")
                    print(await aios.bounty_report(finding, program=prog, severity=sev))
                    print()
                else:
                    print("[ERROR] No finding description provided.\n")

            elif cmd == "triage":
                print("Enter your findings one per line (end with '---'):\n")
                lines = []
                while True:
                    try:
                        line = input()
                        if line.strip() == "---":
                            break
                        if line.strip():
                            lines.append(line.strip())
                    except (EOFError, KeyboardInterrupt):
                        break
                if lines:
                    print(f"\n[BOUNTY] Triaging {len(lines)} findings...\n")
                    print(await aios.bounty_triage(lines))
                    print()
                else:
                    print("[ERROR] No findings provided.\n")

            elif cmd == "track":
                # /track <severity> <program>
                tparts = arg.split(maxsplit=1) if arg else []
                if len(tparts) < 2:
                    print("[ERROR] Usage: /track <severity> <program>\n")
                    print("  Example: /track High HackerOne/Acme\n")
                else:
                    severity = tparts[0]
                    program = tparts[1]
                    try:
                        title = input("Finding title: ").strip()
                        desc = input("Brief description (optional): ").strip()
                    except (EOFError, KeyboardInterrupt):
                        title, desc = "Untitled", ""
                    print(aios.bounty_track(title, severity, program, description=desc))
                    print()

            elif cmd == "update":
                # /update <id> <status>
                uparts = arg.split(maxsplit=1) if arg else []
                if len(uparts) < 2:
                    print("[ERROR] Usage: /update <finding-id> <status>\n")
                    print("  Statuses: draft | submitted | triaged | valid | invalid | duplicate\n")
                else:
                    try:
                        fid = int(uparts[0])
                        status = uparts[1]
                        print(aios.bounty_update(fid, status=status))
                        print()
                    except ValueError:
                        print("[ERROR] Finding ID must be a number.\n")

            elif cmd == "payout":
                # /payout <id> <amount>
                pparts = arg.split(maxsplit=1) if arg else []
                if len(pparts) < 2:
                    print("[ERROR] Usage: /payout <finding-id> <amount>\n")
                else:
                    try:
                        fid = int(pparts[0])
                        amount = float(pparts[1].lstrip("$"))
                        print(aios.bounty_update(fid, payout=amount, status="valid"))
                        print(f"  Recorded ${amount:.2f} payout for finding #{fid}\n")
                    except ValueError:
                        print("[ERROR] Invalid ID or amount.\n")

            elif cmd == "findings":
                program_filter = arg if arg else None
                label = f" [{program_filter}]" if program_filter else ""
                print(f"\n[Bug Bounty Findings{label}]")
                print(aios.bounty_findings(program=program_filter))
                print()

            elif cmd == "bstats":
                stats = aios.bounty_stats()
                if stats:
                    print("\n[Bug Bounty Stats]")
                    print(f"  Total findings:  {stats['total_findings']}")
                    print(f"  Total earnings:  ${stats['total_payout']:.2f}")
                    if stats["by_severity"]:
                        print("  By severity:     " + " | ".join(
                            f"{k}: {v}" for k, v in stats["by_severity"].items()
                        ))
                    if stats["by_status"]:
                        print("  By status:       " + " | ".join(
                            f"{k}: {v}" for k, v in stats["by_status"].items()
                        ))
                    if stats["programs_hunted"]:
                        print(f"  Programs hunted: {', '.join(stats['programs_hunted'])}")
                    print()
                else:
                    print("[BSTATS] No data yet. Start hunting!\n")

            else:
                print(f"[AIOS] Unknown command: /{cmd}. Type /help.\n")
            continue

        # Execute task
        print(f"\n[AIOS] Processing...\n")
        try:
            result = await aios.run(user_input)
            print_result(result)
        except Exception as e:
            print(f"\n[ERROR] {e}\n")


async def run_single(aios, task: str, stream: bool = False) -> None:
    if stream:
        async for chunk in aios.run_stream(task):
            print(chunk, end="", flush=True)
        print()
    else:
        result = await aios.run(task)
        print_result(result)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="AIOS — AI Operating System v3.0",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=COMMANDS,
    )
    parser.add_argument("task", nargs="?", help="Task to execute (omit for interactive mode)")
    parser.add_argument("--project", "-p", help="Project ID for memory scoping")
    parser.add_argument("--session", "-s", help="Session ID to resume")
    parser.add_argument("--stream", action="store_true", help="Stream output phase by phase")
    args = parser.parse_args()

    try:
        from aios import AIOS
        aios_instance = AIOS(
            session_id=args.session,
            project_id=args.project,
        )
    except ValueError as e:
        print(f"[CONFIG ERROR] {e}")
        print("Copy .env.example to .env and set ANTHROPIC_API_KEY")
        sys.exit(1)

    if args.task:
        asyncio.run(run_single(aios_instance, args.task, stream=args.stream))
    else:
        asyncio.run(run_interactive(aios_instance))


if __name__ == "__main__":
    main()
