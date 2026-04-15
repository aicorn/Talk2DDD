"""AgentCore: orchestrates the full agent request-response cycle."""

from __future__ import annotations

import uuid as _uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.context import (
    AgentContext,
    Phase,
    PHASE_LABELS,
    PHASE_PROGRESS,
    TechStackPreferences,
)
from app.agent.context_manager import ContextManager
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
    phase_document: Optional[PhaseDocumentResult]
    tech_stack_preferences: Optional[Dict[str, Any]] = None
    phase_changed: bool = False


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
        "输入 /techstack 设置技术栈偏好",
        "输入 /next 进入审阅完善阶段",
    ],
    Phase.REVIEW_REFINE: [
        "请在「我的项目」中审阅各阶段文档",
        "如需修改，请直接描述修改内容",
        "输入 /complete 标记项目完成",
    ],
}

# Per-phase trigger messages sent as the user turn when the user manually
# switches phases.  These are internal system messages and are NOT persisted
# to the user-visible message history.
_PHASE_SWITCH_TRIGGERS: dict[Phase, str] = {
    Phase.ICEBREAK: (
        "[系统] 用户手动切换回「破冰引入」阶段（P1）。"
        "请简短告知用户当前处于哪个阶段，说明此阶段的目标，并提出第一个引导问题。"
    ),
    Phase.REQUIREMENT: (
        "[系统] 用户手动进入「需求收集」阶段（P2）。"
        "请简短告知用户此阶段目标（梳理业务场景），总结已收集到的场景数量，"
        "并引导用户继续补充或澄清下一个场景。"
    ),
    Phase.DOMAIN_EXPLORE: (
        "[系统] 用户手动进入「领域探索」阶段（P3）。"
        "请简短告知此阶段目标（识别领域概念、建立通用语言），总结已识别的概念，"
        "并提出第一个领域探索问题。"
    ),
    Phase.MODEL_DESIGN: (
        "[系统] 用户手动进入「模型设计」阶段（P4）。"
        "请简短告知此阶段目标（设计聚合、划定限界上下文），总结已有概念，"
        "并提出第一个聚合边界问题。"
    ),
    Phase.REVIEW_REFINE: (
        "[系统] 用户手动进入「审阅完善」阶段（P5）。"
        "请简短告知此阶段目标（审阅各阶段文档、收集反馈），"
        "告知用户可以在「我的项目」中查阅最新文档，并提出修改意见。"
    ),
}


