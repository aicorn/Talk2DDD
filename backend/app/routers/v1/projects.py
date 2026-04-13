"""Projects API router — /api/v1/projects/*"""

from __future__ import annotations

import logging
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.database.session import get_db
from app.models.document import DocumentVersion, Project
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class DocumentVersionSummary(BaseModel):
    id: str
    document_type: str
    version_number: int
    is_current: bool
    created_at: str
    content_preview: str


class ProjectSummary(BaseModel):
    id: str
    name: str
    description: Optional[str]
    domain_name: Optional[str]
    status: str
    created_at: str
    document_count: int


class ProjectDetail(ProjectSummary):
    documents: List[DocumentVersionSummary]


# ---------------------------------------------------------------------------
# GET /projects
# ---------------------------------------------------------------------------


@router.get("", response_model=List[ProjectSummary])
async def list_projects(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> List[ProjectSummary]:
    """List all projects owned by the current user."""
    result = await db.execute(
        select(Project)
        .where(Project.owner_id == current_user.id)
        .order_by(Project.created_at.desc())
    )
    projects = result.scalars().all()

    summaries = []
    for proj in projects:
        doc_count_result = await db.execute(
            select(DocumentVersion).where(
                DocumentVersion.project_id == proj.id,
                DocumentVersion.is_current == True,  # noqa: E712
            )
        )
        doc_count = len(doc_count_result.scalars().all())
        summaries.append(
            ProjectSummary(
                id=str(proj.id),
                name=proj.name,
                description=proj.description,
                domain_name=proj.domain_name,
                status=proj.status,
                created_at=proj.created_at.isoformat(),
                document_count=doc_count,
            )
        )
    return summaries


# ---------------------------------------------------------------------------
# GET /projects/{project_id}
# ---------------------------------------------------------------------------


@router.get("/{project_id}", response_model=ProjectDetail)
async def get_project(
    project_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ProjectDetail:
    """Get a project with its current documents."""
    import uuid as _uuid

    try:
        proj_uuid = _uuid.UUID(project_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project_id")

    result = await db.execute(
        select(Project).where(
            Project.id == proj_uuid,
            Project.owner_id == current_user.id,
        )
    )
    proj = result.scalar_one_or_none()
    if proj is None:
        raise HTTPException(status_code=404, detail="Project not found")

    doc_result = await db.execute(
        select(DocumentVersion)
        .where(DocumentVersion.project_id == proj_uuid)
        .order_by(DocumentVersion.document_type, DocumentVersion.version_number.desc())
    )
    docs = doc_result.scalars().all()

    doc_summaries = [
        DocumentVersionSummary(
            id=str(d.id),
            document_type=d.document_type,
            version_number=d.version_number,
            is_current=d.is_current,
            created_at=d.created_at.isoformat(),
            content_preview=(d.content or "")[:200],
        )
        for d in docs
    ]

    doc_count = sum(1 for d in docs if d.is_current)
    return ProjectDetail(
        id=str(proj.id),
        name=proj.name,
        description=proj.description,
        domain_name=proj.domain_name,
        status=proj.status,
        created_at=proj.created_at.isoformat(),
        document_count=doc_count,
        documents=doc_summaries,
    )


# ---------------------------------------------------------------------------
# GET /projects/{project_id}/documents/{doc_id}/content
# ---------------------------------------------------------------------------


@router.get("/{project_id}/documents/{doc_id}/content")
async def get_document_content(
    project_id: str,
    doc_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Get the full content of a specific document version."""
    import uuid as _uuid

    try:
        proj_uuid = _uuid.UUID(project_id)
        doc_uuid = _uuid.UUID(doc_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid ID")

    # Verify project ownership
    proj_result = await db.execute(
        select(Project).where(
            Project.id == proj_uuid,
            Project.owner_id == current_user.id,
        )
    )
    if proj_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Project not found")

    doc_result = await db.execute(
        select(DocumentVersion).where(
            DocumentVersion.id == doc_uuid,
            DocumentVersion.project_id == proj_uuid,
        )
    )
    doc = doc_result.scalar_one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")

    return {
        "id": str(doc.id),
        "document_type": doc.document_type,
        "version_number": doc.version_number,
        "content": doc.content,
        "is_current": doc.is_current,
        "created_at": doc.created_at.isoformat(),
    }


# ---------------------------------------------------------------------------
# DELETE /projects/{project_id}
# ---------------------------------------------------------------------------


@router.delete("/{project_id}", status_code=204, response_class=Response)
async def delete_project(
    project_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """Delete a project and all its documents."""
    import uuid as _uuid

    try:
        proj_uuid = _uuid.UUID(project_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project_id")

    result = await db.execute(
        select(Project).where(
            Project.id == proj_uuid,
            Project.owner_id == current_user.id,
        )
    )
    proj = result.scalar_one_or_none()
    if proj is None:
        raise HTTPException(status_code=404, detail="Project not found")

    await db.delete(proj)
    await db.commit()
    return Response(status_code=204)
