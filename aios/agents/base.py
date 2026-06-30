import asyncio
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import anthropic
from tenacity import retry, stop_after_attempt, wait_exponential

from ..config import config
from ..system_prompt import AGENT_SYSTEM_PROMPTS, MASTER_SYSTEM_PROMPT


@dataclass
class AgentResult:
    agent_name: str
    content: str
    confidence: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)
    tokens_used: int = 0
    duration_ms: float = 0.0
    error: str | None = None
    succeeded: bool = True


@dataclass
class AgentMessage:
    role: str   # "user" | "assistant"
    content: str


class BaseAgent(ABC):
    name: str = "base"
    model: str = ""
    description: str = ""
    tools: list[dict] = []

    def __init__(self):
        self._client = anthropic.Anthropic(api_key=config.api_key)
        self._system_prompt = AGENT_SYSTEM_PROMPTS.get(self.name, MASTER_SYSTEM_PROMPT)
        if not self.model:
            self.model = config.worker_model

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def call(
        self,
        messages: list[AgentMessage],
        context: str | None = None,
        max_tokens: int | None = None,
    ) -> AgentResult:
        start = datetime.utcnow()
        try:
            full_system = self._system_prompt
            if context:
                full_system = f"{full_system}\n\n## Retrieved Memory Context\n{context}"

            api_messages = [{"role": m.role, "content": m.content} for m in messages]

            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._client.messages.create(
                    model=self.model,
                    max_tokens=max_tokens or config.max_tokens_worker,
                    system=full_system,
                    messages=api_messages,
                    tools=self.tools if self.tools else anthropic.NOT_GIVEN,
                ),
            )

            content = ""
            for block in response.content:
                if hasattr(block, "text"):
                    content += block.text

            duration = (datetime.utcnow() - start).total_seconds() * 1000
            return AgentResult(
                agent_name=self.name,
                content=content,
                tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                duration_ms=duration,
                succeeded=True,
            )
        except Exception as e:
            duration = (datetime.utcnow() - start).total_seconds() * 1000
            return AgentResult(
                agent_name=self.name,
                content="",
                duration_ms=duration,
                error=str(e),
                succeeded=False,
            )

    async def run(self, task: str, context: str | None = None, **kwargs) -> AgentResult:
        messages = [AgentMessage(role="user", content=task)]
        return await self.call(messages, context=context)