class AgentCore:
    """Orchestrates the full agent request-response cycle."""

    def __init__(self) -> None:
        self._context_manager = ContextManager()
        self._memory_manager = MemoryManager()
        self._phase_engine = PhaseEngine()
        self._prompt_builder = PromptBuilder()
        self._knowledge_extractor = KnowledgeExtractor()
        self._doc_renderer = PhaseDocumentRenderer()

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
        prev_ts_confirmed = ctx.tech_stack_preferences.confirmed
        self._knowledge_extractor.extract(ai_reply, ctx)

        # 5b. In the ICEBREAK phase, run a dedicated project-info extraction pass to
        #     ensure the project name and domain background discussed in the
        #     conversation are captured even when the conversational AI omitted
        #     <project_info> tags.
        if ctx.current_phase == Phase.ICEBREAK:
            await self._reconcile_project_info(
                ctx=ctx,
                user_message=message,
                ai_reply=ai_reply,
                provider=provider,
            )

        # 5c. In the REQUIREMENT phase, run a dedicated scenario-extraction pass to
        #     ensure all business items discussed in the conversation are captured in
        #     the context even when the conversational AI omitted <scenario> tags.
        if ctx.current_phase == Phase.REQUIREMENT:
            await self._reconcile_scenarios(
                ctx=ctx,
                user_message=message,
                ai_reply=ai_reply,
                provider=provider,
            )

        # 5d. In the DOMAIN_EXPLORE phase, run a dedicated concept-extraction pass to
        #     ensure all domain concepts discussed in the conversation are captured in
        #     the context even when the conversational AI omitted <concept> tags.
        if ctx.current_phase == Phase.DOMAIN_EXPLORE:
            await self._reconcile_domain_concepts(
                ctx=ctx,
                user_message=message,
                ai_reply=ai_reply,
                provider=provider,
            )

        # 6. Increment turn counter
        ctx.turn_count += 1

        # 7. Render phase document
        phase_doc_content = self._doc_renderer.render(ctx)
        phase_doc_title = self._doc_renderer.get_title(ctx)
        phase_doc = PhaseDocumentResult(
            phase=ctx.current_phase.value,
            title=phase_doc_title,
            content=phase_doc_content,
            rendered_at=datetime.now(timezone.utc),
            turn_count=ctx.turn_count,
        )

        # 8. Persist context and conversation messages
        await self._context_manager.save(ctx, db)
        await self._context_manager.append_messages(session_id, message, ai_reply, db)

        # 9. Auto-save phase document to project (non-fatal)
        await self._save_phase_document_to_project(
            session_id=session_id,
            ctx=ctx,
            phase=ctx.current_phase,
            content=phase_doc_content,
            db=db,
        )

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
            phase_document=phase_doc,
            tech_stack_preferences=self._format_tech_stack(ctx),
        )

    async def switch_phase(
        self,
        session_id: str,
        direction: str,
        db: AsyncSession,
        provider: Optional[str] = None,
    ) -> AgentResponse:
        """Manually advance or retreat one phase, then generate a phase-intro message.

        Args:
            session_id: The conversation session UUID.
            direction: ``"next"`` to advance one phase, ``"back"`` to retreat one.
            db: Active database session.
            provider: Optional AI provider override.

        Raises:
            ValueError: If *direction* is invalid or the session is already at the
                boundary phase in the requested direction.
        """
        # 1. Load context
        ctx = await self._context_manager.load(session_id, db)

        # 2. Compute target phase via the public PhaseEngine method
        new_phase = self._phase_engine.get_adjacent_phase(ctx, direction)
        # get_adjacent_phase raises ValueError for invalid direction already

        if new_phase is None:
            raise ValueError(
                f"Already at the {'last' if direction == 'next' else 'first'} phase "
                f"({ctx.current_phase.value}); cannot navigate further."
            )

        # 3. Apply phase transition
        reason = f"manual-switch ({direction}): {ctx.current_phase.value} → {new_phase.value}"
        self._phase_engine.advance_phase(ctx, new_phase, reason)

        # 4. Build system prompt with phase-switch instruction appended
        summary_block = self._memory_manager.get_summary_block(ctx)
        system_prompt = self._prompt_builder.build(
            ctx,
            memory_summary_block=summary_block,
            phase_switch_trigger=True,
        )

        # 5. Retrieve immediate message history (Layer 1) and call AI
        history = await self._memory_manager.get_messages_for_ai(ctx, db)

        # For DOMAIN_EXPLORE: extract initial domain concepts from Phase 2 scenarios,
        # then embed the rendered initial document in the trigger message so the AI
        # can present it to the user and invite feedback.
        if ctx.current_phase == Phase.DOMAIN_EXPLORE:
            await self._generate_initial_domain_concepts(ctx, provider=provider)
            initial_doc = self._doc_renderer.render(ctx)
            trigger_msg = (
                "[系统] 用户手动进入「领域探索」阶段（P3）。\n"
                "系统已根据上一阶段收集的业务场景，自动提炼了初版「领域概念词汇表」，内容如下：\n\n"
                f"{initial_doc}\n\n"
                "请向用户展示这份初版领域概念词汇表，说明这是根据业务场景自动生成的初版，"
                "邀请用户提出修改意见，并引导进入下一个领域探索问题。"
            )
        else:
            trigger_msg = _PHASE_SWITCH_TRIGGERS.get(
                ctx.current_phase,
                f"[系统] 用户切换到阶段 {ctx.current_phase.value}。",
            )
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": trigger_msg})

        ai_reply = await chat_completion(messages=messages, provider=provider)

        # 6. Extract any domain knowledge embedded in the AI reply
        self._knowledge_extractor.extract(ai_reply, ctx)

        # 7. Increment turn counter
        ctx.turn_count += 1

        # 8. Render the phase document for the new phase
        phase_doc_content = self._doc_renderer.render(ctx)
        phase_doc_title = self._doc_renderer.get_title(ctx)
        phase_doc = PhaseDocumentResult(
            phase=ctx.current_phase.value,
            title=phase_doc_title,
            content=phase_doc_content,
            rendered_at=datetime.now(timezone.utc),
            turn_count=ctx.turn_count,
        )

        # 9. Persist context and the AI reply (trigger message is an internal
        #    system action and is not stored in user-visible history)
        await self._context_manager.save(ctx, db)
        await self._context_manager.append_assistant_only(session_id, ai_reply, db)

        # 10. Auto-save phase document to project (non-fatal)
        await self._save_phase_document_to_project(
            session_id=session_id,
            ctx=ctx,
            phase=ctx.current_phase,
            content=phase_doc_content,
            db=db,
        )

        # 11. Async memory compression (does not block response)
        await self._memory_manager.maybe_compress(ctx, provider=provider)

        # 12. Build and return response
        return AgentResponse(
            reply=ai_reply,
            session_id=session_id,
            phase=ctx.current_phase.value,
            phase_label=PHASE_LABELS.get(ctx.current_phase, ctx.current_phase.value),
            progress=PHASE_PROGRESS.get(ctx.current_phase, 0.0),
            suggestions=_PHASE_SUGGESTIONS.get(ctx.current_phase, []),
            extracted_concepts=self._format_concepts(ctx),
            requirement_changes=self._format_requirement_changes(ctx),
            phase_document=phase_doc,
            tech_stack_preferences=self._format_tech_stack(ctx),
            phase_changed=True,
        )

    async def _reconcile_project_info(
        self,
        ctx: AgentContext,
        user_message: str,
        ai_reply: str,
        provider: Optional[str] = None,
    ) -> None:
        """Run a dedicated extractor AI call to reconcile Phase 1 project info.

        This is the "Extractor Role" in the dual-role pattern for Phase 1
        (ICEBREAK).  After the main conversational AI response has been
        processed, a second lightweight AI call is made whose only job is to
        extract the project name and domain background from the exchange and
        return them as a JSON object.  The result is merged into
        ``ctx.domain_knowledge`` so the P1 phase document is always in sync
        with what was discussed even when the conversational AI omitted
        ``<project_info>`` tags.

        This call is non-fatal: any exception is silently logged and the
        regular flow continues uninterrupted.
        """
        import logging as _logging

        _log = _logging.getLogger(__name__)

        # Skip if both fields are already populated — nothing more to extract.
        if (
            ctx.domain_knowledge.project_name
            and ctx.domain_knowledge.domain_description
        ):
            return

        try:
            reconcile_prompt = self._prompt_builder.build_project_info_reconcile_prompt(
                ctx, user_message, ai_reply
            )
            messages = [{"role": "user", "content": reconcile_prompt}]
            json_reply = await chat_completion(messages=messages, provider=provider)
            updated = self._knowledge_extractor.merge_project_info_from_json(
                json_reply, ctx
            )
            if updated:
                _log.info(
                    "Project info reconciler updated context for session %s "
                    "(turn %d): project_name=%r domain_description=%r",
                    ctx.session_id,
                    ctx.turn_count,
                    ctx.domain_knowledge.project_name,
                    ctx.domain_knowledge.domain_description,
                )
            else:
                _log.warning(
                    "Project info reconciler ran but extracted nothing for "
                    "session %s (turn %d). Check if project name or domain "
                    "background was mentioned but not captured.",
                    ctx.session_id,
                    ctx.turn_count,
                )
        except Exception:
            _log.debug(
                "Project info reconciliation failed for session %s (non-fatal)",
                ctx.session_id,
                exc_info=True,
            )

    async def _reconcile_scenarios(
        self,
        ctx: AgentContext,
        user_message: str,
        ai_reply: str,
        provider: Optional[str] = None,
    ) -> None:
        """Run a dedicated extractor AI call to reconcile business scenarios.

        This is the "Extractor Role" in the dual-role pattern for Phase 2.
        After the main conversational AI response has been processed, a second
        lightweight AI call is made whose only job is to identify ALL business
        scenarios mentioned in the current exchange and return them as JSON.
        The result is merged into ``ctx.domain_knowledge.business_scenarios``
        so the phase document is always in sync with what was discussed.

        This call is non-fatal: any exception is silently logged and the
        regular flow continues uninterrupted.
        """
        import logging as _logging

        _log = _logging.getLogger(__name__)
        count_before = len(ctx.domain_knowledge.business_scenarios)

        try:
            extraction_prompt = self._prompt_builder.build_scenario_extraction_prompt(
                ctx, user_message, ai_reply
            )
            messages = [{"role": "user", "content": extraction_prompt}]
            json_reply = await chat_completion(messages=messages, provider=provider)
            added = int(
                self._knowledge_extractor.merge_scenarios_from_json(json_reply, ctx)
                or 0
            )
            if added > 0:
                _log.info(
                    "Scenario reconciler added %d new scenario(s) for session %s "
                    "(turn %d, total=%d)",
                    added,
                    ctx.session_id,
                    ctx.turn_count,
                    len(ctx.domain_knowledge.business_scenarios),
                )
            else:
                _log.warning(
                    "Scenario reconciler ran but added 0 new scenarios for session %s "
                    "(turn %d, existing=%d). Check if a scenario was confirmed in the "
                    "conversation but not captured.",
                    ctx.session_id,
                    ctx.turn_count,
                    count_before,
                )
        except Exception:
            _log.debug(
                "Scenario reconciliation failed for session %s (non-fatal)",
                ctx.session_id,
                exc_info=True,
            )

    async def _generate_initial_domain_concepts(
        self,
        ctx: AgentContext,
        provider: Optional[str] = None,
    ) -> None:
        """Extract initial domain concepts from Phase 2 business scenarios.

        This is called once when the session enters DOMAIN_EXPLORE so that the
        opening phase document already contains a seed set of concepts derived
        from all collected business scenarios.  The result is merged into
        ``ctx.domain_knowledge.domain_concepts``.

        This call is non-fatal: any exception is silently logged and the phase
        switch continues uninterrupted (the document will simply be empty).
        """
        import logging as _logging

        try:
            extraction_prompt = (
                self._prompt_builder.build_initial_domain_concept_extraction_prompt(ctx)
            )
            if not extraction_prompt:
                return
            messages = [{"role": "user", "content": extraction_prompt}]
            json_reply = await chat_completion(messages=messages, provider=provider)
            self._knowledge_extractor.merge_concepts_from_json(json_reply, ctx)
        except Exception:
            _logging.getLogger(__name__).debug(
                "Initial domain concept extraction failed for session %s (non-fatal)",
                ctx.session_id,
                exc_info=True,
            )

    async def _reconcile_domain_concepts(
        self,
        ctx: AgentContext,
        user_message: str,
        ai_reply: str,
        provider: Optional[str] = None,
    ) -> None:
        """Run a dedicated extractor AI call to reconcile domain concepts.

        This is the "Extractor Role" in the dual-role pattern for Phase 3.
        After the main conversational AI response has been processed, a second
        lightweight AI call is made whose only job is to identify ALL domain
        concepts mentioned in the current exchange and return them as JSON.
        The result is merged into ``ctx.domain_knowledge.domain_concepts``
        so the phase document is always in sync with what was discussed.

        This call is non-fatal: any exception is silently logged and the
        regular flow continues uninterrupted.
        """
        import logging as _logging

        _log = _logging.getLogger(__name__)
        count_before = len(ctx.domain_knowledge.domain_concepts)

        try:
            reconcile_prompt = self._prompt_builder.build_domain_concept_reconcile_prompt(
                ctx, user_message, ai_reply
            )
            messages = [{"role": "user", "content": reconcile_prompt}]
            json_reply = await chat_completion(messages=messages, provider=provider)
            added = int(
                self._knowledge_extractor.merge_concepts_from_json(json_reply, ctx)
                or 0
            )
            if added > 0:
                _log.info(
                    "Concept reconciler added %d new concept(s) for session %s "
                    "(turn %d, total=%d)",
                    added,
                    ctx.session_id,
                    ctx.turn_count,
                    len(ctx.domain_knowledge.domain_concepts),
                )
            else:
                _log.warning(
                    "Concept reconciler ran but added 0 new concepts for session %s "
                    "(turn %d, existing=%d). Check if a concept was confirmed in the "
                    "conversation but not captured.",
                    ctx.session_id,
                    ctx.turn_count,
                    count_before,
                )
        except Exception:
            _log.debug(
                "Domain concept reconciliation failed for session %s (non-fatal)",
                ctx.session_id,
                exc_info=True,
            )

    async def _save_phase_document_to_project(
        self,
        session_id: str,
        ctx: AgentContext,
        phase: Phase,
        content: str,
        db: AsyncSession,
    ) -> Optional[str]:
        """Save the current phase document to the linked project as a DocumentVersion.

        Uses overwrite semantics: the previous version of the same phase document
        is marked ``is_current=False``, and a new version is inserted.  A Project
        is auto-created from domain knowledge if the conversation has none yet.

        Returns the project_id (str) that was used, or None if skipped / on error.
        """
        from sqlalchemy import select, func
        from app.models.conversation import Conversation
        from app.models.document import Project, DocumentVersion

        if not content.strip():
            return None

        phase_doc_type = f"PHASE_{phase.value}"

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
                ctx.project_id = str(project.id)
                project_id_uuid = project.id
            else:
                project_id_uuid = conv.project_id
                # Keep ctx.project_id in sync
                if ctx.project_id is None:
                    ctx.project_id = str(project_id_uuid)

            # Determine version number for this phase document type
            count_result = await db.execute(
                select(func.count()).select_from(DocumentVersion).where(
                    DocumentVersion.project_id == project_id_uuid,
                    DocumentVersion.document_type == phase_doc_type,
                )
            )
            existing_count = count_result.scalar() or 0

            # Mark previous versions of the same phase as not current
            prev_result = await db.execute(
                select(DocumentVersion).where(
                    DocumentVersion.project_id == project_id_uuid,
                    DocumentVersion.document_type == phase_doc_type,
                    DocumentVersion.is_current == True,  # noqa: E712
                )
            )
            for old_ver in prev_result.scalars().all():
                old_ver.is_current = False

            doc_ver = DocumentVersion(
                id=_uuid.uuid4(),
                project_id=project_id_uuid,
                version_number=existing_count + 1,
                content=content,
                document_type=phase_doc_type,
                is_current=True,
                staleness_status="CURRENT",
            )
            db.add(doc_ver)
            await db.flush()
            return str(project_id_uuid)
        except Exception:
            import logging
            logging.getLogger(__name__).exception(
                "Failed to save phase document for session %s phase %s",
                session_id,
                phase.value,
            )
            return None

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

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

    def _format_tech_stack(self, ctx: AgentContext) -> Optional[Dict[str, Any]]:
        """Return a serialisable dict of tech stack preferences, or None if empty."""
        ts = ctx.tech_stack_preferences
        if not ts.confirmed and ts.is_empty():
            return None
        return {
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
