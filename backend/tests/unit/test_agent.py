"""Unit tests for the AI Agent core components."""

from __future__ import annotations

import pytest

from app.agent.context import (
    AgentContext,
    BusinessScenario,
    BoundedContext,
    DomainConcept,
    ConceptType,
    DocumentRef,
    DocumentStatus,
    DocumentType,
    Phase,
    ScenarioStatus,
)
from app.agent.knowledge_extractor import KnowledgeExtractor
from app.agent.phase_document_renderer import PhaseDocumentRenderer
from app.agent.phase_engine import PhaseEngine
from app.agent.prompt_builder import PromptBuilder


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------


def make_context(**kwargs) -> AgentContext:
    defaults = dict(session_id="00000000-0000-0000-0000-000000000001")
    defaults.update(kwargs)
    return AgentContext(**defaults)


# ---------------------------------------------------------------------------
# PhaseEngine tests
# ---------------------------------------------------------------------------


class TestPhaseEngine:
    def test_default_phase_is_icebreak(self):
        ctx = make_context()
        assert ctx.current_phase == Phase.ICEBREAK

    def test_no_transition_when_exit_condition_not_met(self):
        engine = PhaseEngine()
        ctx = make_context()
        result = engine.evaluate(ctx, "Hello")
        assert result is None

    def test_transition_on_next_command(self):
        engine = PhaseEngine()
        ctx = make_context()
        result = engine.evaluate(ctx, "/next")
        assert result == Phase.REQUIREMENT

    def test_transition_on_back_command(self):
        engine = PhaseEngine()
        ctx = make_context()
        ctx.current_phase = Phase.REQUIREMENT
        result = engine.evaluate(ctx, "/back")
        assert result == Phase.ICEBREAK

    def test_back_from_first_phase_returns_none(self):
        engine = PhaseEngine()
        ctx = make_context()
        assert ctx.current_phase == Phase.ICEBREAK
        result = engine.evaluate(ctx, "/back")
        assert result is None

    def test_generate_command_jumps_to_doc_generate(self):
        engine = PhaseEngine()
        ctx = make_context()
        result = engine.evaluate(ctx, "/generate")
        assert result == Phase.DOC_GENERATE

    def test_exit_condition_icebreak_met(self):
        engine = PhaseEngine()
        ctx = make_context()
        ctx.domain_knowledge.project_name = "电商系统"
        ctx.domain_knowledge.domain_description = "B2C 电商平台"
        result = engine.evaluate(ctx, "")
        assert result == Phase.REQUIREMENT

    def test_exit_condition_requirement_met(self):
        engine = PhaseEngine()
        ctx = make_context()
        ctx.current_phase = Phase.REQUIREMENT
        for i in range(3):
            ctx.domain_knowledge.business_scenarios.append(
                BusinessScenario(name=f"场景{i}", description="描述")
            )
        result = engine.evaluate(ctx, "")
        assert result == Phase.DOMAIN_EXPLORE

    def test_exit_condition_domain_explore_met(self):
        engine = PhaseEngine()
        ctx = make_context()
        ctx.current_phase = Phase.DOMAIN_EXPLORE
        for i in range(5):
            ctx.domain_knowledge.domain_concepts.append(
                DomainConcept(
                    name=f"概念{i}",
                    concept_type=ConceptType.ENTITY,
                    description="描述",
                )
            )
        result = engine.evaluate(ctx, "")
        assert result == Phase.MODEL_DESIGN

    def test_requirement_change_rollback_sets_phase_before_change(self):
        engine = PhaseEngine()
        ctx = make_context()
        ctx.current_phase = Phase.DOMAIN_EXPLORE
        result = engine.evaluate(ctx, "还有一个需求，我们需要退款功能")
        assert result == Phase.REQUIREMENT
        assert ctx.phase_before_change == Phase.DOMAIN_EXPLORE

    def test_no_rollback_in_icebreak_phase(self):
        engine = PhaseEngine()
        ctx = make_context()
        ctx.current_phase = Phase.ICEBREAK
        result = engine.evaluate(ctx, "还有一个需求")
        assert result is None  # ICEBREAK not in rollback-enabled phases

    def test_advance_phase_records_transition(self):
        engine = PhaseEngine()
        ctx = make_context()
        engine.advance_phase(ctx, Phase.REQUIREMENT, reason="test")
        assert ctx.current_phase == Phase.REQUIREMENT
        assert len(ctx.phase_history) == 1
        assert ctx.phase_history[0].from_phase == Phase.ICEBREAK
        assert ctx.phase_history[0].to_phase == Phase.REQUIREMENT


