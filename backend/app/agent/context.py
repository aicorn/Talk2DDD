"""AgentContext and related data structures for the Talk2DDD AI Agent."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field


class Phase(str, Enum):
    ICEBREAK = "ICEBREAK"
    REQUIREMENT = "REQUIREMENT"
    DOMAIN_EXPLORE = "DOMAIN_EXPLORE"
    MODEL_DESIGN = "MODEL_DESIGN"
    REVIEW_REFINE = "REVIEW_REFINE"


PHASE_ORDER: List[Phase] = [
    Phase.ICEBREAK,
    Phase.REQUIREMENT,
    Phase.DOMAIN_EXPLORE,
    Phase.MODEL_DESIGN,
    Phase.REVIEW_REFINE,
]

PHASE_LABELS: dict[Phase, str] = {
    Phase.ICEBREAK: "破冰引入",
    Phase.REQUIREMENT: "需求收集",
    Phase.DOMAIN_EXPLORE: "领域探索",
    Phase.MODEL_DESIGN: "模型设计",
    Phase.REVIEW_REFINE: "审阅完善",
}

PHASE_PROGRESS: dict[Phase, float] = {
    Phase.ICEBREAK: 0.0,
    Phase.REQUIREMENT: 0.25,
    Phase.DOMAIN_EXPLORE: 0.5,
    Phase.MODEL_DESIGN: 0.75,
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


class TechProficiency(str, Enum):
    FAMILIAR = "FAMILIAR"
    LEARNING = "LEARNING"
    UNFAMILIAR = "UNFAMILIAR"


class TechChoice(BaseModel):
    name: str
    category: str = "custom"
    version: Optional[str] = None
    reason: Optional[str] = None
    proficiency: TechProficiency = TechProficiency.FAMILIAR


class TechStackPreferences(BaseModel):
    confirmed: bool = False
    skipped: bool = False
    frontend: List[TechChoice] = Field(default_factory=list)
    backend: List[TechChoice] = Field(default_factory=list)
    database: List[TechChoice] = Field(default_factory=list)
    infrastructure: List[TechChoice] = Field(default_factory=list)
    messaging: List[TechChoice] = Field(default_factory=list)
    custom: List[TechChoice] = Field(default_factory=list)

    def all_choices(self) -> List[TechChoice]:
        return (
            self.frontend
            + self.backend
            + self.database
            + self.infrastructure
            + self.messaging
            + self.custom
        )

    def is_empty(self) -> bool:
        return not self.all_choices()

    def summary(self) -> str:
        """Return a compact summary string for prompt injection."""
        if self.skipped:
            return "（用户跳过，由 AI 根据领域模型推荐）"
        parts = []
        _LABEL = {
            "frontend": "前端",
            "backend": "后端",
            "database": "数据库",
            "infrastructure": "基础设施",
            "messaging": "消息队列",
            "custom": "其他",
        }
        for category, label in _LABEL.items():
            choices: List[TechChoice] = getattr(self, category)
            if choices:
                names = "、".join(c.name for c in choices)
                parts.append(f"{label}：{names}")
        return "；".join(parts) if parts else "（尚未采集）"


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


# ---------------------------------------------------------------------------
# Phase-opening structured suggestion (§21 of ai-agent-design.md)
# ---------------------------------------------------------------------------


class SuggestionStatus(str, Enum):
    PENDING = "PENDING"      # Generated, awaiting user response
    PARTIAL = "PARTIAL"      # Some items handled
    COMPLETED = "COMPLETED"  # All items handled or dismissed


class UserIntent(str, Enum):
    MAKE_SELECTION = "MAKE_SELECTION"        # User accepts/selects an option
    REQUEST_MORE = "REQUEST_MORE"            # User asks for more suggestions
    REQUEST_REFINE = "REQUEST_REFINE"        # User asks for refinement of an item
    REJECT_SUGGESTION = "REJECT_SUGGESTION"  # User rejects/dismisses an item
    PROVIDE_FEEDBACK = "PROVIDE_FEEDBACK"    # User provides open-ended feedback
    OUT_OF_SCOPE = "OUT_OF_SCOPE"            # Request outside the suggestion scope


class IntentClassification(BaseModel):
    intent: UserIntent
    target_index: Optional[int] = None        # Which suggestion item (1-based)
    selected_option: Optional[str] = None     # For MAKE_SELECTION: the chosen option
    raw_feedback: Optional[str] = None        # For PROVIDE_FEEDBACK: summary text
    out_of_scope_hint: Optional[str] = None   # For OUT_OF_SCOPE: user intent hint


class RefinementItem(BaseModel):
    index: int                               # 1-based display index
    question: str                            # The refinement question
    options: List[str]                       # Alternative answers
    selected: Optional[str] = None           # User's selection (None = pending)
    dismissed: bool = False                  # Whether the user dismissed this item
    note: Optional[str] = None               # Additional notes


class ScenarioRefinementSuggestion(BaseModel):
    """P2 opening suggestion: per-scenario refinement questions."""

    scenario_id: str
    scenario_name: str
    items: List[RefinementItem] = Field(default_factory=list)
    status: SuggestionStatus = SuggestionStatus.PENDING


class ContextSuggestionItem(BaseModel):
    """P3 opening suggestion: proposed bounded-context groupings."""

    index: int
    context_name: str                        # Suggested bounded context name
    concepts: List[str]                      # Concepts included
    rationale: str                           # Reason for grouping
    alternatives: List[str]                  # Alternative groupings
    accepted: Optional[bool] = None
    dismissed: bool = False
    modifications: Optional[str] = None


class ModelDesignItem(BaseModel):
    """P4 opening suggestion: aggregate/entity/value-object design."""

    index: int
    context_name: str
    aggregate_root: str
    entities: List[str]
    value_objects: List[str]
    rationale: str
    alternatives: List[str]
    dismissed: bool = False
    decision: Optional[str] = None


class ReviewItem(BaseModel):
    """P5 opening suggestion: model review and revision points."""

    index: int
    severity: Literal["高", "中", "低"]
    issue_type: str                          # "一致性问题" / "边界问题" / etc.
    description: str
    suggestion: str
    options: List[str]
    dismissed: bool = False
    resolution: Optional[str] = None


class PhaseSuggestion(BaseModel):
    """Stores the phase-opening structured suggestion and per-item user choices."""

    model_config = {"protected_namespaces": ()}

    phase: Phase
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    status: SuggestionStatus = SuggestionStatus.PENDING
    # Only the field matching the current phase will be populated
    scenario_refinements: List[ScenarioRefinementSuggestion] = Field(default_factory=list)
    context_groupings: List[ContextSuggestionItem] = Field(default_factory=list)
    model_designs: List[ModelDesignItem] = Field(default_factory=list)
    review_items: List[ReviewItem] = Field(default_factory=list)


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
    tech_stack_preferences: TechStackPreferences = Field(
        default_factory=TechStackPreferences
    )
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

    # Phase-opening structured suggestion (§21 of ai-agent-design.md)
    phase_suggestion: Optional[PhaseSuggestion] = None

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
