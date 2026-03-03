import uuid
from typing import Optional, List
from sqlalchemy import String, Text, ForeignKey, Integer, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.models.base import BaseModel


class Project(BaseModel):
    __tablename__ = "projects"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    domain_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="active", nullable=False)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    # Relationships
    owner: Mapped["User"] = relationship("User", back_populates="projects")
    document_versions: Mapped[List["DocumentVersion"]] = relationship(
        "DocumentVersion", back_populates="project", cascade="all, delete-orphan"
    )
    steps: Mapped[List["Step"]] = relationship(
        "Step", back_populates="project", cascade="all, delete-orphan"
    )
    conversations: Mapped[List["Conversation"]] = relationship(
        "Conversation", back_populates="project", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Project(id={self.id}, name={self.name})>"


class DocumentVersion(BaseModel):
    __tablename__ = "document_versions"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    document_type: Mapped[str] = mapped_column(String(100), default="requirements", nullable=False)
    extra_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    is_current: Mapped[bool] = mapped_column(default=True, nullable=False)

    # Relationships
    project: Mapped["Project"] = relationship("Project", back_populates="document_versions")

    def __repr__(self) -> str:
        return f"<DocumentVersion(id={self.id}, project_id={self.project_id}, version={self.version_number})>"