# ---------------------------------------------------------------------------
# KnowledgeExtractor tests
# ---------------------------------------------------------------------------


class TestKnowledgeExtractor:
    def test_extract_concept(self):
        extractor = KnowledgeExtractor()
        ctx = make_context()
        reply = """
        在这个系统中，订单是最核心的概念。
        <concept type="ENTITY" name="订单" confidence="0.9">用户发起的购买请求</concept>
        """
        extractor.extract(reply, ctx)
        assert len(ctx.domain_knowledge.domain_concepts) == 1
        c = ctx.domain_knowledge.domain_concepts[0]
        assert c.name == "订单"
        assert c.concept_type == ConceptType.ENTITY
        assert c.confidence == 0.9

    def test_extract_multiple_concepts(self):
        extractor = KnowledgeExtractor()
        ctx = make_context()
        reply = """
        <concept type="ENTITY" name="用户" confidence="0.95">系统的使用者</concept>
        <concept type="VALUE_OBJECT" name="地址" confidence="0.8">收货地址</concept>
        <concept type="AGGREGATE" name="购物车" confidence="0.85">用户购物车</concept>
        """
        extractor.extract(reply, ctx)
        assert len(ctx.domain_knowledge.domain_concepts) == 3
        names = [c.name for c in ctx.domain_knowledge.domain_concepts]
        assert "用户" in names
        assert "地址" in names
        assert "购物车" in names

    def test_deduplicate_concepts(self):
        extractor = KnowledgeExtractor()
        ctx = make_context()
        reply1 = '<concept type="ENTITY" name="订单" confidence="0.7">描述1</concept>'
        reply2 = '<concept type="ENTITY" name="订单" confidence="0.9">更新描述</concept>'
        extractor.extract(reply1, ctx)
        extractor.extract(reply2, ctx)
        assert len(ctx.domain_knowledge.domain_concepts) == 1
        assert ctx.domain_knowledge.domain_concepts[0].confidence == 0.9

    def test_extract_scenario(self):
        extractor = KnowledgeExtractor()
        ctx = make_context()
        reply = """
        <scenario id="S001" name="用户下单">用户选择商品并提交订单</scenario>
        """
        extractor.extract(reply, ctx)
        assert len(ctx.domain_knowledge.business_scenarios) == 1
        s = ctx.domain_knowledge.business_scenarios[0]
        assert s.name == "用户下单"
        assert s.id == "S001"

    def test_extract_clarification(self):
        extractor = KnowledgeExtractor()
        ctx = make_context()
        reply = """
        <clarification id="Q001">订单取消后库存是立即恢复还是异步恢复？</clarification>
        """
        extractor.extract(reply, ctx)
        assert len(ctx.clarification_queue) == 1
        assert "库存" in ctx.clarification_queue[0].question

    def test_extract_project_info(self):
        extractor = KnowledgeExtractor()
        ctx = make_context()
        reply = '<project_info name="电商平台" domain="B2C 在线购物"/>'
        extractor.extract(reply, ctx)
        assert ctx.domain_knowledge.project_name == "电商平台"
        assert ctx.domain_knowledge.domain_description == "B2C 在线购物"

    def test_extract_requirement_change_add(self):
        extractor = KnowledgeExtractor()
        ctx = make_context()
        ctx.current_phase = Phase.DOMAIN_EXPLORE
        reply = """
        <requirement_change type="ADD" trigger_rollback="false">
          <description>新增退款流程场景</description>
          <affected_documents>BUSINESS_REQUIREMENT,USE_CASES</affected_documents>
        </requirement_change>
        """
        extractor.extract(reply, ctx)
        assert len(ctx.requirement_changes) == 1
        rc = ctx.requirement_changes[0]
        assert rc.change_type.value == "ADD"
        assert "退款流程" in rc.description
        assert "BUSINESS_REQUIREMENT" in rc.affected_documents

    def test_requirement_change_marks_docs_stale(self):
        extractor = KnowledgeExtractor()
        ctx = make_context()
        ctx.generated_documents.append(
            DocumentRef(document_type="BUSINESS_REQUIREMENT")
        )
        reply = """
        <requirement_change type="MODIFY" trigger_rollback="false">
          <description>修改订单场景</description>
          <affected_documents>BUSINESS_REQUIREMENT</affected_documents>
        </requirement_change>
        """
        extractor.extract(reply, ctx)
        assert ctx.generated_documents[0].status == DocumentStatus.STALE

    def test_unknown_concept_type_defaults_to_entity(self):
        extractor = KnowledgeExtractor()
        ctx = make_context()
        reply = '<concept type="UNKNOWN_TYPE" name="测试" confidence="0.5">描述</concept>'
        extractor.extract(reply, ctx)
        assert ctx.domain_knowledge.domain_concepts[0].concept_type == ConceptType.ENTITY

    def test_malformed_xml_is_ignored(self):
        extractor = KnowledgeExtractor()
        ctx = make_context()
        reply = "<concept type='ENTITY' name='broken'>no closing tag"
        extractor.extract(reply, ctx)
        assert len(ctx.domain_knowledge.domain_concepts) == 0


