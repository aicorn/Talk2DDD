"""Agent API router — /api/v1/agent/*"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

import openai
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.agent_core import AgentCore
from app.agent.context import PHASE_LABELS, PHASE_PROGRESS, Phase
from app.agent.context_manager import ContextManager
from app.agent.phase_document_renderer import PhaseDocumentRenderer
from app.core.dependencies import get_current_user
from app.database.session import get_db
from app.models.user import User
from app.models.conversation import Conversation
from app.schemas.agent import (
    AgentChatRequest,
    AgentChatResponse,
    AgentContextResponse,
    ExtractedConcept,
    GenerateDocumentRequest,
    GenerateDocumentResponse,
    PhaseDocumentResponse,
    PhaseDocumentSchema,
    RequirementChangeSummary,
    RequirementChangesResponse,
)

import uuid as _uuid

router = APIRouter()
_agent_core = AgentCore()
_context_manager = ContextManager()
_renderer = PhaseDocumentRenderer()


# ---------------------------------------------------------------------------
# Helper: resolve or create conversation
# ---------------------------------------------------------------------------

async def _ensure_conversation(
    session_id: str,
    user: User,
    project_id: str | None,
    db: AsyncSession,
) -> None:
    """Create a Conversation record for *session_id* if one doesn't exist."""
    from sqlalchemy import select

    try:
        conv_uuid = _uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid session_id: not a valid UUID",
        )

    result = await db.execute(
        select(Conversation).where(Conversation.id == conv_uuid)
    )
    existing = result.scalar_one_or_none()
    if existing is None:
        project_uuid = None
        if project_id:
            try:
                project_uuid = _uuid.UUID(project_id)
            except ValueError:
                pass
        convo = Conversation(
            id=conv_uuid,
            user_id=user.id,
            project_id=project_uuid,
            title="AI Agent 对话",
            status="active",
            agent_phase=Phase.ICEBREAK.value,
        )
        db.add(convo)
        await db.flush()


# ---------------------------------------------------------------------------
# POST /chat
# ---------------------------------------------------------------------------


@router.post("/chat", response_model=AgentChatResponse, status_code=200)
async def agent_chat(
    request: AgentChatRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AgentChatResponse:
    """Process a user message through the AI Agent and return a structured response."""
    await _ensure_conversation(
        request.session_id, current_user, request.project_id, db
    )

    try:
        result = await _agent_core.chat(
            session_id=request.session_id,
            message=request.message,
            db=db,
            project_id=request.project_id,
            provider=request.provider,
        )
    except (openai.OpenAIError, ValueError, RuntimeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"AI provider error: {exc}",
        ) from exc

    phase_doc = None
    if result.phase_document:
        pd = result.phase_document
        phase_doc = PhaseDocumentSchema(
            phase=pd.phase,
            title=pd.title,
            content=pd.content,
            rendered_at=pd.rendered_at,
            turn_count=pd.turn_count,
        )

    return AgentChatResponse(
        reply=result.reply,
        session_id=result.session_id,
        phase=result.phase,
        phase_label=result.phase_label,
        progress=result.progress,
        suggestions=result.suggestions,
        extracted_concepts=[
            ExtractedConcept(**c) for c in result.extracted_concepts
        ],
        requirement_changes=[
            RequirementChangeSummary(**c) for c in result.requirement_changes
        ],
        stale_documents=result.stale_documents,
        pending_documents=result.pending_documents,
        phase_document=phase_doc,
    )


# ---------------------------------------------------------------------------
# POST /generate-document
# ---------------------------------------------------------------------------


@router.post(
    "/generate-document",
    response_model=GenerateDocumentResponse,
    status_code=200,
)
async def generate_document(
    request: GenerateDocumentRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> GenerateDocumentResponse:
    """Generate a DDD document based on the current agent context."""
    await _ensure_conversation(
        request.session_id, current_user, request.project_id, db
    )

    try:
        content, version_id = await _agent_core.generate_document(
            session_id=request.session_id,
            document_type=request.document_type,
            db=db,
            project_id=request.project_id,
            provider=request.provider,
        )
    except (openai.OpenAIError, ValueError, RuntimeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Document generation error: {exc}",
        ) from exc

    return GenerateDocumentResponse(
        document_type=request.document_type,
        content=content,
        version_id=version_id,
        generated_at=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# GET /context/{session_id}
# ---------------------------------------------------------------------------


@router.get(
    "/context/{session_id}",
    response_model=AgentContextResponse,
    status_code=200,
)
async def get_context(
    session_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AgentContextResponse:
    """Return the current AgentContext for a session."""
    ctx = await _context_manager.load(session_id, db)
    phase = ctx.current_phase
    return AgentContextResponse(
        session_id=session_id,
        project_id=ctx.project_id,
        current_phase=phase.value,
        phase_label=PHASE_LABELS.get(phase, phase.value),
        progress=PHASE_PROGRESS.get(phase, 0.0),
        turn_count=ctx.turn_count,
        domain_knowledge=ctx.domain_knowledge.model_dump(),
        requirement_changes=[
            c.model_dump(mode="json") for c in ctx.requirement_changes
        ],
        generated_documents=[
            d.model_dump(mode="json") for d in ctx.generated_documents
        ],
        stale_documents=ctx.get_stale_documents(),
    )


# ---------------------------------------------------------------------------
# GET /requirement-changes/{session_id}
# ---------------------------------------------------------------------------


@router.get(
    "/requirement-changes/{session_id}",
    response_model=RequirementChangesResponse,
    status_code=200,
)
async def get_requirement_changes(
    session_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RequirementChangesResponse:
    """Return requirement change history and stale documents for a session."""
    ctx = await _context_manager.load(session_id, db)
    return RequirementChangesResponse(
        session_id=session_id,
        changes=[c.model_dump(mode="json") for c in ctx.requirement_changes],
        stale_documents=ctx.get_stale_documents(),
    )


# ---------------------------------------------------------------------------
# GET /phase-document/{session_id}/{phase}
# ---------------------------------------------------------------------------


@router.get(
    "/phase-document/{session_id}/{phase}",
    response_model=PhaseDocumentResponse,
    status_code=200,
)
async def get_phase_document(
    session_id: str,
    phase: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PhaseDocumentResponse:
    """Return the latest phase document for a session and phase.

    *phase* must be one of: ICEBREAK, REQUIREMENT, DOMAIN_EXPLORE,
    MODEL_DESIGN, DOC_GENERATE, REVIEW_REFINE.
    """
    try:
        phase_enum = Phase(phase.upper())
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Invalid phase '{phase}'. Must be one of: "
                + ", ".join(p.value for p in Phase)
            ),
        )

    ctx = await _context_manager.load(session_id, db)

    # Temporarily switch phase to render the requested phase document
    original_phase = ctx.current_phase
    ctx.current_phase = phase_enum
    content = _renderer.render(ctx)
    title = _renderer.get_title(ctx)
    ctx.current_phase = original_phase

    return PhaseDocumentResponse(
        session_id=session_id,
        phase=phase_enum.value,
        title=title,
        content=content,
        rendered_at=datetime.now(timezone.utc),
        turn_count=ctx.turn_count,
    )
