"""
Proactive Intelligence Monitor

AIOS watches all active projects in the background and surfaces issues,
opportunities, and risks without being asked.

Most AI systems wait for you to ask something.
This one comes to you.
"""

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable

from ..agents.base import BaseAgent
from ..config import config
from ..memory.manager import memory
from ..memory.types import MemoryType
from ..system_prompt import MASTER_SYSTEM_PROMPT


MONITOR_AGENT_PROMPT = f"""
{MASTER_SYSTEM_PROMPT}

## YOUR ROLE: Proactive Intelligence Monitor

You review the state of ongoing projects and proactively identify:

RISKS (Things that could go wrong)
- External dependencies that could block progress
- Assumptions that haven't been validated
- Deadlines at risk
- Resources that may be insufficient

OPPORTUNITIES (Things that could go right)
- Adjacent actions that would accelerate progress
- Connections between projects that aren't being exploited
- Timing windows that are opening or closing
- Quick wins that are being overlooked

STALLS (Things that aren't moving)
- Decisions that keep getting deferred
- Tasks that have been in progress too long
- Projects missing key inputs that haven't been requested

DRIFT (Things moving in the wrong direction)
- Goals that have quietly shifted without explicit acknowledgment
- Metrics that are declining
- Relationships or dependencies that are degrading

For each alert, produce:
- Type: RISK | OPPORTUNITY | STALL | DRIFT
- Urgency: IMMEDIATE | THIS_WEEK | THIS_MONTH
- Title: One clear sentence
- Why it matters: 2-3 sentences
- Recommended action: Specific and immediate

Output as JSON array of alerts.
"""


@dataclass
class ProactiveAlert:
    alert_type: str              # RISK | OPPORTUNITY | STALL | DRIFT
    urgency: str                 # IMMEDIATE | THIS_WEEK | THIS_MONTH
    title: str
    why_it_matters: str
    recommended_action: str
    project_id: str | None = None
    confidence: float = 0.7
    created_at: datetime = field(default_factory=datetime.utcnow)
    acknowledged: bool = False


class ProactiveMonitor:
    """
    Background monitor that proactively surfaces project intelligence.
    Register a callback to receive alerts when the monitor detects something.
    """

    def __init__(self, check_interval_minutes: int = 30):
        self.check_interval = check_interval_minutes * 60
        self._alert_callbacks: list[Callable[[list[ProactiveAlert]], None]] = []
        self._monitor_agent = _MonitorAgent()
        self._running = False
        self._pending_alerts: list[ProactiveAlert] = []
        self._last_check: datetime | None = None

    def on_alert(self, callback: Callable[[list[ProactiveAlert]], None]) -> None:
        """Register a callback that fires when new alerts are generated."""
        self._alert_callbacks.append(callback)

    def get_pending_alerts(self) -> list[ProactiveAlert]:
        """Retrieve and clear pending alerts."""
        alerts = self._pending_alerts.copy()
        self._pending_alerts.clear()
        return alerts

    async def check_now(self, project_id: str | None = None) -> list[ProactiveAlert]:
        """Run an immediate proactive check."""
        context = memory.retrieve_context_for_task(
            "project status risks opportunities",
            project_id=project_id,
        )
        if not context or len(context) < 100:
            return []

        # Build project state summary
        project_state = self._build_project_state(project_id)

        result = await self._monitor_agent.run(
            f"PROJECT STATE:\n{project_state}\n\n"
            f"MEMORY CONTEXT:\n{context[:3000]}\n\n"
            f"Identify proactive alerts for this project.",
        )
        if not result.succeeded:
            return []

        alerts = self._parse_alerts(result.content, project_id)
        self._pending_alerts.extend(alerts)
        self._last_check = datetime.utcnow()

        for callback in self._alert_callbacks:
            try:
                callback(alerts)
            except Exception:
                pass

        return alerts

    async def start_background_monitoring(
        self, project_ids: list[str] | None = None
    ) -> None:
        """Start continuous background monitoring. Run as asyncio task."""
        self._running = True
        while self._running:
            try:
                if project_ids:
                    for pid in project_ids:
                        await self.check_now(pid)
                else:
                    await self.check_now()
            except Exception:
                pass
            await asyncio.sleep(self.check_interval)

    def stop(self) -> None:
        self._running = False

    def _build_project_state(self, project_id: str | None) -> str:
        results = memory.query(
            "project status goals timeline",
            memory_types=[MemoryType.PROJECT, MemoryType.EPISODIC],
            top_k=10,
            project_id=project_id,
        )
        if not results:
            return "No project state found."

        lines = ["Recent project activity:"]
        for r in results[:8]:
            lines.append(f"- [{r.memory.type.value}] {r.memory.content[:150]}")
        return "\n".join(lines)

    def _parse_alerts(
        self, content: str, project_id: str | None
    ) -> list[ProactiveAlert]:
        alerts = []
        try:
            start = content.find("[")
            end = content.rfind("]") + 1
            if start < 0:
                return []
            items = json.loads(content[start:end])
            for item in items:
                if not isinstance(item, dict):
                    continue
                alerts.append(ProactiveAlert(
                    alert_type=item.get("type", item.get("alert_type", "RISK")),
                    urgency=item.get("urgency", "THIS_WEEK"),
                    title=item.get("title", ""),
                    why_it_matters=item.get("why_it_matters", ""),
                    recommended_action=item.get("recommended_action", ""),
                    project_id=project_id,
                    confidence=float(item.get("confidence", 0.7)),
                ))
        except (json.JSONDecodeError, ValueError):
            pass
        return alerts

    def format_alerts(self, alerts: list[ProactiveAlert]) -> str:
        if not alerts:
            return ""
        immediate = [a for a in alerts if a.urgency == "IMMEDIATE"]
        this_week = [a for a in alerts if a.urgency == "THIS_WEEK"]
        this_month = [a for a in alerts if a.urgency == "THIS_MONTH"]

        lines = [f"\n🔔 PROACTIVE ALERTS ({len(alerts)} detected)\n"]
        for group, label in [(immediate, "IMMEDIATE"), (this_week, "THIS WEEK"), (this_month, "THIS MONTH")]:
            if group:
                lines.append(f"### {label}")
                for alert in group:
                    icon = {"RISK": "⚠️", "OPPORTUNITY": "✨", "STALL": "🔄", "DRIFT": "📉"}.get(alert.alert_type, "•")
                    lines.append(
                        f"{icon} [{alert.alert_type}] {alert.title}\n"
                        f"  {alert.why_it_matters[:150]}\n"
                        f"  → {alert.recommended_action[:150]}\n"
                    )
        return "\n".join(lines)

    @property
    def status(self) -> dict:
        return {
            "running": self._running,
            "last_check": self._last_check.isoformat() if self._last_check else "never",
            "pending_alerts": len(self._pending_alerts),
            "check_interval_minutes": self.check_interval // 60,
        }


class _MonitorAgent(BaseAgent):
    name = "proactive_monitor"

    def __init__(self):
        super().__init__()
        self._system_prompt = MONITOR_AGENT_PROMPT
        self.model = config.worker_model


proactive_monitor = ProactiveMonitor()