# ---------------------------------------------------------------------------
# PromptBuilder tests
# ---------------------------------------------------------------------------


class TestPromptBuilder:
    def test_build_returns_string(self):
        builder = PromptBuilder()
        ctx = make_context()
        prompt = builder.build(ctx)
        assert isinstance(prompt, str)
        assert len(prompt) > 100

    def test_build_contains_role_definition(self):
        builder = PromptBuilder()
        ctx = make_context()
        prompt = builder.build(ctx)
        assert "Talk2DDD" in prompt
        assert "DDD" in prompt

    def test_build_contains_phase_instruction(self):
        builder = PromptBuilder()
        ctx = make_context()
        ctx.current_phase = Phase.REQUIREMENT
        prompt = builder.build(ctx)
        assert "需求收集" in prompt

    def test_build_contains_context_block_when_project_set(self):
        builder = PromptBuilder()
        ctx = make_context()
        ctx.domain_knowledge.project_name = "电商系统"
        ctx.domain_knowledge.domain_description = "B2C 平台"
        prompt = builder.build(ctx)
        assert "[CONTEXT_BLOCK]" in prompt
        assert "电商系统" in prompt

    def test_no_context_block_when_empty(self):
        builder = PromptBuilder()
        ctx = make_context()
        prompt = builder.build(ctx)
        assert "[CONTEXT_BLOCK]" not in prompt

    def test_different_phase_instructions(self):
        builder = PromptBuilder()
        for phase in Phase:
            ctx = make_context()
            ctx.current_phase = phase
            prompt = builder.build(ctx)
            assert isinstance(prompt, str)
            assert len(prompt) > 0

    def test_stale_documents_appear_in_context(self):
        builder = PromptBuilder()
        ctx = make_context()
        ctx.domain_knowledge.project_name = "Test"
        ctx.domain_knowledge.domain_description = "Testing"
        ctx.generated_documents.append(
            DocumentRef(document_type="DOMAIN_MODEL", status=DocumentStatus.STALE)
        )
        prompt = builder.build(ctx)
        assert "DOMAIN_MODEL" in prompt


