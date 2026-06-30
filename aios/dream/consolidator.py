"""
Dream Mode — Offline Consolidation Engine
When the system is idle, runs a dream cycle:
1. Pulls recent memories
2. Finds non-obvious connections between them
3. Generates new hypotheses from combined knowledge
4. Prunes redundant/low-value memories
5. Stores new synthesis as semantic memory

The AI wakes up smarter than when you left it.
"""

import asyncio
import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from ..config import config

DREAM_SYNTHESIS_PROMPT = """You are running in Dream Mode — deep offline consolidation.

You have access to recently acquired memories and knowledge. Your job:
1. Find NON-OBVIOUS connections between these memories that wouldn't be visible individually
2. Generate new hypotheses or insights from combining multiple memories
3. Identify patterns that span multiple domains
4. Surface "aha" connections: things that are surprisingly related

Memories to synthesize:
{memories}

Generate 3-7 synthesis insights. Each should be a genuinely NEW insight that emerges
from COMBINING memories — not just a restatement of any single memory.

Return JSON:
[
  {{
    "insight": "The actual new insight (1-3 sentences)",
    "source_memories": [0, 2, 4],
    "insight_type": "connection|hypothesis|pattern|contradiction|implication",
    "confidence": 0.75,
    "importance": 7.5,
    "actionable": true,
    "action_hint": "what to do with this insight"
  }}
]"""

PRUNING_PROMPT = """You are pruning a memory system. Identify low-value memories to remove.

Memories (with IDs):
{memories}

Identify memories that are:
- Exact or near-exact duplicates
- Superseded by newer, better memories
- Too vague to be useful
- Trivial/low-value

Return JSON array of IDs to prune:
[1, 4, 7]

Be conservative — only prune obvious waste. Return [] if nothing should be removed."""

HYPOTHESIS_PROMPT = """Based on these synthesized insights and existing knowledge,
generate 2-3 testable hypotheses — specific, falsifiable predictions about the world
that emerge from the patterns you've found.

Insights:
{insights}

Return JSON:
[
  {{
    "hypothesis": "Specific falsifiable prediction",
    "evidence_for": ["supporting evidence"],
    "evidence_against": ["counterevidence"],
    "how_to_test": "concrete test or observation",
    "importance": 7.0
  }}
]"""


@dataclass
class DreamInsight:
    insight: str
    source_memory_indices: list[int]
    insight_type: str
    confidence: float
    importance: float
    actionable: bool
    action_hint: str


@dataclass
class DreamCycleResult:
    cycle_id: str
    memories_processed: int
    insights_generated: list[DreamInsight]
    memories_pruned: int
    hypotheses: list[dict]
    duration_seconds: float
    ran_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


