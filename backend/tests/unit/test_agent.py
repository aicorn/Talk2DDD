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

    def test_generate_command_returns_none(self):
        """The /generate command no longer triggers a phase jump."""
        engine = PhaseEngine()
        ctx = make_context()
        result = engine.evaluate(ctx, "/generate")
        assert result is None

    def test_exit_condition_icebreak_not_auto(self):
        """evaluate() no longer triggers auto phase transitions; returns None."""
        engine = PhaseEngine()
        ctx = make_context()
        ctx.domain_knowledge.project_name = "电商系统"
        ctx.domain_knowledge.domain_description = "B2C 电商平台"
        result = engine.evaluate(ctx, "")
        assert result is None

    def test_exit_condition_requirement_not_auto(self):
        """evaluate() no longer triggers auto phase transitions; returns None."""
        engine = PhaseEngine()
        ctx = make_context()
        ctx.current_phase = Phase.REQUIREMENT
        for i in range(3):
            ctx.domain_knowledge.business_scenarios.append(
                BusinessScenario(name=f"场景{i}", description="描述")
            )
        result = engine.evaluate(ctx, "")
        assert result is None

    def test_exit_condition_domain_explore_not_auto(self):
        """evaluate() no longer triggers auto phase transitions; returns None."""
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
        assert result is None

    def test_requirement_change_signal_returns_none(self):
        """evaluate() no longer handles rollback; requirement change signals are no-ops."""
        engine = PhaseEngine()
        ctx = make_context()
        ctx.current_phase = Phase.DOMAIN_EXPLORE
        result = engine.evaluate(ctx, "还有一个需求，我们需要退款功能")
        assert result is None

    def test_unrecognised_message_returns_none(self):
        engine = PhaseEngine()
        ctx = make_context()
        ctx.current_phase = Phase.ICEBREAK
        result = engine.evaluate(ctx, "还有一个需求")
        assert result is None

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

    def test_extract_scenario_xml_fallback_on_malformed_xml(self):
        """When <scenario> contains a bare & that breaks XML, regex fallback fires."""
        extractor = KnowledgeExtractor()
        ctx = make_context()
        # '&' is invalid in XML without escaping — ET.fromstring() will raise ParseError
        reply = '<scenario id="S003" name="后台内容管理">查看列表 & 编辑更新</scenario>'
        extractor.extract(reply, ctx)
        assert len(ctx.domain_knowledge.business_scenarios) == 1
        s = ctx.domain_knowledge.business_scenarios[0]
        assert s.name == "后台内容管理"
        assert s.id == "S003"

    def test_extract_scenario_xml_fallback_preserves_description(self):
        """Regex fallback preserves the text content as description."""
        extractor = KnowledgeExtractor()
        ctx = make_context()
        reply = '<scenario id="S002" name="用户退款">退款申请 & 审核流程</scenario>'
        extractor.extract(reply, ctx)
        assert ctx.domain_knowledge.business_scenarios[0].description == "退款申请 & 审核流程"

    def test_extract_scenario_xml_fallback_deduplicates(self):
        """Regex fallback still deduplicates by name."""
        extractor = KnowledgeExtractor()
        ctx = make_context()
        # Pre-insert same name
        ctx.domain_knowledge.business_scenarios.append(
            BusinessScenario(id="S001", name="后台内容管理", description="旧描述")
        )
        reply = '<scenario id="S003" name="后台内容管理">新描述 & 新功能</scenario>'
        extractor.extract(reply, ctx)
        assert len(ctx.domain_knowledge.business_scenarios) == 1
        # Description should be updated to the new one (non-empty)
        assert ctx.domain_knowledge.business_scenarios[0].description == "新描述 & 新功能"

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

    # ------------------------------------------------------------------
    # merge_scenarios_from_json tests
    # ------------------------------------------------------------------

    def test_merge_scenarios_from_json_adds_new_scenarios(self):
        extractor = KnowledgeExtractor()
        ctx = make_context()
        json_text = '[{"id": "S001", "name": "用户注册", "description": "用户创建账号"}]'
        added = extractor.merge_scenarios_from_json(json_text, ctx)
        assert added == 1
        assert len(ctx.domain_knowledge.business_scenarios) == 1
        assert ctx.domain_knowledge.business_scenarios[0].name == "用户注册"
        assert ctx.domain_knowledge.business_scenarios[0].id == "S001"

    def test_merge_scenarios_from_json_no_duplicate_by_name(self):
        extractor = KnowledgeExtractor()
        ctx = make_context()
        ctx.domain_knowledge.business_scenarios.append(
            BusinessScenario(id="S001", name="用户注册", description="已有描述")
        )
        json_text = '[{"id": "S001", "name": "用户注册", "description": "另一描述"}]'
        added = extractor.merge_scenarios_from_json(json_text, ctx)
        assert added == 0
        # Original description must not be overwritten
        assert ctx.domain_knowledge.business_scenarios[0].description == "已有描述"

    def test_merge_scenarios_from_json_supplements_empty_description(self):
        extractor = KnowledgeExtractor()
        ctx = make_context()
        ctx.domain_knowledge.business_scenarios.append(
            BusinessScenario(id="S001", name="用户注册", description="")
        )
        json_text = '[{"id": "S001", "name": "用户注册", "description": "用户创建账号"}]'
        extractor.merge_scenarios_from_json(json_text, ctx)
        assert ctx.domain_knowledge.business_scenarios[0].description == "用户创建账号"

    def test_merge_scenarios_from_json_resolves_id_conflict(self):
        extractor = KnowledgeExtractor()
        ctx = make_context()
        ctx.domain_knowledge.business_scenarios.append(
            BusinessScenario(id="S001", name="用户注册", description="描述")
        )
        # Extractor returns a new scenario with a conflicting id
        json_text = '[{"id": "S001", "name": "用户下单", "description": "下单流程"}]'
        added = extractor.merge_scenarios_from_json(json_text, ctx)
        assert added == 1
        ids = [s.id for s in ctx.domain_knowledge.business_scenarios]
        assert ids.count("S001") == 1  # no duplicate id

    def test_merge_scenarios_from_json_handles_empty_array(self):
        extractor = KnowledgeExtractor()
        ctx = make_context()
        added = extractor.merge_scenarios_from_json("[]", ctx)
        assert added == 0
        assert len(ctx.domain_knowledge.business_scenarios) == 0

    def test_merge_scenarios_from_json_handles_invalid_json(self):
        extractor = KnowledgeExtractor()
        ctx = make_context()
        added = extractor.merge_scenarios_from_json("not valid json at all", ctx)
        assert added == 0
        assert len(ctx.domain_knowledge.business_scenarios) == 0

    def test_merge_scenarios_from_json_extracts_array_from_surrounding_text(self):
        extractor = KnowledgeExtractor()
        ctx = make_context()
        json_text = (
            '以下是提取的场景：\n'
            '[{"id": "S001", "name": "商品搜索", "description": "用户搜索商品"}]\n'
            '提取完毕。'
        )
        added = extractor.merge_scenarios_from_json(json_text, ctx)
        assert added == 1
        assert ctx.domain_knowledge.business_scenarios[0].name == "商品搜索"

    def test_merge_scenarios_from_json_skips_items_without_name(self):
        extractor = KnowledgeExtractor()
        ctx = make_context()
        json_text = '[{"id": "S001", "description": "没有名称的场景"}]'
        added = extractor.merge_scenarios_from_json(json_text, ctx)
        assert added == 0

    # ------------------------------------------------------------------
    # merge_concepts_from_json tests
    # ------------------------------------------------------------------

    def test_merge_concepts_from_json_adds_new_concepts(self):
        extractor = KnowledgeExtractor()
        ctx = make_context()
        json_text = '[{"name": "订单", "type": "ENTITY", "description": "用户购买请求", "confidence": 0.9}]'
        added = extractor.merge_concepts_from_json(json_text, ctx)
        assert added == 1
        assert len(ctx.domain_knowledge.domain_concepts) == 1
        c = ctx.domain_knowledge.domain_concepts[0]
        assert c.name == "订单"
        assert c.concept_type == ConceptType.ENTITY
        assert c.confidence == 0.9

    def test_merge_concepts_from_json_no_duplicate_by_name(self):
        extractor = KnowledgeExtractor()
        ctx = make_context()
        ctx.domain_knowledge.domain_concepts.append(
            DomainConcept(name="订单", concept_type=ConceptType.ENTITY, description="已有描述", confidence=0.8)
        )
        json_text = '[{"name": "订单", "type": "ENTITY", "description": "另一描述", "confidence": 0.95}]'
        added = extractor.merge_concepts_from_json(json_text, ctx)
        assert added == 0
        # confidence should be bumped to the higher value
        assert ctx.domain_knowledge.domain_concepts[0].confidence == 0.95
        # existing description should not be overwritten
        assert ctx.domain_knowledge.domain_concepts[0].description == "已有描述"

    def test_merge_concepts_from_json_supplements_empty_description(self):
        extractor = KnowledgeExtractor()
        ctx = make_context()
        ctx.domain_knowledge.domain_concepts.append(
            DomainConcept(name="用户", concept_type=ConceptType.ENTITY, description="", confidence=0.7)
        )
        json_text = '[{"name": "用户", "type": "ENTITY", "description": "系统使用者", "confidence": 0.8}]'
        extractor.merge_concepts_from_json(json_text, ctx)
        assert ctx.domain_knowledge.domain_concepts[0].description == "系统使用者"

    def test_merge_concepts_from_json_handles_empty_array(self):
        extractor = KnowledgeExtractor()
        ctx = make_context()
        added = extractor.merge_concepts_from_json("[]", ctx)
        assert added == 0
        assert len(ctx.domain_knowledge.domain_concepts) == 0

    def test_merge_concepts_from_json_handles_invalid_json(self):
        extractor = KnowledgeExtractor()
        ctx = make_context()
        added = extractor.merge_concepts_from_json("not valid json", ctx)
        assert added == 0

    def test_merge_concepts_from_json_extracts_from_surrounding_text(self):
        extractor = KnowledgeExtractor()
        ctx = make_context()
        json_text = (
            '以下是提取结果：\n'
            '[{"name": "商品", "type": "ENTITY", "description": "可购买的物品", "confidence": 0.85}]\n'
            '完成。'
        )
        added = extractor.merge_concepts_from_json(json_text, ctx)
        assert added == 1
        assert ctx.domain_knowledge.domain_concepts[0].name == "商品"

    def test_merge_concepts_from_json_skips_items_without_name(self):
        extractor = KnowledgeExtractor()
        ctx = make_context()
        json_text = '[{"type": "ENTITY", "description": "没有名称"}]'
        added = extractor.merge_concepts_from_json(json_text, ctx)
        assert added == 0

    def test_merge_concepts_from_json_defaults_unknown_type_to_entity(self):
        extractor = KnowledgeExtractor()
        ctx = make_context()
        json_text = '[{"name": "未知类型概念", "type": "UNKNOWN", "description": "描述", "confidence": 0.7}]'
        extractor.merge_concepts_from_json(json_text, ctx)
        assert ctx.domain_knowledge.domain_concepts[0].concept_type == ConceptType.ENTITY

    def test_merge_concepts_from_json_handles_missing_confidence(self):
        extractor = KnowledgeExtractor()
        ctx = make_context()
        json_text = '[{"name": "支付", "type": "EVENT", "description": "支付事件"}]'
        extractor.merge_concepts_from_json(json_text, ctx)
        assert ctx.domain_knowledge.domain_concepts[0].confidence == 0.8

    # merge_project_info_from_json tests

    def test_merge_project_info_from_json_sets_both_fields(self):
        extractor = KnowledgeExtractor()
        ctx = make_context()
        json_text = '{"project_name": "电商系统", "domain_description": "B2C 电商平台"}'
        updated = extractor.merge_project_info_from_json(json_text, ctx)
        assert updated is True
        assert ctx.domain_knowledge.project_name == "电商系统"
        assert ctx.domain_knowledge.domain_description == "B2C 电商平台"

    def test_merge_project_info_from_json_does_not_overwrite_existing_name(self):
        extractor = KnowledgeExtractor()
        ctx = make_context()
        ctx.domain_knowledge.project_name = "已有项目名"
        json_text = '{"project_name": "新名称", "domain_description": "新描述"}'
        updated = extractor.merge_project_info_from_json(json_text, ctx)
        assert ctx.domain_knowledge.project_name == "已有项目名"
        # domain_description was empty, so it should be filled
        assert ctx.domain_knowledge.domain_description == "新描述"
        assert updated is True

    def test_merge_project_info_from_json_does_not_overwrite_existing_description(self):
        extractor = KnowledgeExtractor()
        ctx = make_context()
        ctx.domain_knowledge.project_name = "已有项目名"
        ctx.domain_knowledge.domain_description = "已有描述"
        json_text = '{"project_name": "新名称", "domain_description": "新描述"}'
        updated = extractor.merge_project_info_from_json(json_text, ctx)
        assert updated is False
        assert ctx.domain_knowledge.project_name == "已有项目名"
        assert ctx.domain_knowledge.domain_description == "已有描述"

    def test_merge_project_info_from_json_handles_invalid_json(self):
        extractor = KnowledgeExtractor()
        ctx = make_context()
        updated = extractor.merge_project_info_from_json("not valid json", ctx)
        assert updated is False

    def test_merge_project_info_from_json_handles_empty_fields(self):
        extractor = KnowledgeExtractor()
        ctx = make_context()
        json_text = '{"project_name": "", "domain_description": ""}'
        updated = extractor.merge_project_info_from_json(json_text, ctx)
        assert updated is False
        assert ctx.domain_knowledge.project_name == ""
        assert ctx.domain_knowledge.domain_description == ""

    def test_merge_project_info_from_json_extracts_from_surrounding_text(self):
        extractor = KnowledgeExtractor()
        ctx = make_context()
        json_text = '好的，提取结果：{"project_name": "物流系统", "domain_description": "货运管理平台"} 完成。'
        updated = extractor.merge_project_info_from_json(json_text, ctx)
        assert updated is True
        assert ctx.domain_knowledge.project_name == "物流系统"

    def test_merge_project_info_from_json_returns_false_when_no_braces(self):
        extractor = KnowledgeExtractor()
        ctx = make_context()
        updated = extractor.merge_project_info_from_json("no braces here", ctx)
        assert updated is False


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

    def test_build_scenario_extraction_prompt_returns_string(self):
        builder = PromptBuilder()
        ctx = make_context()
        prompt = builder.build_scenario_extraction_prompt(
            ctx,
            user_message="我们需要支持用户注册",
            ai_reply="好的，用户注册是一个核心业务场景。",
        )
        assert isinstance(prompt, str)
        assert len(prompt) > 50

    def test_build_scenario_extraction_prompt_includes_existing_scenarios(self):
        builder = PromptBuilder()
        ctx = make_context()
        ctx.domain_knowledge.business_scenarios.append(
            BusinessScenario(id="S001", name="用户注册", description="用户创建账号")
        )
        prompt = builder.build_scenario_extraction_prompt(
            ctx,
            user_message="还有下单功能",
            ai_reply="是的，用户下单也是重要场景。",
        )
        assert "S001" in prompt
        assert "用户注册" in prompt

    def test_build_scenario_extraction_prompt_instructs_json_output(self):
        builder = PromptBuilder()
        ctx = make_context()
        prompt = builder.build_scenario_extraction_prompt(
            ctx,
            user_message="我们有一个报表功能",
            ai_reply="好的，报表功能是一个场景。",
        )
        assert "JSON" in prompt

    def test_build_scenario_extraction_prompt_mentions_xml_fallback(self):
        """Prompt explicitly instructs to include <scenario>-tagged items as XML-parse fallback."""
        builder = PromptBuilder()
        ctx = make_context()
        prompt = builder.build_scenario_extraction_prompt(
            ctx,
            user_message="确认 S003 后台内容管理场景",
            ai_reply='<scenario id="S003" name="后台内容管理">博主登录后台管理内容</scenario>',
        )
        assert "XML" in prompt or "scenario" in prompt

    def test_build_scenario_extraction_prompt_does_not_prohibit_repeats(self):
        """Existing scenarios should be listed but NOT marked as forbidden to return."""
        builder = PromptBuilder()
        ctx = make_context()
        ctx.domain_knowledge.business_scenarios.append(
            BusinessScenario(id="S001", name="用户注册", description="用户创建账号")
        )
        prompt = builder.build_scenario_extraction_prompt(
            ctx,
            user_message="确认 S001 用户注册场景",
            ai_reply="好的，用户注册场景已确认。",
        )
        # Must NOT say "请勿重复" — the merge function handles dedup
        assert "请勿重复" not in prompt

    def test_build_initial_domain_concept_extraction_prompt_returns_empty_when_no_scenarios(self):
        builder = PromptBuilder()
        ctx = make_context()
        prompt = builder.build_initial_domain_concept_extraction_prompt(ctx)
        assert prompt == ""

    def test_build_initial_domain_concept_extraction_prompt_includes_scenarios(self):
        builder = PromptBuilder()
        ctx = make_context()
        ctx.domain_knowledge.business_scenarios.append(
            BusinessScenario(id="S001", name="用户注册", description="用户创建账号")
        )
        prompt = builder.build_initial_domain_concept_extraction_prompt(ctx)
        assert "用户注册" in prompt
        assert "JSON" in prompt

    def test_build_initial_domain_concept_extraction_prompt_excludes_deprecated(self):
        builder = PromptBuilder()
        ctx = make_context()
        ctx.domain_knowledge.business_scenarios.append(
            BusinessScenario(id="S001", name="弃用场景", description="已弃用", status=ScenarioStatus.DEPRECATED)
        )
        prompt = builder.build_initial_domain_concept_extraction_prompt(ctx)
        assert prompt == ""

    def test_build_domain_concept_reconcile_prompt_returns_string(self):
        builder = PromptBuilder()
        ctx = make_context()
        prompt = builder.build_domain_concept_reconcile_prompt(
            ctx,
            user_message="订单是核心概念",
            ai_reply="是的，订单是一个实体。",
        )
        assert isinstance(prompt, str)
        assert "JSON" in prompt

    def test_build_domain_concept_reconcile_prompt_includes_existing_concepts(self):
        builder = PromptBuilder()
        ctx = make_context()
        ctx.domain_knowledge.domain_concepts.append(
            DomainConcept(name="订单", concept_type=ConceptType.ENTITY, description="购买请求")
        )
        prompt = builder.build_domain_concept_reconcile_prompt(
            ctx,
            user_message="还有用户概念",
            ai_reply="用户是系统的使用者。",
        )
        assert "订单" in prompt

    def test_phase_switch_trigger_domain_explore_uses_special_instruction(self):
        builder = PromptBuilder()
        ctx = make_context()
        ctx.current_phase = Phase.DOMAIN_EXPLORE
        prompt = builder.build(ctx, phase_switch_trigger=True)
        assert "领域探索开场" in prompt

    def test_phase_switch_trigger_other_phase_uses_generic_instruction(self):
        builder = PromptBuilder()
        ctx = make_context()
        ctx.current_phase = Phase.REQUIREMENT
        prompt = builder.build(ctx, phase_switch_trigger=True)
        assert "领域探索开场" not in prompt
        assert "阶段切换模式" in prompt

    def test_build_project_info_reconcile_prompt_returns_string(self):
        builder = PromptBuilder()
        ctx = make_context()
        prompt = builder.build_project_info_reconcile_prompt(
            ctx,
            user_message="我们在做一个电商项目",
            ai_reply="好的，您的项目叫电商系统，主要做 B2C 平台。",
        )
        assert isinstance(prompt, str)
        assert "JSON" in prompt

    def test_build_project_info_reconcile_prompt_shows_current_state_when_set(self):
        builder = PromptBuilder()
        ctx = make_context()
        ctx.domain_knowledge.project_name = "电商系统"
        prompt = builder.build_project_info_reconcile_prompt(
            ctx,
            user_message="领域是 B2C",
            ai_reply="好的，领域背景是 B2C 电商平台。",
        )
        assert "电商系统" in prompt

    def test_build_project_info_reconcile_prompt_shows_empty_state(self):
        builder = PromptBuilder()
        ctx = make_context()
        prompt = builder.build_project_info_reconcile_prompt(
            ctx,
            user_message="我们做个系统",
            ai_reply="请告诉我项目名称。",
        )
        assert "尚无" in prompt

    def test_build_project_info_reconcile_prompt_includes_user_and_ai_messages(self):
        builder = PromptBuilder()
        ctx = make_context()
        prompt = builder.build_project_info_reconcile_prompt(
            ctx,
            user_message="物流系统项目",
            ai_reply="明白，这是一个物流管理平台。",
        )
        assert "物流系统项目" in prompt
        assert "物流管理平台" in prompt


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

