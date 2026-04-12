"""AgentCore: orchestrates the full agent request-response cycle."""

from __future__ import annotations

import re
import uuid as _uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.context import (
    AgentContext,
    DocumentType,
    Phase,
    PHASE_LABELS,
    PHASE_PROGRESS,
)
from app.agent.context_manager import ContextManager
from app.agent.document_pipeline import DocumentGenerationPipeline
from app.agent.knowledge_extractor import KnowledgeExtractor
from app.agent.memory_manager import MemoryManager
from app.agent.phase_document_renderer import PhaseDocumentRenderer
from app.agent.phase_engine import PhaseEngine
from app.agent.prompt_builder import PromptBuilder
from app.services.ai_service import chat_completion


@dataclass
class PhaseDocumentResult:
    phase: str
    title: str
    content: str
    rendered_at: datetime
    turn_count: int


@dataclass
class AgentResponse:
    reply: str
    session_id: str
    phase: str
    phase_label: str
    progress: float
    suggestions: List[str]
    extracted_concepts: List[Dict[str, Any]]
    requirement_changes: List[Dict[str, Any]]
    stale_documents: List[str]
    pending_documents: List[str]
    phase_document: Optional[PhaseDocumentResult]


# Phase-specific follow-up suggestions shown to the user
_PHASE_SUGGESTIONS: dict[Phase, List[str]] = {
    Phase.ICEBREAK: [
        "请介绍一下您的项目背景",
        "这个系统主要解决什么业务问题？",
        "核心用户是谁？",
    ],
    Phase.REQUIREMENT: [
        "请描述一个核心业务流程",
        "这个流程中有哪些关键角色？",
        "有哪些边界场景或异常情况？",
        "输入 /next 进入领域探索阶段",
    ],
    Phase.DOMAIN_EXPLORE: [
        "这些概念中有哪些是核心业务对象？",
        "有哪些重要的业务规则？",
        "输入 /next 进入模型设计阶段",
    ],
    Phase.MODEL_DESIGN: [
        "这些概念是否应该归属同一个聚合？",
        "输入 /next 进入文档生成阶段",
        "输入 /generate 直接生成文档",
    ],
    Phase.DOC_GENERATE: [
        "点击下方按钮生成「领域模型文档」",
        "点击下方按钮生成「业务需求文档」",
        "输入 /next 进入审阅完善阶段",
    ],
    Phase.REVIEW_REFINE: [
        "请审阅已生成的文档，提出修改意见",
        "输入 /regenerate [文档类型] 重新生成",
        "输入 /complete 标记项目完成",
    ],
}

_DOC_TYPE_LABELS: dict[str, str] = {
    "BUSINESS_REQUIREMENT": "业务需求文档",
    "DOMAIN_MODEL": "领域模型文档",
    "UBIQUITOUS_LANGUAGE": "通用语言术语表",
    "USE_CASES": "用例说明",
    "TECH_ARCHITECTURE": "技术架构建议",
}

# Matches "/generate [DOC_TYPE]" — these commands trigger the document pipeline
# directly to avoid long AI responses in the chat endpoint.
_GENERATE_DOC_RE = re.compile(
    r"/generate\s+(BUSINESS_REQUIREMENT|DOMAIN_MODEL|UBIQUITOUS_LANGUAGE|USE_CASES|TECH_ARCHITECTURE)",
    re.IGNORECASE,
)


