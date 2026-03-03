import uuid
from typing import Optional, List
from sqlalchemy import String, Text, ForeignKey, Integer, JSON, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.models.base import BaseModel


class Step(BaseModel):
    __tablename__ = "steps"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    step_type: Mapped[str] = mapped_column(String(100), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    extra_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Relationships
    project: Mapped["Project"] = relationship("Project", back_populates="steps")
    ai_suggestions: Mapped[List["AISuggestion"]] = relationship(
        "AISuggestion", back_populates="step", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Step(id={self.id}, name={self.name}, type={self.step_type})>"


class AISuggestion(BaseModel):
    __tablename__ = "ai_suggestions"

    step_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("steps.id", ondelete="CASCADE"), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    suggestion_type: Mapped[str] = mapped_column(String(100), nullable=False)
    confidence_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    is_accepted: Mapped[Optional[bool]] = mapped_column(nullable=True)
    model_used: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    extra_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Relationships
    step: Mapped["Step"] = relationship("Step", back_populates="ai_suggestions")

    def __repr__(self) -> str:
        return f"<AISuggestion(id={self.id}, step_id={self.step_id}, type={self.suggestion_type})>"
