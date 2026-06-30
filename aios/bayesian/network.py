"""
Bayesian Belief Network

A live probability network that connects all stored knowledge.
When one fact updates, every belief that depends on it updates automatically.

This turns static memories into a living, self-updating knowledge system.
"""

import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from ..config import config


@dataclass
class BeliefNode:
    id: str
    label: str
    description: str
    probability: float          # 0.0 to 1.0
    confidence: float           # How certain we are of this probability
    evidence_for: list[str]     # Evidence supporting this belief
    evidence_against: list[str] # Evidence against this belief
    tags: list[str]
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    domain: str = "general"


@dataclass
class BeliefEdge:
    id: str
    source_id: str              # Parent belief
    target_id: str              # Child belief
    relationship: str           # "supports" | "undermines" | "requires" | "suggests"
    strength: float             # 0.0 to 1.0 — how strongly parent affects child
    direction: float            # +1.0 = positive correlation, -1.0 = negative


@dataclass
class BeliefUpdate:
    node_id: str
    old_probability: float
    new_probability: float
    reason: str
    cascade_updates: list[dict]  # downstream nodes that also changed


class BayesianBeliefNetwork:
    """
    Maintains a graph of interconnected beliefs with probability scores.
    New evidence automatically propagates through the network.

    Example:
    - Belief: "Restaurant market in Atlanta is growing" (p=0.8)
    - Belief: "BTJ Wings expansion is viable" (p=0.7)
    - Edge: market_growth → expansion_viable (strength=0.6)
    - New fact: "Atlanta restaurant market down 15%"
    - → market_growth probability drops to 0.3
    - → expansion_viable automatically drops to 0.4
    - → AIOS alerts: "The expansion plan's viability has been updated"
    """

    def __init__(self):
        self._conn: sqlite3.Connection | None = None
        self._initialized = False

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            db_path = config.db_path
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def initialize(self) -> None:
        if self._initialized:
            return
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS belief_nodes (
                id TEXT PRIMARY KEY,
                label TEXT NOT NULL,
                description TEXT,
                probability REAL NOT NULL DEFAULT 0.5,
                confidence REAL DEFAULT 0.5,
                evidence_for TEXT DEFAULT '[]',
                evidence_against TEXT DEFAULT '[]',
                tags TEXT DEFAULT '[]',
                domain TEXT DEFAULT 'general',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS belief_edges (
                id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL,
                target_id TEXT NOT NULL,
                relationship TEXT DEFAULT 'supports',
                strength REAL DEFAULT 0.5,
                direction REAL DEFAULT 1.0,
                FOREIGN KEY(source_id) REFERENCES belief_nodes(id),
                FOREIGN KEY(target_id) REFERENCES belief_nodes(id)
            );

            CREATE TABLE IF NOT EXISTS belief_history (
                id TEXT PRIMARY KEY,
                node_id TEXT NOT NULL,
                old_probability REAL,
                new_probability REAL,
                reason TEXT,
                changed_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_bn_domain ON belief_nodes(domain);
            CREATE INDEX IF NOT EXISTS idx_be_source ON belief_edges(source_id);
            CREATE INDEX IF NOT EXISTS idx_be_target ON belief_edges(target_id);
        """)
        conn.commit()
        self._initialized = True

    def add_belief(
        self,
        label: str,
        probability: float,
        description: str = "",
        evidence_for: list[str] | None = None,
        evidence_against: list[str] | None = None,
        tags: list[str] | None = None,
        domain: str = "general",
        confidence: float = 0.5,
    ) -> BeliefNode:
        if not self._initialized:
            self.initialize()

        now = datetime.utcnow().isoformat()
        node = BeliefNode(
            id=str(uuid.uuid4()),
            label=label,
            description=description,
            probability=max(0.0, min(1.0, probability)),
            confidence=max(0.0, min(1.0, confidence)),
            evidence_for=evidence_for or [],
            evidence_against=evidence_against or [],
            tags=tags or [],
            domain=domain,
        )
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO belief_nodes
               (id, label, description, probability, confidence,
                evidence_for, evidence_against, tags, domain, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                node.id, node.label, node.description, node.probability,
                node.confidence, json.dumps(node.evidence_for),
                json.dumps(node.evidence_against), json.dumps(node.tags),
                node.domain, now, now,
            ),
        )
        conn.commit()
        return node

    def link_beliefs(
        self,
        source_id: str,
        target_id: str,
        relationship: str = "supports",
        strength: float = 0.5,
        direction: float = 1.0,
    ) -> BeliefEdge:
        if not self._initialized:
            self.initialize()

        edge = BeliefEdge(
            id=str(uuid.uuid4()),
            source_id=source_id,
            target_id=target_id,
            relationship=relationship,
            strength=max(0.0, min(1.0, strength)),
            direction=direction,
        )
        conn = self._get_conn()
        conn.execute(
            """INSERT OR REPLACE INTO belief_edges
               (id, source_id, target_id, relationship, strength, direction)
               VALUES (?,?,?,?,?,?)""",
            (edge.id, edge.source_id, edge.target_id,
             edge.relationship, edge.strength, edge.direction),
        )
        conn.commit()
        return edge

    def update_belief(
        self,
        node_id: str,
        new_probability: float,
        evidence: str = "",
        cascade: bool = True,
    ) -> BeliefUpdate:
        if not self._initialized:
            self.initialize()

        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM belief_nodes WHERE id = ?", (node_id,)
        ).fetchone()
        if not row:
            raise ValueError(f"Belief node {node_id} not found")

        old_prob = row["probability"]
        new_prob = max(0.0, min(1.0, new_probability))
        delta = new_prob - old_prob
        now = datetime.utcnow().isoformat()

        # Update node
        conn.execute(
            "UPDATE belief_nodes SET probability = ?, updated_at = ? WHERE id = ?",
            (new_prob, now, node_id),
        )

        # Record history
        conn.execute(
            "INSERT INTO belief_history (id, node_id, old_probability, new_probability, reason, changed_at) VALUES (?,?,?,?,?,?)",
            (str(uuid.uuid4()), node_id, old_prob, new_prob, evidence[:500], now),
        )
        conn.commit()

        cascade_updates = []
        if cascade and abs(delta) > 0.05:
            cascade_updates = self._cascade_update(node_id, delta, visited={node_id})

        return BeliefUpdate(
            node_id=node_id,
            old_probability=old_prob,
            new_probability=new_prob,
            reason=evidence,
            cascade_updates=cascade_updates,
        )

    def _cascade_update(
        self, source_id: str, delta: float, visited: set, depth: int = 0
    ) -> list[dict]:
        if depth > 4:  # Max cascade depth
            return []

        conn = self._get_conn()
        edges = conn.execute(
            "SELECT * FROM belief_edges WHERE source_id = ?", (source_id,)
        ).fetchall()

        updates = []
        for edge in edges:
            target_id = edge["target_id"]
            if target_id in visited:
                continue
            visited.add(target_id)

            target = conn.execute(
                "SELECT * FROM belief_nodes WHERE id = ?", (target_id,)
            ).fetchone()
            if not target:
                continue

            # Bayesian update: child shifts proportional to parent delta × edge strength × direction
            child_delta = delta * edge["strength"] * edge["direction"]
            new_prob = max(0.01, min(0.99, target["probability"] + child_delta))

            conn.execute(
                "UPDATE belief_nodes SET probability = ?, updated_at = ? WHERE id = ?",
                (new_prob, datetime.utcnow().isoformat(), target_id),
            )
            updates.append({
                "node_id": target_id,
                "label": target["label"],
                "old_probability": target["probability"],
                "new_probability": new_prob,
                "reason": f"Cascaded from parent update (strength={edge['strength']:.2f})",
            })
            # Recurse
            updates.extend(self._cascade_update(target_id, child_delta, visited, depth + 1))

        conn.commit()
        return updates

    def query_beliefs(
        self,
        domain: str | None = None,
        min_probability: float = 0.0,
        max_probability: float = 1.0,
        tags: list[str] | None = None,
    ) -> list[BeliefNode]:
        if not self._initialized:
            self.initialize()

        conn = self._get_conn()
        query = "SELECT * FROM belief_nodes WHERE probability BETWEEN ? AND ?"
        params: list[Any] = [min_probability, max_probability]
        if domain:
            query += " AND domain = ?"
            params.append(domain)
        query += " ORDER BY confidence DESC, probability DESC LIMIT 50"

        rows = conn.execute(query, params).fetchall()
        nodes = [self._row_to_node(r) for r in rows]

        if tags:
            tag_set = set(tags)
            nodes = [n for n in nodes if tag_set.intersection(set(n.tags))]
        return nodes

    def get_high_uncertainty_beliefs(self) -> list[BeliefNode]:
        """Beliefs near 50% probability — most in need of more evidence."""
        if not self._initialized:
            self.initialize()
        conn = self._get_conn()
        rows = conn.execute(
            """SELECT * FROM belief_nodes
               WHERE probability BETWEEN 0.35 AND 0.65
               ORDER BY confidence ASC LIMIT 10"""
        ).fetchall()
        return [self._row_to_node(r) for r in rows]

    def get_network_summary(self) -> str:
        if not self._initialized:
            self.initialize()
        conn = self._get_conn()
        total = conn.execute("SELECT COUNT(*) FROM belief_nodes").fetchone()[0]
        high_conf = conn.execute(
            "SELECT COUNT(*) FROM belief_nodes WHERE probability > 0.7 AND confidence > 0.6"
        ).fetchone()[0]
        uncertain = conn.execute(
            "SELECT COUNT(*) FROM belief_nodes WHERE probability BETWEEN 0.35 AND 0.65"
        ).fetchone()[0]
        edges = conn.execute("SELECT COUNT(*) FROM belief_edges").fetchone()[0]
        return (
            f"Belief Network: {total} beliefs, {edges} connections\n"
            f"High confidence (p>0.7): {high_conf} | Uncertain (0.35-0.65): {uncertain}"
        )

    def _row_to_node(self, row: sqlite3.Row) -> BeliefNode:
        return BeliefNode(
            id=row["id"],
            label=row["label"],
            description=row["description"] or "",
            probability=row["probability"],
            confidence=row["confidence"],
            evidence_for=json.loads(row["evidence_for"] or "[]"),
            evidence_against=json.loads(row["evidence_against"] or "[]"),
            tags=json.loads(row["tags"] or "[]"),
            domain=row["domain"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )


belief_network = BayesianBeliefNetwork()