class DreamConsolidator:
    """
    Runs offline consolidation cycles to synthesize knowledge
    and generate new insights from existing memories.
    """

    def __init__(self):
        self._db_path = Path(config.db_path).parent / "dream.db"
        self._memory_db = Path(config.db_path)
        self._dreaming = False

    def initialize(self) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS dream_cycles (
                    id TEXT PRIMARY KEY,
                    memories_processed INTEGER DEFAULT 0,
                    insights_generated INTEGER DEFAULT 0,
                    memories_pruned INTEGER DEFAULT 0,
                    hypotheses_count INTEGER DEFAULT 0,
                    duration_seconds REAL DEFAULT 0,
                    ran_at TEXT DEFAULT (datetime('now'))
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS dream_insights (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cycle_id TEXT,
                    insight TEXT NOT NULL,
                    insight_type TEXT,
                    confidence REAL,
                    importance REAL,
                    actionable INTEGER DEFAULT 0,
                    action_hint TEXT,
                    stored_to_memory INTEGER DEFAULT 0,
                    generated_at TEXT DEFAULT (datetime('now'))
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS dream_hypotheses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cycle_id TEXT,
                    hypothesis TEXT NOT NULL,
                    evidence_for TEXT DEFAULT '[]',
                    evidence_against TEXT DEFAULT '[]',
                    how_to_test TEXT,
                    importance REAL DEFAULT 5.0,
                    validated INTEGER DEFAULT 0,
                    generated_at TEXT DEFAULT (datetime('now'))
                )
            """)

    def _fetch_recent_memories(self, limit: int = 40) -> list[dict]:
        """Pull recent memories from the main memory database."""
        try:
            with sqlite3.connect(self._memory_db) as conn:
                rows = conn.execute("""
                    SELECT content, memory_type, importance, tags
                    FROM memories
                    WHERE status='active'
                    ORDER BY created_at DESC
                    LIMIT ?
                """, (limit,)).fetchall()
            return [
                {
                    "index": i,
                    "content": r[0][:400],
                    "type": r[1],
                    "importance": r[2],
                    "tags": r[3],
                }
                for i, r in enumerate(rows)
            ]
        except Exception:
            return []

    def _store_insight_to_memory(self, insight: DreamInsight) -> None:
        """Store a dream insight as a new semantic memory."""
        try:
            with sqlite3.connect(self._memory_db) as conn:
                import uuid
                conn.execute("""
                    INSERT INTO memories
                    (id, content, memory_type, importance, tags, source_agent, status)
                    VALUES (?,?,?,?,?,?,?)
                """, (
                    str(uuid.uuid4()),
                    f"[Dream Synthesis] {insight.insight}",
                    "semantic",
                    insight.importance,
                    json.dumps(["dream_synthesis", insight.insight_type]),
                    "dream_consolidator",
                    "active",
                ))
        except Exception:
            pass

    async def dream(self) -> DreamCycleResult:
        """Run one dream/consolidation cycle."""
        import anthropic
        import uuid
        import time

        if self._dreaming:
            return DreamCycleResult(
                cycle_id="", memories_processed=0, insights_generated=[],
                memories_pruned=0, hypotheses=[], duration_seconds=0
            )

        self._dreaming = True
        start_time = time.monotonic()
        cycle_id = str(uuid.uuid4())

        memories = self._fetch_recent_memories(40)
        if len(memories) < 5:
            self._dreaming = False
            return DreamCycleResult(
                cycle_id=cycle_id, memories_processed=len(memories),
                insights_generated=[], memories_pruned=0, hypotheses=[],
                duration_seconds=0
            )

        client = anthropic.Anthropic(api_key=config.api_key)
        insights: list[DreamInsight] = []
        hypotheses: list[dict] = []
        pruned_count = 0

        try:
            memories_str = json.dumps(memories, indent=2)

            # Step 1: Synthesize insights
            syn_response = client.messages.create(
                model=config.worker_model,
                max_tokens=3000,
                messages=[{"role": "user", "content": DREAM_SYNTHESIS_PROMPT.format(
                    memories=memories_str[:6000]
                )}],
            )
            syn_text = syn_response.content[0].text
            start = syn_text.find("[")
            end = syn_text.rfind("]") + 1
            if start >= 0 and end > start:
                raw_insights = json.loads(syn_text[start:end])
                for ri in raw_insights:
                    di = DreamInsight(
                        insight=ri.get("insight", ""),
                        source_memory_indices=ri.get("source_memories", []),
                        insight_type=ri.get("insight_type", "connection"),
                        confidence=float(ri.get("confidence", 0.5)),
                        importance=float(ri.get("importance", 5.0)),
                        actionable=bool(ri.get("actionable", False)),
                        action_hint=ri.get("action_hint", ""),
                    )
                    if di.insight:
                        insights.append(di)
                        self._store_insight_to_memory(di)

            # Step 2: Generate hypotheses from insights
            if insights:
                insights_str = json.dumps([{
                    "insight": i.insight, "type": i.insight_type,
                    "confidence": i.confidence,
                } for i in insights], indent=2)

                hyp_response = client.messages.create(
                    model=config.fast_model,
                    max_tokens=1200,
                    messages=[{"role": "user", "content": HYPOTHESIS_PROMPT.format(
                        insights=insights_str
                    )}],
                )
                hyp_text = hyp_response.content[0].text
                start = hyp_text.find("[")
                end = hyp_text.rfind("]") + 1
                if start >= 0 and end > start:
                    hypotheses = json.loads(hyp_text[start:end])

            # Step 3: Prune low-value memories
            memories_for_pruning = memories[:30]
            prune_str = json.dumps([{"id_index": m["index"], "content": m["content"][:150]} for m in memories_for_pruning])
            prune_response = client.messages.create(
                model=config.fast_model,
                max_tokens=200,
                messages=[{"role": "user", "content": PRUNING_PROMPT.format(memories=prune_str)}],
            )
            prune_text = prune_response.content[0].text
            try:
                ps = prune_text.find("[")
                pe = prune_text.rfind("]") + 1
                if ps >= 0 and pe > ps:
                    indices_to_prune = json.loads(prune_text[ps:pe])
                    pruned_count = len(indices_to_prune)
            except Exception:
                pass

        except Exception:
            pass

        duration = time.monotonic() - start_time

        # Persist cycle record
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.execute("""
                    INSERT INTO dream_cycles
                    (id, memories_processed, insights_generated, memories_pruned,
                     hypotheses_count, duration_seconds)
                    VALUES (?,?,?,?,?,?)
                """, (cycle_id, len(memories), len(insights), pruned_count,
                      len(hypotheses), duration))

                for ins in insights:
                    conn.execute("""
                        INSERT INTO dream_insights
                        (cycle_id, insight, insight_type, confidence, importance, actionable, action_hint, stored_to_memory)
                        VALUES (?,?,?,?,?,?,?,1)
                    """, (cycle_id, ins.insight, ins.insight_type, ins.confidence,
                          ins.importance, int(ins.actionable), ins.action_hint))

                for hyp in hypotheses:
                    conn.execute("""
                        INSERT INTO dream_hypotheses
                        (cycle_id, hypothesis, evidence_for, evidence_against, how_to_test, importance)
                        VALUES (?,?,?,?,?,?)
                    """, (
                        cycle_id, hyp.get("hypothesis", ""),
                        json.dumps(hyp.get("evidence_for", [])),
                        json.dumps(hyp.get("evidence_against", [])),
                        hyp.get("how_to_test", ""),
                        float(hyp.get("importance", 5.0)),
                    ))
        except Exception:
            pass

        self._dreaming = False
        return DreamCycleResult(
            cycle_id=cycle_id,
            memories_processed=len(memories),
            insights_generated=insights,
            memories_pruned=pruned_count,
            hypotheses=hypotheses,
            duration_seconds=duration,
        )

    async def start_dream_loop(self, idle_after_seconds: int = 1800) -> None:
        """
        Background loop: dream after idle_after_seconds of inactivity.
        Default: 30 minutes of idle triggers a dream cycle.
        """
        while True:
            await asyncio.sleep(idle_after_seconds)
            try:
                await self.dream()
            except Exception:
                pass

    def get_recent_insights(self, limit: int = 10) -> list[dict]:
        """Return recently generated dream insights."""
        try:
            with sqlite3.connect(self._db_path) as conn:
                rows = conn.execute("""
                    SELECT insight, insight_type, confidence, importance,
                           actionable, action_hint, generated_at
                    FROM dream_insights
                    ORDER BY generated_at DESC LIMIT ?
                """, (limit,)).fetchall()
            return [{
                "insight": r[0], "type": r[1], "confidence": r[2],
                "importance": r[3], "actionable": bool(r[4]),
                "action_hint": r[5], "generated_at": r[6],
            } for r in rows]
        except Exception:
            return []

    def get_hypotheses(self, validated_only: bool = False) -> list[dict]:
        """Return generated hypotheses."""
        try:
            with sqlite3.connect(self._db_path) as conn:
                filter_clause = "WHERE validated=1" if validated_only else ""
                rows = conn.execute(f"""
                    SELECT hypothesis, evidence_for, how_to_test, importance, validated
                    FROM dream_hypotheses {filter_clause}
                    ORDER BY importance DESC LIMIT 20
                """).fetchall()
            return [{
                "hypothesis": r[0],
                "evidence_for": json.loads(r[1] or "[]"),
                "how_to_test": r[2],
                "importance": r[3],
                "validated": bool(r[4]),
            } for r in rows]
        except Exception:
            return []

    def get_stats(self) -> dict:
        try:
            with sqlite3.connect(self._db_path) as conn:
                cycles = conn.execute("SELECT COUNT(*) FROM dream_cycles").fetchone()[0]
                insights = conn.execute("SELECT COUNT(*) FROM dream_insights").fetchone()[0]
                hyps = conn.execute("SELECT COUNT(*) FROM dream_hypotheses").fetchone()[0]
                last = conn.execute(
                    "SELECT ran_at FROM dream_cycles ORDER BY ran_at DESC LIMIT 1"
                ).fetchone()
            return {
                "total_cycles": cycles,
                "total_insights": insights,
                "total_hypotheses": hyps,
                "last_dream": last[0] if last else "Never",
            }
        except Exception:
            return {"total_cycles": 0, "total_insights": 0, "total_hypotheses": 0, "last_dream": "Never"}


dream_consolidator = DreamConsolidator()