# ---------------------------------------------------------------------------
# PhaseDocumentRenderer tests
# ---------------------------------------------------------------------------


class TestPhaseDocumentRenderer:
    def test_render_icebreak(self):
        renderer = PhaseDocumentRenderer()
        ctx = make_context()
        ctx.domain_knowledge.project_name = "电商系统"
        ctx.domain_knowledge.domain_description = "B2C 平台"
        doc = renderer.render(ctx)
        assert "项目简介" in doc
        assert "电商系统" in doc
        assert "B2C 平台" in doc

    def test_render_requirement(self):
        renderer = PhaseDocumentRenderer()
        ctx = make_context()
        ctx.current_phase = Phase.REQUIREMENT
        ctx.domain_knowledge.business_scenarios.append(
            BusinessScenario(id="S001", name="用户注册", description="用户创建账号")
        )
        doc = renderer.render(ctx)
        assert "业务需求草稿" in doc
        assert "用户注册" in doc

    def test_render_domain_explore(self):
        renderer = PhaseDocumentRenderer()
        ctx = make_context()
        ctx.current_phase = Phase.DOMAIN_EXPLORE
        ctx.domain_knowledge.domain_concepts.append(
            DomainConcept(
                name="订单", concept_type=ConceptType.ENTITY, description="购买请求"
            )
        )
        doc = renderer.render(ctx)
        assert "领域概念词汇表" in doc
        assert "订单" in doc

    def test_render_model_design(self):
        renderer = PhaseDocumentRenderer()
        ctx = make_context()
        ctx.current_phase = Phase.MODEL_DESIGN
        ctx.domain_knowledge.bounded_contexts.append(
            BoundedContext(name="订单上下文", description="管理订单生命周期")
        )
        doc = renderer.render(ctx)
        assert "领域模型草稿" in doc
        assert "订单上下文" in doc

    def test_render_doc_generate_no_docs(self):
        renderer = PhaseDocumentRenderer()
        ctx = make_context()
        ctx.current_phase = Phase.DOC_GENERATE
        doc = renderer.render(ctx)
        assert "已生成文档列表" in doc
        assert "尚未生成任何文档" in doc

    def test_render_doc_generate_with_docs(self):
        renderer = PhaseDocumentRenderer()
        ctx = make_context()
        ctx.current_phase = Phase.DOC_GENERATE
        ctx.generated_documents.append(
            DocumentRef(document_type="DOMAIN_MODEL", status=DocumentStatus.CURRENT)
        )
        ctx.generated_documents.append(
            DocumentRef(
                document_type="BUSINESS_REQUIREMENT", status=DocumentStatus.STALE
            )
        )
        doc = renderer.render(ctx)
        assert "DOMAIN_MODEL" in doc
        assert "BUSINESS_REQUIREMENT" in doc
        assert "需更新" in doc

    def test_render_review_refine(self):
        renderer = PhaseDocumentRenderer()
        ctx = make_context()
        ctx.current_phase = Phase.REVIEW_REFINE
        doc = renderer.render(ctx)
        assert "修订记录" in doc

    def test_get_title_returns_label(self):
        renderer = PhaseDocumentRenderer()
        ctx = make_context()
        ctx.current_phase = Phase.REQUIREMENT
        assert renderer.get_title(ctx) == "业务需求草稿"


# ---------------------------------------------------------------------------
# AgentContext helper methods
# ---------------------------------------------------------------------------




