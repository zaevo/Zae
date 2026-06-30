from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class MemoryType(str, Enum):
    EPISODIC = "episodic"      # What happened in past sessions
    SEMANTIC = "semantic"       # Domain knowledge and facts
    PROJECT = "project"         # Ongoing work context and goals
    PROCEDURAL = "procedural"   # Workflows and processes that worked
    PREFERENCE = "preference"   # User communication style and priorities


class MemoryStatus(str, Enum):
    ACTIVE = "active"
    DECAYED = "decayed"
    CONSOLIDATED = "consolidated"
    ARCHIVED = "archived"


@dataclass
class Memory:
    id: str
    type: MemoryType
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    importance: float = 5.0          # 0–10 importance score
    confidence: float = 1.0          # 0–1 how certain we are this is accurate
    created_at: datetime = field(default_factory=datetime.utcnow)
    accessed_at: datetime = field(default_factory=datetime.utcnow)
    access_count: int = 0
    status: MemoryStatus = MemoryStatus.ACTIVE
    tags: list[str] = field(default_factory=list)
    project_id: str | None = None
    session_id: str | None = None
    source_agent: str | None = None

    def decay_score(self, days_since_access: float, decay_rate: float = 0.95) -> float:
        return self.importance * (decay_rate ** days_since_access)

    def relevance_to(self, query_embedding: list[float]) -> float:
        # Computed externally via vector store
        return 0.0


@dataclass
class MemoryQueryResult:
    memory: Memory
    relevance_score: float
    distance: float


@dataclass
class KnowledgeNode:
    id: str
    label: str
    node_type: str          # "entity", "concept", "fact", "relationship"
    properties: dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class KnowledgeEdge:
    source_id: str
    target_id: str
    relationship: str
    weight: float = 1.0
    confidence: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)
