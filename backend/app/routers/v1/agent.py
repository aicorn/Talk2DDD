"""Agent API router — /api/v1/agent/*"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Annotated

import openai
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

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
    ConversationListResponse,
    ConversationSummary,
    ExtractedConcept,
    PhaseDocumentResponse,
    PhaseDocumentSchema,
    RequirementChangeSummary,
    RequirementChangesResponse,
    SessionMessageItem,
    SessionMessagesResponse,
    SwitchPhaseRequest,
)

import uuid as _uuid

router = APIRouter()
_agent_core = AgentCore()
_context_manager = ContextManager()
_renderer = PhaseDocumentRenderer()


def _friendly_ai_error(exc: Exception) -> str:
    """Return a user-friendly Chinese error message for an AI provider error.

    Translates transient capacity / rate-limit errors into short, actionable
    messages so users aren't shown raw JSON error bodies.
    """
    # openai.APIStatusError carries a numeric status_code attribute
    status_code: int | None = getattr(exc, "status_code", None)
    if status_code in (429, 529):
        return "AI 服务当前繁忙，请稍等几秒后点击「重试」。"
    if status_code in (500, 502, 503):
        return "AI 服务暂时不可用，请稍后重试。"
    # Connection / timeout errors
    exc_type = type(exc).__name__
    if "Connection" in exc_type or "Timeout" in exc_type:
        return "无法连接到 AI 服务，请检查网络后重试。"
    # Fallback: include a shortened version of the original error
    msg = str(exc)
    if len(msg) > 200:
        msg = msg[:200] + "…"
    return f"AI 服务调用失败：{msg}"


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
            detail=_friendly_ai_error(exc),
        ) from exc
    except Exception as exc:
        # Catch-all: any unhandled exception (DB errors, unexpected failures)
        # must return a proper HTTP error instead of letting Uvicorn close the
        # connection (which would produce ECONNRESET on the proxy side).
        logger.exception("Unhandled error in agent_chat: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="服务器内部错误，请稍后重试",
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
        phase_document=phase_doc,
        tech_stack_preferences=result.tech_stack_preferences,
    )


# ---------------------------------------------------------------------------
# POST /switch-phase
# ---------------------------------------------------------------------------


@router.post("/switch-phase", response_model=AgentChatResponse, status_code=200)
async def switch_phase(
    request: SwitchPhaseRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AgentChatResponse:
    """Manually advance or retreat one phase and return an AI-generated phase intro.

    The AI response is focused on orienting the user in the new phase rather
    than continuing the previous topic.  The direction parameter must be either
    ``"next"`` (advance) or ``"back"`` (retreat).  Returns HTTP 400 when the
    session is already at the first or last phase.
    """
    await _ensure_conversation(request.session_id, current_user, None, db)

    try:
        result = await _agent_core.switch_phase(
            session_id=request.session_id,
            direction=request.direction,
            db=db,
            provider=request.provider,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except (openai.OpenAIError, RuntimeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=_friendly_ai_error(exc),
        ) from exc
    except Exception as exc:
        logger.exception("Unhandled error in switch_phase: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="服务器内部错误，请稍后重试",
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
        phase_document=phase_doc,
        tech_stack_preferences=result.tech_stack_preferences,
        phase_changed=result.phase_changed,
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
    ts = ctx.tech_stack_preferences
    tech_stack_data = None
    if ts.confirmed or not ts.is_empty():
        tech_stack_data = {
            "confirmed": ts.confirmed,
            "skipped": ts.skipped,
            "summary": ts.summary(),
            "frontend": [c.model_dump() for c in ts.frontend],
            "backend": [c.model_dump() for c in ts.backend],
            "database": [c.model_dump() for c in ts.database],
            "infrastructure": [c.model_dump() for c in ts.infrastructure],
            "messaging": [c.model_dump() for c in ts.messaging],
            "custom": [c.model_dump() for c in ts.custom],
        }
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
        tech_stack_preferences=tech_stack_data,
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
    MODEL_DESIGN, REVIEW_REFINE.
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


# ---------------------------------------------------------------------------
# GET /sessions
# ---------------------------------------------------------------------------


@router.get(
    "/sessions",
    response_model=ConversationListResponse,
    status_code=200,
)
async def list_sessions(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ConversationListResponse:
    """Return all Agent conversations belonging to the current user."""
    from sqlalchemy import select

    result = await db.execute(
        select(Conversation)
        .where(Conversation.user_id == current_user.id)
        .order_by(Conversation.updated_at.desc())
    )
    convs = result.scalars().all()

    items: list[ConversationSummary] = []
    for conv in convs:
        # Fall back to ICEBREAK if the conversation hasn't started an agent session yet
        phase_val = conv.agent_phase or Phase.ICEBREAK.value
        turn_count = 0
        if conv.extra_data and "agent_context" in conv.extra_data:
            turn_count = conv.extra_data["agent_context"].get("turn_count", 0)
        items.append(
            ConversationSummary(
                session_id=str(conv.id),
                title=conv.title,
                phase=phase_val,
                phase_label=PHASE_LABELS.get(phase_val, phase_val),
                turn_count=turn_count,
                created_at=conv.created_at,
                updated_at=conv.updated_at,
            )
        )

    return ConversationListResponse(conversations=items)


# ---------------------------------------------------------------------------
# GET /sessions/{session_id}/messages
# ---------------------------------------------------------------------------


@router.get(
    "/sessions/{session_id}/messages",
    response_model=SessionMessagesResponse,
    status_code=200,
)
async def get_session_messages(
    session_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SessionMessagesResponse:
    """Return all stored user/assistant messages for a session."""
    from sqlalchemy import select

    try:
        conv_uuid = _uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid session_id: not a valid UUID",
        )

    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conv_uuid,
            Conversation.user_id == current_user.id,
        )
    )
    conv = result.scalar_one_or_none()
    if conv is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    msgs = await _context_manager.load_messages(session_id, db)
    return SessionMessagesResponse(
        session_id=session_id,
        messages=[
            SessionMessageItem(role=m["role"], content=m["content"])
            for m in msgs
        ],
    )


# ---------------------------------------------------------------------------
# DELETE /sessions/{session_id}
# ---------------------------------------------------------------------------


@router.delete("/sessions/{session_id}", status_code=204, response_class=Response)
async def delete_session(
    session_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """Permanently delete an Agent conversation and all its messages."""
    from sqlalchemy import select

    try:
        conv_uuid = _uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid session_id: not a valid UUID",
        )

    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conv_uuid,
            Conversation.user_id == current_user.id,
        )
    )
    conv = result.scalar_one_or_none()
    if conv is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    await db.delete(conv)
    await db.commit()
    return Response(status_code=204)
