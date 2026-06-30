import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


@dataclass
class AIOSConfig:
    api_key: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    db_path: str = field(default_factory=lambda: os.getenv("AIOS_DB_PATH", "./data/aios.db"))
    vector_path: str = field(default_factory=lambda: os.getenv("AIOS_VECTOR_PATH", "./data/vectors"))

    # Model tiers: CEO gets the most capable model
    ceo_model: str = field(default_factory=lambda: os.getenv("AIOS_CEO_MODEL", "claude-opus-4-8"))
    worker_model: str = field(default_factory=lambda: os.getenv("AIOS_WORKER_MODEL", "claude-sonnet-4-6"))
    fast_model: str = field(default_factory=lambda: os.getenv("AIOS_FAST_MODEL", "claude-haiku-4-5-20251001"))

    max_parallel_agents: int = field(default_factory=lambda: int(os.getenv("AIOS_MAX_PARALLEL_AGENTS", "6")))
    memory_decay_days: int = field(default_factory=lambda: int(os.getenv("AIOS_MEMORY_DECAY_DAYS", "90")))
    debug: bool = field(default_factory=lambda: os.getenv("AIOS_DEBUG", "false").lower() == "true")

    max_tokens_ceo: int = 8096
    max_tokens_worker: int = 16384
    max_tokens_fast: int = 4096

    memory_top_k: int = 10
    research_min_sources: int = 3
    confidence_threshold: float = 0.75

    def validate(self) -> None:
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY is required. Copy .env.example to .env and set it.")


config = AIOSConfig()