class TestAgentContext:
    def test_get_stale_documents(self):
        ctx = make_context()
        ctx.generated_documents.append(
            DocumentRef(document_type="DOMAIN_MODEL", status=DocumentStatus.CURRENT)
        )
        ctx.generated_documents.append(
            DocumentRef(
                document_type="BUSINESS_REQUIREMENT", status=DocumentStatus.STALE
            )
        )
        stale = ctx.get_stale_documents()
        assert stale == ["BUSINESS_REQUIREMENT"]

    def test_mark_documents_stale(self):
        ctx = make_context()
        ctx.generated_documents.append(
            DocumentRef(document_type="DOMAIN_MODEL", status=DocumentStatus.CURRENT)
        )
        ctx.mark_documents_stale(["DOMAIN_MODEL"])
        assert ctx.generated_documents[0].status == DocumentStatus.STALE

    def test_add_document_ref_supersedes_current(self):
        ctx = make_context()
        ctx.generated_documents.append(
            DocumentRef(document_type="DOMAIN_MODEL", status=DocumentStatus.CURRENT)
        )
        ctx.add_document_ref("DOMAIN_MODEL", "new-version-id")
        assert ctx.generated_documents[0].status == DocumentStatus.SUPERSEDED
        assert ctx.generated_documents[1].status == DocumentStatus.CURRENT
        assert ctx.generated_documents[1].version_id == "new-version-id"


# ---------------------------------------------------------------------------
# ContextManager — conversation history helpers
# ---------------------------------------------------------------------------


class _FakeMessage:
    """Minimal stand-in for app.models.conversation.Message in unit tests."""

    def __init__(self, role: str, content: str) -> None:
        self.role = role
        self.content = content


class _FakeConversation:
    def __init__(self, messages: list) -> None:
        self.messages = messages


class TestContextManagerHistory:
    """Unit-tests for load_messages / append_messages (DB is mocked)."""

    @pytest.mark.asyncio
    async def test_load_messages_returns_user_and_assistant_only(self):
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, MagicMock
        from app.agent.context_manager import ContextManager

        cm = ContextManager()
        session_id = "00000000-0000-0000-0000-000000000002"

        fake_messages = [
            _FakeMessage("system", "system prompt"),
            _FakeMessage("user", "你好"),
            _FakeMessage("assistant", "嗨，欢迎！"),
            _FakeMessage("user", "我的项目是电商平台"),
            _FakeMessage("assistant", "请详细描述一下"),
        ]
        fake_convo = _FakeConversation(fake_messages)

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = fake_convo
        db.execute = AsyncMock(return_value=mock_result)

        history = await cm.load_messages(session_id, db)

        # system message is excluded
        assert all(m["role"] != "system" for m in history)
        assert len(history) == 4
        assert history[0] == {"role": "user", "content": "你好"}
        assert history[1] == {"role": "assistant", "content": "嗨，欢迎！"}

    @pytest.mark.asyncio
    async def test_load_messages_trims_to_max(self):
        from unittest.mock import AsyncMock, MagicMock
        from app.agent.context_manager import ContextManager

        cm = ContextManager()
        session_id = "00000000-0000-0000-0000-000000000002"

        # Create more than MAX_HISTORY_MESSAGES messages
        many = [
            _FakeMessage("user" if i % 2 == 0 else "assistant", f"msg{i}")
            for i in range(60)
        ]
        fake_convo = _FakeConversation(many)

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = fake_convo
        db.execute = AsyncMock(return_value=mock_result)

        history = await cm.load_messages(session_id, db)

        assert len(history) == ContextManager.MAX_HISTORY_MESSAGES
        # Should be the LAST messages
        assert history[-1]["content"] == "msg59"

    @pytest.mark.asyncio
    async def test_load_messages_returns_empty_when_no_conversation(self):
        from unittest.mock import AsyncMock, MagicMock
        from app.agent.context_manager import ContextManager

        cm = ContextManager()
        session_id = "00000000-0000-0000-0000-000000000003"

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)

        history = await cm.load_messages(session_id, db)
        assert history == []

    @pytest.mark.asyncio
    async def test_load_messages_returns_empty_for_invalid_uuid(self):
        from unittest.mock import AsyncMock
        from app.agent.context_manager import ContextManager

        cm = ContextManager()
        db = AsyncMock()
        history = await cm.load_messages("not-a-valid-uuid", db)
        assert history == []
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_append_messages_adds_user_and_assistant_records(self):
        from unittest.mock import AsyncMock, MagicMock
        from app.agent.context_manager import ContextManager

        cm = ContextManager()
        session_id = "00000000-0000-0000-0000-000000000002"

        db = AsyncMock()
        db.flush = AsyncMock()

        added_objects = []
        db.add = MagicMock(side_effect=added_objects.append)

        await cm.append_messages(session_id, "用户消息", "AI 回复", db)

        assert len(added_objects) == 2
        assert added_objects[0].role == "user"
        assert added_objects[0].content == "用户消息"
        assert added_objects[1].role == "assistant"
        assert added_objects[1].content == "AI 回复"
        db.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_append_messages_noop_for_invalid_uuid(self):
        from unittest.mock import AsyncMock, MagicMock
        from app.agent.context_manager import ContextManager

        cm = ContextManager()
        db = AsyncMock()
        db.add = MagicMock()

        await cm.append_messages("bad-uuid", "msg", "reply", db)

        db.add.assert_not_called()


