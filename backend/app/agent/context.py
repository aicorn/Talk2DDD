"""AgentContext and related data structures for the Talk2DDD AI Agent."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class Phase(str, Enum):
    ICEBREAK = "ICEBREAK"
    REQUIREMENT = "REQUIREMENT"
    DOMAIN_EXPLORE = "DOMAIN_EXPLORE"
    MODEL_DESIGN = "MODEL_DESIGN"
    DOC_GENERATE = "DOC_GENERATE"
    REVIEW_REFINE = "REVIEW_REFINE"


PHASE_ORDER: List[Phase] = [
    Phase.ICEBREAK,
    Phase.REQUIREMENT,
    Phase.DOMAIN_EXPLORE,
    Phase.MODEL_DESIGN,
    Phase.DOC_GENERATE,
    Phase.REVIEW_REFINE,
]

PHASE_LABELS: dict[Phase, str] = {
    Phase.ICEBREAK: "破冰引入",
    Phase.REQUIREMENT: "需求收集",
    Phase.DOMAIN_EXPLORE: "领域探索",
    Phase.MODEL_DESIGN: "模型设计",
    Phase.DOC_GENERATE: "文档生成",
    Phase.REVIEW_REFINE: "审阅完善",
}

PHASE_PROGRESS: dict[Phase, float] = {
    Phase.ICEBREAK: 0.0,
    Phase.REQUIREMENT: 0.2,
    Phase.DOMAIN_EXPLORE: 0.4,
    Phase.MODEL_DESIGN: 0.6,
    Phase.DOC_GENERATE: 0.8,
    Phase.REVIEW_REFINE: 1.0,
}


class ConceptType(str, Enum):
    ENTITY = "ENTITY"
    VALUE_OBJECT = "VALUE_OBJECT"
    SERVICE = "SERVICE"
    EVENT = "EVENT"
    AGGREGATE = "AGGREGATE"
    REPOSITORY = "REPOSITORY"
    DOMAIN_SERVICE = "DOMAIN_SERVICE"


class ScenarioStatus(str, Enum):
    ACTIVE = "ACTIVE"
    MODIFIED = "MODIFIED"
    DEPRECATED = "DEPRECATED"


class DocumentStatus(str, Enum):
    CURRENT = "CURRENT"
    STALE = "STALE"
    SUPERSEDED = "SUPERSEDED"


class DocumentType(str, Enum):
    BUSINESS_REQUIREMENT = "BUSINESS_REQUIREMENT"
    DOMAIN_MODEL = "DOMAIN_MODEL"
    UBIQUITOUS_LANGUAGE = "UBIQUITOUS_LANGUAGE"
    USE_CASES = "USE_CASES"
    TECH_ARCHITECTURE = "TECH_ARCHITECTURE"


class ChangeType(str, Enum):
    ADD = "ADD"
    MODIFY = "MODIFY"
    DEPRECATE = "DEPRECATE"


class BusinessScenario(BaseModel):
    id: str = Field(default_factory=lambda: f"S{str(uuid.uuid4())[:8]}")
    name: str
    description: str
    status: ScenarioStatus = ScenarioStatus.ACTIVE
    version: int = 1


class DomainConcept(BaseModel):
    name: str
    concept_type: ConceptType
    description: str
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)


class BoundedContext(BaseModel):
    name: str
    description: str
    concepts: List[str] = Field(default_factory=list)


class ConceptRelation(BaseModel):
    source: str
    target: str
    relation_type: str
    description: str = ""


class DomainKnowledge(BaseModel):
    project_name: str = ""
    domain_description: str = ""
    business_scenarios: List[BusinessScenario] = Field(default_factory=list)
    domain_concepts: List[DomainConcept] = Field(default_factory=list)
    bounded_contexts: List[BoundedContext] = Field(default_factory=list)
    relationships: List[ConceptRelation] = Field(default_factory=list)


class PhaseTransition(BaseModel):
    from_phase: Optional[Phase] = None
    to_phase: Phase
    reason: str = ""
    transitioned_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class RequirementChange(BaseModel):
    change_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    change_type: ChangeType
    target_id: Optional[str] = None
    description: str
    changed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    affected_documents: List[str] = Field(default_factory=list)


class DocumentRef(BaseModel):
    version_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    document_type: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status: DocumentStatus = DocumentStatus.CURRENT


class ClarificationQuestion(BaseModel):
    id: str = Field(default_factory=lambda: f"Q{str(uuid.uuid4())[:8]}")
    question: str
    scenario_id: Optional[str] = None
    answered: bool = False


class MemoryConfig(BaseModel):
    """Tunable parameters for the three-layer memory model."""

    immediate_memory_turns: int = Field(
        default=10,
        description="K – keep the most recent K turns verbatim in the messages list.",
    )
    min_immediate_memory_turns: int = Field(
        default=2,
        description=(
            "Hard floor for K when the token budget forces trimming; "
            "always keep at least this many recent turns."
        ),
    )
    summary_trigger_turns: int = Field(
        default=10,
        description="First-fire: start compression once turn_count reaches this value.",
    )
    summary_refresh_interval: int = Field(
        default=5,
        description=(
            "After the first compression, refresh the rolling summary every M turns "
            "(i.e. at turns 10, 15, 20, …)."
        ),
    )
    max_input_tokens: int = Field(
        default=6000,
        description="Soft token budget for the full input sent to the AI provider.",
    )


class AgentContext(BaseModel):
    session_id: str
    project_id: Optional[str] = None
    current_phase: Phase = Phase.ICEBREAK
    phase_before_change: Optional[Phase] = None
    phase_history: List[PhaseTransition] = Field(default_factory=list)
    domain_knowledge: DomainKnowledge = Field(default_factory=DomainKnowledge)
    requirement_changes: List[RequirementChange] = Field(default_factory=list)
    generated_documents: List[DocumentRef] = Field(default_factory=list)
    clarification_queue: List[ClarificationQuestion] = Field(default_factory=list)
    turn_count: int = 0

    # ── Memory mechanism fields (§4.4 of ai-agent-design.md) ──────────────
    conversation_summary: str = Field(
        default="",
        description=(
            "Layer 2 rolling summary: AI-generated compression of turns older than "
            "the immediate-memory window.  Empty until the first compression fires."
        ),
    )
    summary_last_updated_turn: int = Field(
        default=0,
        description="turn_count at which conversation_summary was last updated.",
    )
    summary_covers_turns: int = Field(
        default=0,
        description="Number of turns already covered by conversation_summary.",
    )
    memory_config: MemoryConfig = Field(default_factory=MemoryConfig)

    def get_stale_documents(self) -> List[str]:
        return [
            d.document_type
            for d in self.generated_documents
            if d.status == DocumentStatus.STALE
        ]

    def mark_documents_stale(self, document_types: List[str]) -> None:
        for doc in self.generated_documents:
            if doc.document_type in document_types:
                doc.status = DocumentStatus.STALE

    def add_document_ref(self, doc_type: str, version_id: str) -> None:
        # Supersede existing documents of the same type
        for doc in self.generated_documents:
            if doc.document_type == doc_type and doc.status == DocumentStatus.CURRENT:
                doc.status = DocumentStatus.SUPERSEDED
        self.generated_documents.append(
            DocumentRef(version_id=version_id, document_type=doc_type)
        )
