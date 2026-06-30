"""
Bug Bounty Engine
Wraps the BugBountyHunterAgent with SQLite-backed finding tracking,
scope management, and recon state persistence.
"""

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from ..config import config
from .hunter import BugBountyHunterAgent
from ..agents.base import AgentResult


@dataclass
class Finding:
    title: str
    severity: str
    program: str
    description: str
    status: str = "draft"           # draft | submitted | triaged | valid | invalid | duplicate
    payout: float = 0.0
    report_url: str = ""
    notes: str = ""
    finding_id: int = 0
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class ScopeProfile:
    program_name: str
    scope_text: str
    analysis: str
    in_scope_domains: list[str] = field(default_factory=list)
    out_of_scope: list[str] = field(default_factory=list)
    profile_id: int = 0
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


class BugBountyEngine:
    """
    End-to-end bug bounty hunting engine.
    Combines AI-powered analysis with persistent finding tracking.
    """

    def __init__(self):
        self._db_path = Path(config.db_path).parent / "bounty.db"
        self._hunter = BugBountyHunterAgent()

    def initialize(self) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS findings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    severity TEXT DEFAULT 'Medium',
                    program TEXT DEFAULT '',
                    description TEXT DEFAULT '',
                    status TEXT DEFAULT 'draft',
                    payout REAL DEFAULT 0.0,
                    report_url TEXT DEFAULT '',
                    notes TEXT DEFAULT '',
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now'))
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS scope_profiles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    program_name TEXT NOT NULL,
                    scope_text TEXT DEFAULT '',
                    analysis TEXT DEFAULT '',
                    in_scope_domains TEXT DEFAULT '[]',
                    out_of_scope TEXT DEFAULT '[]',
                    created_at TEXT DEFAULT (datetime('now'))
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS recon_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    program TEXT NOT NULL,
                    target_domain TEXT NOT NULL,
                    recon_plan TEXT DEFAULT '',
                    notes TEXT DEFAULT '',
                    started_at TEXT DEFAULT (datetime('now'))
                )
            """)

    async def analyze_program(self, scope_text: str, program_name: str = "") -> str:
        """
        Analyze a bug bounty program's scope policy.
        Returns attack surface map + prioritized testing queue.
        """
        result = await self._hunter.analyze_scope(scope_text, program_name)

        if result.succeeded:
            # Persist the scope profile
            with sqlite3.connect(self._db_path) as conn:
                conn.execute("""
                    INSERT INTO scope_profiles (program_name, scope_text, analysis)
                    VALUES (?, ?, ?)
                """, (program_name or "unknown", scope_text[:2000], result.content))
            return result.content
        return f"Scope analysis failed: {result.error}"

    async def plan_recon(self, target_domain: str, program: str = "", scope_context: str = "") -> str:
        """
        Generate a targeted recon plan for a domain within a bug bounty program.
        """
        result = await self._hunter.plan_recon(target_domain, scope_context)

        if result.succeeded:
            with sqlite3.connect(self._db_path) as conn:
                conn.execute("""
                    INSERT INTO recon_sessions (program, target_domain, recon_plan)
                    VALUES (?, ?, ?)
                """, (program or "unknown", target_domain, result.content))
            return result.content
        return f"Recon planning failed: {result.error}"

    async def draft_report(
        self, finding_description: str, program: str = "", severity: str = ""
    ) -> str:
        """
        Draft a professional bug bounty report from a finding description.
        """
        result = await self._hunter.draft_report(finding_description, program, severity)
        return result.content if result.succeeded else f"Report drafting failed: {result.error}"

    async def triage(self, findings: list[str]) -> str:
        """Triage and prioritize a list of potential findings."""
        result = await self._hunter.triage_findings(findings)
        return result.content if result.succeeded else f"Triage failed: {result.error}"

    def track_finding(
        self,
        title: str,
        severity: str,
        program: str,
        description: str = "",
        status: str = "draft",
    ) -> Finding:
        """Persist a finding to the tracking database."""
        with sqlite3.connect(self._db_path) as conn:
            cursor = conn.execute("""
                INSERT INTO findings (title, severity, program, description, status)
                VALUES (?, ?, ?, ?, ?)
            """, (title, severity, program, description, status))
            finding_id = cursor.lastrowid
        return Finding(
            title=title, severity=severity, program=program,
            description=description, status=status, finding_id=finding_id,
        )

    def update_finding(
        self,
        finding_id: int,
        status: str | None = None,
        payout: float | None = None,
        report_url: str | None = None,
        notes: str | None = None,
    ) -> bool:
        """Update an existing finding's status, payout, or notes."""
        fields = []
        values = []
        if status is not None:
            fields.append("status = ?")
            values.append(status)
        if payout is not None:
            fields.append("payout = ?")
            values.append(payout)
        if report_url is not None:
            fields.append("report_url = ?")
            values.append(report_url)
        if notes is not None:
            fields.append("notes = ?")
            values.append(notes)
        if not fields:
            return False
        fields.append("updated_at = datetime('now')")
        values.append(finding_id)
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                f"UPDATE findings SET {', '.join(fields)} WHERE id = ?",
                values,
            )
        return True

    def get_findings(
        self, program: str | None = None, status: str | None = None
    ) -> list[Finding]:
        """Return all tracked findings, optionally filtered by program or status."""
        query = "SELECT id, title, severity, program, description, status, payout, report_url, notes, created_at, updated_at FROM findings"
        params: list = []
        conditions = []
        if program:
            conditions.append("program = ?")
            params.append(program)
        if status:
            conditions.append("status = ?")
            params.append(status)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY created_at DESC"
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(query, params).fetchall()
        return [
            Finding(
                finding_id=r[0], title=r[1], severity=r[2], program=r[3],
                description=r[4], status=r[5], payout=r[6],
                report_url=r[7], notes=r[8],
                created_at=r[9], updated_at=r[10],
            )
            for r in rows
        ]

    def get_stats(self) -> dict:
        """Return high-level stats on the hunting session."""
        with sqlite3.connect(self._db_path) as conn:
            total = conn.execute("SELECT COUNT(*) FROM findings").fetchone()[0]
            by_status = dict(conn.execute(
                "SELECT status, COUNT(*) FROM findings GROUP BY status"
            ).fetchall())
            by_severity = dict(conn.execute(
                "SELECT severity, COUNT(*) FROM findings GROUP BY severity"
            ).fetchall())
            total_payout = conn.execute(
                "SELECT COALESCE(SUM(payout), 0) FROM findings"
            ).fetchone()[0]
            programs = conn.execute(
                "SELECT DISTINCT program FROM findings WHERE program != ''"
            ).fetchall()
        return {
            "total_findings": total,
            "by_status": by_status,
            "by_severity": by_severity,
            "total_payout": total_payout,
            "programs_hunted": [p[0] for p in programs],
        }

    def format_findings_table(self, findings: list[Finding]) -> str:
        if not findings:
            return "No findings tracked yet."
        sev_icons = {"Critical": "!!!!", "High": "!!!", "Medium": "!!", "Low": "!"}
        lines = [f"{'#':<4} {'Severity':<10} {'Status':<12} {'Program':<20} {'Title'}"]
        lines.append("─" * 72)
        for f in findings:
            icon = sev_icons.get(f.severity, "?")
            payout_str = f" (${f.payout:.0f})" if f.payout > 0 else ""
            lines.append(
                f"{f.finding_id:<4} {f.severity:<10} {f.status:<12} "
                f"{f.program[:18]:<20} {f.title[:40]}{payout_str}"
            )
        return "\n".join(lines)


bounty_engine = BugBountyEngine()