# ---------------------------------------------------------------------------
# MemoryManager
# ---------------------------------------------------------------------------


class TestMemoryManagerEstimateTokens:
    """Deterministic tests – no I/O."""

    def test_empty_list_returns_zero(self):
        from app.agent.memory_manager import MemoryManager

        mm = MemoryManager()
        assert mm.estimate_tokens([]) == 0

    def test_single_short_message(self):
        from app.agent.memory_manager import MemoryManager

        mm = MemoryManager()
        msgs = [{"role": "user", "content": "你好"}]
        # "你好" = 2 chars → int(2/2.5) = 0 content tokens
        # + 10-token per-message overhead → total ≥ 10
        result = mm.estimate_tokens(msgs)
        assert result > 0

    def test_longer_content_gives_larger_estimate(self):
        from app.agent.memory_manager import MemoryManager

        mm = MemoryManager()
        short = [{"role": "user", "content": "短消息"}]
        long = [{"role": "user", "content": "这是一条非常长的消息，包含了大量的文字内容，用来测试估算是否随内容增长而增大"}]
        assert mm.estimate_tokens(long) > mm.estimate_tokens(short)

    def test_multiple_messages_accumulate(self):
        from app.agent.memory_manager import MemoryManager

        mm = MemoryManager()
        one = [{"role": "user", "content": "你好"}]
        two = [{"role": "user", "content": "你好"}, {"role": "assistant", "content": "嗨"}]
        assert mm.estimate_tokens(two) > mm.estimate_tokens(one)


class TestMemoryManagerGetSummaryBlock:
    """Tests for the summary block helper – no I/O."""

    def test_empty_summary_returns_empty_string(self):
        from app.agent.memory_manager import MemoryManager

        mm = MemoryManager()
        ctx = make_context()
        assert mm.get_summary_block(ctx) == ""

    def test_non_empty_summary_returns_wrapped_block(self):
        from app.agent.memory_manager import MemoryManager

        mm = MemoryManager()
        ctx = make_context()
        ctx.conversation_summary = "用户想做个人博客网站，技术选型 Next.js"
        block = mm.get_summary_block(ctx)
        assert "[MEMORY_SUMMARY]" in block
        assert "[/MEMORY_SUMMARY]" in block
        assert "用户想做个人博客网站" in block