class AgentCore:
    """Orchestrates the full agent request-response cycle."""

    def __init__(self) -> None:
        self._context_manager = ContextManager()
        self._memory_manager = MemoryManager()
        self._phase_engine = PhaseEngine()
        self._prompt_builder = PromptBuilder()
        self._knowledge_extractor = KnowledgeExtractor()
        self._doc_renderer = PhaseDocumentRenderer()
        self._doc_pipeline = DocumentGenerationPipeline()

    async def chat(
        self,
        session_id: str,
        message: str,
        db: AsyncSession,
        project_id: Optional[str] = None,
        provider: Optional[str] = None,
    ) -> AgentResponse:
        """Process a user message and return a structured agent response."""

        # 1. Load context
        ctx = await self._context_manager.load(session_id, db, project_id)

        # 2. Evaluate phase transition (may update ctx.phase_before_change)
        new_phase = self._phase_engine.evaluate(ctx, message)
        phase_transition_reason = ""
        if new_phase and new_phase != ctx.current_phase:
            phase_transition_reason = f"auto: {ctx.current_phase.value} → {new_phase.value}"
            self._phase_engine.advance_phase(ctx, new_phase, phase_transition_reason)

        # 2b. Intercept "/generate [DOC_TYPE]" — call the document pipeline directly
        #     instead of sending the command to the chat AI. The chat AI would try to
        #     output the full document as its reply (thousands of tokens), which causes
        #     the Next.js proxy to ECONNRESET before the backend finishes responding.
        gen_match = _GENERATE_DOC_RE.search(message)
        if gen_match:
            doc_type_str = gen_match.group(1).upper()
            try:
                doc_type = DocumentType(doc_type_str)
            except ValueError:
                doc_type = None
            if doc_type is not None:
                return await self._handle_generate_command(
                    ctx, session_id, message, doc_type, db, provider
                )

        # 3. Build system prompt (with optional rolling summary – Layer 2)
        summary_block = self._memory_manager.get_summary_block(ctx)
        system_prompt = self._prompt_builder.build(ctx, memory_summary_block=summary_block)

        # 4. Call AI – pass Layer-1 immediate history + current message
        history = await self._memory_manager.get_messages_for_ai(ctx, db)
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": message})

        ai_reply = await chat_completion(messages=messages, provider=provider)

        # 5. Extract knowledge from AI reply
        self._knowledge_extractor.extract(ai_reply, ctx)

        # 6. Re-evaluate phase transition post-extraction (knowledge may satisfy exit cond)
        if phase_transition_reason == "":
            post_phase = self._phase_engine.evaluate(ctx, "")
            if post_phase and post_phase != ctx.current_phase:
                self._phase_engine.advance_phase(
                    ctx, post_phase, f"exit-condition: {ctx.current_phase.value}"
                )

        # 7. Increment turn counter
        ctx.turn_count += 1

        # 8. Render phase document
        phase_doc_content = self._doc_renderer.render(ctx)
        phase_doc_title = self._doc_renderer.get_title(ctx)
        phase_doc = PhaseDocumentResult(
            phase=ctx.current_phase.value,
            title=phase_doc_title,
            content=phase_doc_content,
            rendered_at=datetime.now(timezone.utc),
            turn_count=ctx.turn_count,
        )

        # 9. Persist context and conversation messages
        await self._context_manager.save(ctx, db)
        await self._context_manager.append_messages(session_id, message, ai_reply, db)

        # 10. Trigger async memory compression if threshold reached (Layer 2).
        #     The background task opens its own DB session so the request-scoped
        #     session (now committed) is never touched after this point.
        await self._memory_manager.maybe_compress(ctx, provider=provider)

        # 11. Build response
        return AgentResponse(
            reply=ai_reply,
            session_id=session_id,
            phase=ctx.current_phase.value,
            phase_label=PHASE_LABELS.get(ctx.current_phase, ctx.current_phase.value),
            progress=PHASE_PROGRESS.get(ctx.current_phase, 0.0),
            suggestions=_PHASE_SUGGESTIONS.get(ctx.current_phase, []),
            extracted_concepts=self._format_concepts(ctx),
            requirement_changes=self._format_requirement_changes(ctx),
            stale_documents=ctx.get_stale_documents(),
            pending_documents=self._pending_document_types(ctx),
            phase_document=phase_doc,
        )

    async def generate_document(
        self,
        session_id: str,
        document_type: str,
        db: AsyncSession,
        project_id: Optional[str] = None,
        provider: Optional[str] = None,
    ) -> tuple[str, str, Optional[str]]:
        """Generate a DDD document and return (content, version_id, project_id).

        Also updates the AgentContext to record the generated document and
        persists the content as a DocumentVersion record linked to a Project.
        A Project is auto-created from the conversation's domain knowledge if
        one doesn't already exist.
        """
        ctx = await self._context_manager.load(session_id, db, project_id)

        try:
            doc_type = DocumentType(document_type)
        except ValueError:
            raise ValueError(
                f"Unsupported document type '{document_type}'. "
                f"Supported: {[d.value for d in DocumentType]}"
            )

        content = await self._doc_pipeline.generate(ctx, doc_type, provider=provider)

        # Record the generated document in context
        version_id = str(_uuid.uuid4())
        ctx.add_document_ref(doc_type.value, version_id)
        ctx.turn_count += 1

        # Persist to DB: ensure a Project exists and save DocumentVersion
        resolved_project_id = await self._save_document_version(
            session_id=session_id,
            ctx=ctx,
            doc_type=doc_type,
            content=content,
            version_id=version_id,
            db=db,
        )

        await self._context_manager.save(ctx, db)
        return content, version_id, resolved_project_id

    async def _save_document_version(
        self,
        session_id: str,
        ctx: AgentContext,
        doc_type: DocumentType,
        content: str,
        version_id: str,
        db: AsyncSession,
    ) -> Optional[str]:
        """Ensure a Project exists for this session and persist the DocumentVersion.

        Returns the project_id (str) that was used, or None on error.
        """
        from sqlalchemy import select, func
        from app.models.conversation import Conversation
        from app.models.document import Project, DocumentVersion

        try:
            conv_uuid = _uuid.UUID(session_id)
            result = await db.execute(
                select(Conversation).where(Conversation.id == conv_uuid)
            )
            conv = result.scalar_one_or_none()
            if conv is None:
                return None

            # Auto-create a project from domain knowledge if none linked yet
            if conv.project_id is None:
                project_name = (
                    ctx.domain_knowledge.project_name
                    or ctx.domain_knowledge.domain_description
                    or "未命名项目"
                )
                if len(project_name) > 100:
                    project_name = project_name[:100]
                project = Project(
                    name=project_name,
                    description=ctx.domain_knowledge.domain_description or "",
                    domain_name=ctx.domain_knowledge.project_name or "",
                    owner_id=conv.user_id,
                    status="active",
                )
                db.add(project)
                await db.flush()
                conv.project_id = project.id
                project_id_uuid = project.id
            else:
                project_id_uuid = conv.project_id

            # Determine next version number for this doc type in the project
            count_result = await db.execute(
                select(func.count()).select_from(DocumentVersion).where(
                    DocumentVersion.project_id == project_id_uuid,
                    DocumentVersion.document_type == doc_type.value,
                )
            )
            existing_count = count_result.scalar() or 0

            # Mark previous versions of the same type as not current
            prev_result = await db.execute(
                select(DocumentVersion).where(
                    DocumentVersion.project_id == project_id_uuid,
                    DocumentVersion.document_type == doc_type.value,
                    DocumentVersion.is_current == True,  # noqa: E712
                )
            )
            for old_ver in prev_result.scalars().all():
                old_ver.is_current = False

            doc_ver = DocumentVersion(
                id=_uuid.UUID(version_id),
                project_id=project_id_uuid,
                version_number=existing_count + 1,
                content=content,
                document_type=doc_type.value,
                is_current=True,
                staleness_status="CURRENT",
            )
            db.add(doc_ver)
            await db.flush()
            return str(project_id_uuid)
        except Exception:
            # Non-fatal: log but don't fail document generation
            import logging
            logging.getLogger(__name__).exception(
                "Failed to persist DocumentVersion for session %s", session_id
            )
            return None

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _handle_generate_command(
        self,
        ctx: AgentContext,
        session_id: str,
        user_message: str,
        doc_type: DocumentType,
        db: AsyncSession,
        provider: Optional[str],
    ) -> AgentResponse:
        """Handle a /generate [DOC_TYPE] command inside the chat turn.

        Calls the document pipeline directly (skipping the chat AI) so the
        chat endpoint returns quickly.  The generated document is surfaced in
        ``phase_document`` so the frontend can display it in the side panel.
        """
        doc_label = _DOC_TYPE_LABELS.get(doc_type.value, doc_type.value)

        content = await self._doc_pipeline.generate(ctx, doc_type, provider=provider)

        # Record the document in context (same as generate_document())
        version_id = str(_uuid.uuid4())
        ctx.add_document_ref(doc_type.value, version_id)
        ctx.turn_count += 1

        # Persist to DB
        await self._save_document_version(
            session_id=session_id,
            ctx=ctx,
            doc_type=doc_type,
            content=content,
            version_id=version_id,
            db=db,
        )

        ai_reply = (
            f"✅ **{doc_label}**已生成完毕，并已保存到「我的项目」！请查看右侧文档面板。\n\n"
            "您可以继续生成其他类型文档，或输入 `/next` 进入审阅完善阶段。"
        )

        phase_doc = PhaseDocumentResult(
            phase=ctx.current_phase.value,
            title=doc_label,
            content=content,
            rendered_at=datetime.now(timezone.utc),
            turn_count=ctx.turn_count,
        )

        await self._context_manager.save(ctx, db)
        await self._context_manager.append_messages(session_id, user_message, ai_reply, db)

        return AgentResponse(
            reply=ai_reply,
            session_id=session_id,
            phase=ctx.current_phase.value,
            phase_label=PHASE_LABELS.get(ctx.current_phase, ctx.current_phase.value),
            progress=PHASE_PROGRESS.get(ctx.current_phase, 0.0),
            suggestions=_PHASE_SUGGESTIONS.get(ctx.current_phase, []),
            extracted_concepts=self._format_concepts(ctx),
            requirement_changes=self._format_requirement_changes(ctx),
            stale_documents=ctx.get_stale_documents(),
            pending_documents=self._pending_document_types(ctx),
            phase_document=phase_doc,
        )

    def _format_concepts(self, ctx: AgentContext) -> List[Dict[str, Any]]:
        return [
            {
                "name": c.name,
                "type": c.concept_type.value,
                "confidence": c.confidence,
            }
            for c in ctx.domain_knowledge.domain_concepts
        ]

    def _format_requirement_changes(self, ctx: AgentContext) -> List[Dict[str, Any]]:
        return [
            {
                "change_id": c.change_id,
                "change_type": c.change_type.value,
                "description": c.description,
                "affected_documents": c.affected_documents,
            }
            for c in ctx.requirement_changes[-5:]
        ]

    def _pending_document_types(self, ctx: AgentContext) -> List[str]:
        """Return document types that are ready to generate but not yet generated."""
        if ctx.current_phase.value not in {"DOC_GENERATE", "REVIEW_REFINE"}:
            return []
        generated_types = {
            d.document_type for d in ctx.generated_documents
        }
        return [
            dt.value
            for dt in DocumentType
            if dt.value not in generated_types
        ]
