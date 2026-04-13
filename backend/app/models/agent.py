"""Agent-related DB models: DomainConcept, BusinessScenario, RequirementChange, PhaseDocument."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class DomainConcept(BaseModel):
    __tablename__ = "domain_concepts"

    project_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=True,
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    concept_type: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.8, nullable=False)

    conversation: Mapped["Conversation"] = relationship(  # type: ignore[name-defined]
        "Conversation", foreign_keys=[conversation_id]
    )

    def __repr__(self) -> str:
        return f"<DomainConcept(id={self.id}, name={self.name}, type={self.concept_type})>"


class BusinessScenarioRecord(BaseModel):
    __tablename__ = "business_scenario_records"

    project_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=True,
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    scenario_key: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # e.g. "S001"
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(50), default="ACTIVE", nullable=False
    )  # ACTIVE | MODIFIED | DEPRECATED
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    conversation: Mapped["Conversation"] = relationship(  # type: ignore[name-defined]
        "Conversation", foreign_keys=[conversation_id]
    )

    def __repr__(self) -> str:
        return f"<BusinessScenarioRecord(id={self.id}, name={self.name}, status={self.status})>"


class RequirementChangeRecord(BaseModel):
    __tablename__ = "requirement_change_records"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    project_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=True,
    )
    change_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # ADD | MODIFY | DEPRECATE
    target_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    affected_document_types: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    conversation: Mapped["Conversation"] = relationship(  # type: ignore[name-defined]
        "Conversation", foreign_keys=[conversation_id]
    )

    def __repr__(self) -> str:
        return (
            f"<RequirementChangeRecord(id={self.id}, type={self.change_type}, "
            f"target={self.target_id})>"
        )


class PhaseDocument(BaseModel):
    __tablename__ = "phase_documents"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    phase: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # ICEBREAK | REQUIREMENT | ...
    content: Mapped[str] = mapped_column(Text, nullable=False)
    rendered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    turn_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    conversation: Mapped["Conversation"] = relationship(  # type: ignore[name-defined]
        "Conversation", foreign_keys=[conversation_id]
    )

    def __repr__(self) -> str:
        return (
            f"<PhaseDocument(id={self.id}, conversation_id={self.conversation_id}, "
            f"phase={self.phase})>"
        )