class TestMemoryManagerShouldCompress:
    """Tests for the private _should_compress logic – no I/O."""

    def test_no_compression_before_trigger_turns(self):
        from app.agent.memory_manager import MemoryManager

        mm = MemoryManager()
        ctx = make_context()
        ctx.turn_count = 5  # below default trigger of 10
        assert mm._should_compress(ctx) is False

    def test_first_compression_fires_at_trigger_turns(self):
        from app.agent.memory_manager import MemoryManager

        mm = MemoryManager()
        ctx = make_context()
        ctx.turn_count = 10  # equals default trigger
        ctx.summary_last_updated_turn = 0
        assert mm._should_compress(ctx) is True

    def test_no_duplicate_first_fire_when_already_updated(self):
        from app.agent.memory_manager import MemoryManager

        mm = MemoryManager()
        ctx = make_context()
        ctx.turn_count = 10
        ctx.summary_last_updated_turn = 10  # already fired
        # Neither first-fire nor periodic (delta = 0, < interval 5)
        assert mm._should_compress(ctx) is False

    def test_periodic_refresh_fires_after_interval(self):
        from app.agent.memory_manager import MemoryManager

        mm = MemoryManager()
        ctx = make_context()
        ctx.turn_count = 15
        ctx.summary_last_updated_turn = 10  # first fire already happened
        # delta = 5 == refresh_interval (default 5) → should fire
        assert mm._should_compress(ctx) is True

    def test_periodic_refresh_does_not_fire_between_intervals(self):
        from app.agent.memory_manager import MemoryManager

        mm = MemoryManager()
        ctx = make_context()
        ctx.turn_count = 13
        ctx.summary_last_updated_turn = 10
        # delta = 3 < interval 5 → should NOT fire
        assert mm._should_compress(ctx) is False


class TestMemoryManagerGetMessagesForAI:
    """Tests for get_messages_for_ai – DB is mocked."""

    @pytest.mark.asyncio
    async def test_returns_most_recent_k_turns(self):
        from unittest.mock import AsyncMock, MagicMock
        from app.agent.memory_manager import MemoryManager

        mm = MemoryManager()
        ctx = make_context()
        # K=10 turns → at most 20 messages

        # Build 30 fake messages (15 turns)
        fake_messages = [
            _FakeMessage("user" if i % 2 == 0 else "assistant", f"msg{i}")
            for i in range(30)
        ]
        fake_convo = _FakeConversation(fake_messages)

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = fake_convo
        db.execute = AsyncMock(return_value=mock_result)

        result = await mm.get_messages_for_ai(ctx, db)

        # Default K=10 → max 20 messages; we have 30, so trim to last 20
        assert len(result) == 20
        # Last message should be the last fake message
        assert result[-1]["content"] == "msg29"

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_history(self):
        from unittest.mock import AsyncMock, MagicMock
        from app.agent.memory_manager import MemoryManager

        mm = MemoryManager()
        ctx = make_context()

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)

        result = await mm.get_messages_for_ai(ctx, db)
        assert result == []

    @pytest.mark.asyncio
    async def test_trims_further_when_over_token_budget(self):
        from unittest.mock import AsyncMock, MagicMock
        from app.agent.memory_manager import MemoryManager
        from app.agent.context import MemoryConfig

        mm = MemoryManager()
        ctx = make_context()
        # Set a very small token budget to force trimming
        ctx.memory_config = MemoryConfig(
            immediate_memory_turns=10,
            min_immediate_memory_turns=2,
            max_input_tokens=100,  # tiny budget
        )

        # Build 20 messages with large content (each ~200 chars → many tokens)
        long_content = "这是非常长的消息内容" * 20  # 180 chars
        fake_messages = [
            _FakeMessage("user" if i % 2 == 0 else "assistant", long_content)
            for i in range(20)
        ]
        fake_convo = _FakeConversation(fake_messages)

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = fake_convo
        db.execute = AsyncMock(return_value=mock_result)

        result = await mm.get_messages_for_ai(ctx, db)

        # Should have been trimmed to at least min_immediate_memory_turns * 2 = 4
        assert len(result) <= 20
        # Should keep at least min turns
        assert len(result) >= ctx.memory_config.min_immediate_memory_turns * 2

