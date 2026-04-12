"""AgentCore: orchestrates the full agent request-response cycle."""

from __future__ import annotations

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
        "输入 /generate DOMAIN_MODEL 生成领域模型文档",
        "输入 /generate BUSINESS_REQUIREMENT 生成业务需求文档",
        "输入 /generate UBIQUITOUS_LANGUAGE 生成通用语言术语表",
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


class AgentCore:
    """Orchestrates the full agent request-response cycle."""

    def __init__(self) -> None:
        self._context_manager = ContextManager()
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

        # 3. Build system prompt
        system_prompt = self._prompt_builder.build(ctx)

        # 4. Call AI (pass full conversation history from context + current message)
        messages = [{"role": "system", "content": system_prompt}]
        # Include recent conversation messages from DB for continuity
        # (We use a minimal representation here; full history is in the DB)
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

        # 9. Persist context
        await self._context_manager.save(ctx, db)

        # 10. Build response
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
    ) -> tuple[str, str]:
        """Generate a DDD document and return (content, version_id).

        Also updates the AgentContext to record the generated document.
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
        import uuid as _uuid

        version_id = str(_uuid.uuid4())
        ctx.add_document_ref(doc_type.value, version_id)
        ctx.turn_count += 1

        await self._context_manager.save(ctx, db)
        return content, version_id

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

    def _pending_document_types(self, ctx: AgentContext) -> List[str]:
        """Return document types that are ready to generate but not yet generated."""
        if ctx.current_phase.value not in {"DOC_GENERATE", "REVIEW_REFINE"}:
            return []
        generated_types = {
            d.document_type for d in ctx.generated_documents
        }
        return [
            f"{dt.value}（{_DOC_TYPE_LABELS.get(dt.value, dt.value)}）"
            for dt in DocumentType
            if dt.value not in generated_types
        ]
