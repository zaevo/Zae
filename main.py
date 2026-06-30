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

# Make sure we can import from project root
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
║   AI Operating System v1.0                               ║
║   Exceeding single-model limits through architecture     ║
║                                                           ║
╚═══════════════════════════════════════════════════════════╝
"""

COMMANDS = """
Commands:
  /memory <query>    Search your memory
  /remember <text>   Store something to memory
  /project <id>      Set active project
  /stats             Show session statistics
  /agents            List available agents
  /help              Show this message
  /exit              Exit AIOS
"""

AGENTS_LIST = """
Active Agents:
  ceo            — Orchestrates all other agents, makes routing decisions
  planner        — Task decomposition and execution planning
  researcher     — Multi-source research and evidence synthesis
  coder          — Production software engineering
  writer         — Executive-quality written deliverables
  analyst        — Data interpretation and quantitative reasoning
  scientist      — Hypothesis generation and causal inference
  critic         — Quality control and output improvement
  fact_checker   — Claims verification and hallucination detection
  memory_manager — Memory retrieval and learning consolidation
  finance        — Financial analysis and modeling
  assistant      — Personal productivity and communications
  security       — Vulnerability auditing, threat modeling, pentest support, hardening
  vuln_researcher — Deep CVE research, exploit analysis, bug bounty methodology
"""


def print_result(result) -> None:
    """Pretty-print a WorkflowResult."""
    print("\n" + "━" * 60)
    print(result.final_output)
    print("━" * 60)
    print(
        f"\n[Quality: {result.quality_score:.0f}/100] "
        f"[Confidence: {result.confidence:.0%}] "
        f"[Agents: {', '.join(result.agents_used)}] "
        f"[Tokens: {result.tokens_used:,}] "
        f"[Time: {result.total_duration_ms/1000:.1f}s]"
    )
    if result.flags:
        print(f"[Flags: {', '.join(result.flags)}]")
    print()


async def run_interactive(aios) -> None:
    """Interactive REPL."""
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

        # Handle commands
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
            else:
                print(f"[AIOS] Unknown command: /{cmd}\n")
            continue

        # Execute task
        print(f"\n[AIOS] Processing...\n")
        try:
            result = await aios.run(user_input)
            print_result(result)
        except Exception as e:
            print(f"\n[ERROR] {e}\n")


async def run_single(aios, task: str, stream: bool = False) -> None:
    """Run a single task and exit."""
    if stream:
        async for chunk in aios.run_stream(task):
            print(chunk, end="", flush=True)
        print()
    else:
        result = await aios.run(task)
        print_result(result)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="AIOS — AI Operating System",
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
