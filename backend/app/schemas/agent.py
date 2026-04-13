"""Pydantic schemas for the Agent API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class AgentChatRequest(BaseModel):
    session_id: str = Field(..., description="Conversation UUID")
    project_id: Optional[str] = Field(None, description="Associated project UUID")
    message: str = Field(..., min_length=1, description="User message")
    provider: Optional[Literal["openai", "deepseek", "minimax"]] = None


class ExtractedConcept(BaseModel):
    name: str
    type: str
    confidence: float


class RequirementChangeSummary(BaseModel):
    change_id: str
    change_type: str
    description: str
    affected_documents: List[str]


class PhaseDocumentSchema(BaseModel):
    phase: str
    title: str
    content: str
    rendered_at: datetime
    turn_count: int


class AgentChatResponse(BaseModel):
    reply: str
    session_id: str
    phase: str
    phase_label: str
    progress: float = Field(..., ge=0.0, le=1.0)
    suggestions: List[str] = Field(default_factory=list)
    extracted_concepts: List[ExtractedConcept] = Field(default_factory=list)
    requirement_changes: List[RequirementChangeSummary] = Field(default_factory=list)
    stale_documents: List[str] = Field(default_factory=list)
    pending_documents: List[str] = Field(default_factory=list)
    phase_document: Optional[PhaseDocumentSchema] = None
    tech_stack_preferences: Optional[Dict[str, Any]] = None
    phase_changed: bool = False


class SwitchPhaseRequest(BaseModel):
    session_id: str = Field(..., description="Conversation UUID")
    direction: Literal["next", "back"] = Field(
        ..., description="Direction to navigate: 'next' advances one phase, 'back' retreats one phase"
    )
    provider: Optional[Literal["openai", "deepseek", "minimax"]] = None


class GenerateDocumentRequest(BaseModel):
    session_id: str = Field(..., description="Conversation UUID")
    project_id: Optional[str] = Field(None, description="Associated project UUID")
    document_type: Literal[
        "BUSINESS_REQUIREMENT",
        "DOMAIN_MODEL",
        "UBIQUITOUS_LANGUAGE",
        "USE_CASES",
        "TECH_ARCHITECTURE",
    ] = Field(..., description="Type of DDD document to generate")
    provider: Optional[Literal["openai", "deepseek", "minimax"]] = None


class GenerateDocumentResponse(BaseModel):
    document_type: str
    content: str
    version_id: str
    project_id: Optional[str] = None
    generated_at: datetime


class AgentContextResponse(BaseModel):
    session_id: str
    project_id: Optional[str]
    current_phase: str
    phase_label: str
    progress: float
    turn_count: int
    domain_knowledge: Dict[str, Any]
    requirement_changes: List[Dict[str, Any]]
    generated_documents: List[Dict[str, Any]]
    stale_documents: List[str]
    tech_stack_preferences: Optional[Dict[str, Any]] = None


class RequirementChangesResponse(BaseModel):
    session_id: str
    changes: List[Dict[str, Any]]
    stale_documents: List[str]


class PhaseDocumentResponse(BaseModel):
    session_id: str
    phase: str
    title: str
    content: str
    rendered_at: Optional[datetime]
    turn_count: int


class ConversationSummary(BaseModel):
    session_id: str
    title: Optional[str]
    phase: str
    phase_label: str
    turn_count: int
    created_at: datetime
    updated_at: datetime


class ConversationListResponse(BaseModel):
    conversations: List[ConversationSummary]


class SessionMessageItem(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class SessionMessagesResponse(BaseModel):
    session_id: str
    messages: List[SessionMessageItem]
