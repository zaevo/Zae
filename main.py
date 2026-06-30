#!/usr/bin/env python3
"""
AIOS — AI Operating System
Entry point for interactive and programmatic use.

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
╔═══════════════════════════════════════════════════════════╗
║                                                           ║
║   ████████╗ █████╗ ███████╗                              ║
║      ███╔═╝██╔══██╗██╔════╝                              ║
║      ███║  ███████║█████╗                                ║
║      ███║  ██╔══██║██╔══╝                                ║
║      ███║  ██║  ██║███████╗                              ║
║      ╚══╝  ╚═╝  ╚═╝╚══════╝                             ║
║                                                           ║
║   AI Operating System v2.0                               ║
║   13 novel capabilities beyond single-model limits       ║
║                                                           ║
╚═══════════════════════════════════════════════════════════╝
"""

COMMANDS = """
Core Commands:
  /memory <query>       Search your memory
  /remember <text>      Store something to memory
  /project <id>         Set active project
  /stats                Show session statistics
  /agents               List available agents
  /help                 Show this message
  /exit                 Exit AIOS

Advanced Commands:
  /temporal <topic>     Analyze topic across 6 time horizons
  /premortem <plan>     Imagine the plan failed — why?
  /patterns             Mine cross-session behavioral patterns
  /archaeology <topic>  Trace root causes of past outcomes
  /beliefs              Show high-uncertainty Bayesian beliefs
  /belief <label> <p>   Add a belief node (e.g. /belief "market_fit" 0.7)
  /alerts               Check proactive intelligence monitor
  /improve              Trigger recursive self-architecture
  /docs                 List living documents
  /newdoc <title>       Create a living document (prompts for content)
"""

AGENTS_LIST = """
Active Agents:
  ceo              — Orchestrates all other agents, makes routing decisions
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
  vuln_researcher  — Deep CVE research, exploit analysis, bug bounty methodology

Novel Capabilities (auto-activated in workflow):
  Adversarial Debate       — Red/Blue team debates every answer before delivery
  Assumption Tracker       — Alerts when stored assumptions become invalid
  Failure Mode Library     — Stress-tests plans against known failure patterns
  Cognitive Fingerprinting — Models your reasoning biases and compensates
  Temporal Reasoning       — 6 vantage points: now → 5yr + pre-mortem
  Bayesian Belief Network  — Live probability propagation across beliefs
  Self-Architecture        — Rewrites agent prompts from performance data
  Pattern Mining           — Finds behavioral patterns across all sessions
  Proactive Monitor        — Watches projects for risks/opportunities 24/7
  Meta-Cognitive Monitor   — Interrupts bad reasoning before it completes
  Decision Archaeology     — Traces root causes to decision points
  Living Documentation     — Self-updating docs that track project state
"""


def print_result(result) -> None:
    print("\n" + "━" * 60)
    print(result.final_output)
    print("━" * 60)
    debate = f" | Debate: {result.debate_verdict}" if result.debate_verdict else ""
    print(
        f"\n[Quality: {result.quality_score:.0f}/100] "
        f"[Confidence: {result.confidence:.0%}] "
        f"[Agents: {', '.join(result.agents_used)}] "
        f"[Tokens: {result.tokens_used:,}] "
        f"[Time: {result.total_duration_ms/1000:.1f}s]{debate}"
    )
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
                print(f"[PROJECT] Active project set to: {arg}\n")

            elif cmd == "temporal":
                if not arg:
                    print("[ERROR] Usage: /temporal <topic>\n")
                else:
                    print("[TEMPORAL] Analyzing across 6 time horizons...\n")
                    result = await aios.temporal(arg)
                    print(result)
                    print()

            elif cmd == "premortem":
                if not arg:
                    print("[ERROR] Usage: /premortem <plan description>\n")
                else:
                    print("[PRE-MORTEM] Imagining failure...\n")
                    result = await aios.premortem(arg)
                    print(result)
                    print()

            elif cmd == "patterns":
                print("[PATTERNS] Mining cross-session patterns...\n")
                result = await aios.mine_patterns()
                print(result)
                print()

            elif cmd == "archaeology":
                if not arg:
                    print("[ERROR] Usage: /archaeology <topic or outcome to investigate>\n")
                else:
                    print("[ARCHAEOLOGY] Tracing root causes...\n")
                    result = await aios.investigate(arg)
                    print(result)
                    print()

            elif cmd == "beliefs":
                nodes = aios.get_uncertain_beliefs()
                if nodes:
                    print("\n[High-Uncertainty Beliefs]")
                    for n in nodes:
                        bar = "█" * int(n["probability"] * 20) + "░" * (20 - int(n["probability"] * 20))
                        print(f"  {n['label']:<40} [{bar}] {n['probability']:.0%}")
                        if n.get("evidence"):
                            print(f"    Evidence: {n['evidence'][:80]}")
                    print()
                else:
                    print("[BELIEFS] No high-uncertainty beliefs found. Add beliefs with /belief.\n")

            elif cmd == "belief":
                # /belief <label> <probability>
                belief_parts = arg.split(maxsplit=1)
                if len(belief_parts) < 2:
                    print("[ERROR] Usage: /belief <label> <probability 0.0-1.0>\n")
                else:
                    try:
                        label = belief_parts[0]
                        prob = float(belief_parts[1])
                        aios.add_belief(label, prob)
                        print(f"[BELIEF] Stored '{label}' = {prob:.0%}\n")
                    except ValueError:
                        print("[ERROR] Probability must be a number between 0 and 1.\n")

            elif cmd == "alerts":
                print("[ALERTS] Checking proactive monitor...\n")
                alerts = await aios.check_alerts()
                if alerts:
                    for a in alerts:
                        urgency_icon = {"IMMEDIATE": "🔴", "THIS_WEEK": "🟡", "THIS_MONTH": "🟢"}.get(a["urgency"], "⚪")
                        print(f"  {urgency_icon} [{a['type']}] {a['message']}")
                    print()
                else:
                    print("[ALERTS] No pending alerts.\n")

            elif cmd == "improve":
                print("[SELF-ARCHITECT] Analyzing agent performance and rewriting prompts...\n")
                result = await aios.trigger_improvement()
                print(result)
                print()

            elif cmd == "docs":
                docs = aios.list_living_docs()
                if docs:
                    print("\n[Living Documents]")
                    for d in docs:
                        print(f"  [{d['doc_id'][:8]}] v{d['version']} — {d['title']} (updated: {d['last_updated']})")
                    print()
                else:
                    print("[DOCS] No living documents yet. Create one with /newdoc <title>\n")

            elif cmd == "newdoc":
                if not arg:
                    print("[ERROR] Usage: /newdoc <title>\n")
                else:
                    print(f"Enter document content (end with a line containing only '---'):\n")
                    lines = []
                    while True:
                        try:
                            line = input()
                            if line.strip() == "---":
                                break
                            lines.append(line)
                        except (EOFError, KeyboardInterrupt):
                            break
                    content = "\n".join(lines)
                    result = await aios.create_living_doc(arg, content)
                    print(f"[DOCS] {result}\n")

            else:
                print(f"[AIOS] Unknown command: /{cmd}. Type /help for commands.\n")
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
        description="AIOS — AI Operating System v2.0",
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
