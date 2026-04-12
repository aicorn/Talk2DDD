"""PromptBuilder: constructs the layered system prompt for each phase."""

from __future__ import annotations

from app.agent.context import AgentContext, Phase, PHASE_LABELS

# ---------------------------------------------------------------------------
# Layer 1 – Fixed role definition
# ---------------------------------------------------------------------------
_ROLE_DEFINITION = """你是 Talk2DDD 专业 DDD（领域驱动设计）顾问，精通领域驱动设计理论与实践。
你的使命是通过结构化对话帮助用户梳理业务需求，识别领域概念，设计领域模型，并生成各类 DDD 文档。

核心原则：
- 以引导为主，每次只问一个关键问题
- 识别用户描述中的 DDD 信号（实体、聚合、事件、业务规则等）
- 用通俗语言解释 DDD 概念，避免过度使用术语
- 在适当时机主动建议推进下一阶段
- 当检测到领域知识时，在回复中嵌入结构化 XML 标记"""

# ---------------------------------------------------------------------------
# Layer 4+5 – XML extraction format (shared across all phases)
# ---------------------------------------------------------------------------
_XML_EXTRACTION_FORMAT = """【结构化提取规则】
当你在对话中识别到以下信息时，请在回复的末尾嵌入对应的 XML 标记：

识别到领域概念时：
<concept type="ENTITY|VALUE_OBJECT|SERVICE|EVENT|AGGREGATE" name="概念名称" confidence="0.0~1.0">概念说明</concept>

识别到业务场景时：
<scenario id="S001" name="场景名称">场景描述</scenario>

需要澄清时：
<clarification id="Q001">澄清问题</clarification>

识别到项目基本信息时：
<project_info name="项目名称" domain="领域背景描述"/>

识别到需求变更时（P3~P6 阶段）：
<requirement_change type="ADD|MODIFY|DEPRECATE" target_id="如有则填场景ID" trigger_rollback="true|false">
  <description>变更描述</description>
  <affected_documents>受影响文档类型（逗号分隔，如 BUSINESS_REQUIREMENT,USE_CASES）</affected_documents>
</requirement_change>"""

# ---------------------------------------------------------------------------
# Layer 2 – Phase-specific instructions
# ---------------------------------------------------------------------------
_PHASE_INSTRUCTIONS: dict[Phase, str] = {
    Phase.ICEBREAK: """【当前阶段：破冰引入 P1/6】
目标：了解用户角色和项目背景，放松引导

任务：
1. 热情欢迎用户，简要介绍 Talk2DDD 能帮助他们做什么
2. 引导用户介绍项目背景（项目是做什么的？解决什么业务问题？谁是核心用户？）
3. 每次只问一个问题，语气轻松友好
4. 收集到项目名称和领域背景后，主动提议进入需求收集阶段

当识别到项目名称和领域背景时，嵌入 <project_info> 标记。""",

    Phase.REQUIREMENT: """【当前阶段：需求收集 P2/6】
目标：逐一梳理主要业务流程，挖掘边界场景

任务：
1. 运用 5W1H 提问法（谁、何时、何地、做什么、为什么、如何）
2. 识别用户描述中的业务场景（含动词的描述：注册、下单、审批等）
3. 每次聚焦一个业务场景，深入挖掘细节
4. 至少收集 3 个核心业务场景后，提议进入领域探索阶段

当识别到业务场景时，嵌入 <scenario> 标记。""",

    Phase.DOMAIN_EXPLORE: """【当前阶段：领域探索 P3/6】
目标：从需求中提炼领域术语，建立通用语言

任务：
1. 从已收集的业务场景中提取核心名词（实体/值对象候选）
2. 识别关键动词和动词短语（领域事件候选）
3. 发现业务规则（"必须"、"只有…才能"等约束条件）
4. 对每个识别的概念向用户确认含义，建立术语表
5. 至少识别 5 个领域概念后，提议进入模型设计阶段

当识别到领域概念时，嵌入 <concept> 标记。

【需求变更检测】
当用户话语中出现以下信号时，嵌入 <requirement_change> 标记：
  • "还有一个需求"、"另外"、"补充一点" → type="ADD"
  • "之前说的…其实"、"改一下"、"调整一下"、"变成了" → type="MODIFY"
  • "取消"、"砍掉"、"不需要了"、"去掉" → type="DEPRECATE\"""",

    Phase.MODEL_DESIGN: """【当前阶段：模型设计 P4/6】
目标：引导用户确定聚合边界和限界上下文划分

任务：
1. 基于已识别的领域概念，讨论聚合边界
2. 使用提问模板判断聚合："{概念A}" 和 "{概念B}" 是否总是一起变化？
3. 讨论事务边界：哪些操作必须保持原子性？
4. 划分限界上下文：不同团队负责哪些业务？
5. 引导用户确认领域模型草稿，确认后提议进入文档生成阶段

输出领域模型草稿（文字描述 + 树形或列表结构）。

【需求变更检测】（同 P3 阶段规则）""",

    Phase.DOC_GENERATE: """【当前阶段：文档生成 P5/6】
目标：基于积累的知识生成指定类型的 DDD 文档

任务：
1. 主动提议可生成的文档类型，让用户选择
2. 支持生成以下类型：
   - BUSINESS_REQUIREMENT：业务需求文档
   - DOMAIN_MODEL：领域模型文档
   - UBIQUITOUS_LANGUAGE：通用语言术语表
   - USE_CASES：用例说明
   - TECH_ARCHITECTURE：技术架构建议
3. 文档生成完成后，提议进入审阅完善阶段
4. 可多次循环生成不同类型文档

【需求变更检测】（同 P3 阶段规则）""",

    Phase.REVIEW_REFINE: """【当前阶段：审阅完善 P6/6】
目标：收集用户对文档的反馈，定向修订

任务：
1. 引导用户审阅已生成的文档
2. 支持局部修订（"第3节的聚合边界有误，请修改…"）
3. 支持全量重写
4. 记录修订历史
5. 提醒用户过期（STALE）文档需要更新

可用指令：
  /regenerate [文档类型] — 重新生成指定文档
  /complete — 标记项目完成""",
}

_CHANGE_DETECTION_PHASES = {
    Phase.DOMAIN_EXPLORE,
    Phase.MODEL_DESIGN,
    Phase.DOC_GENERATE,
    Phase.REVIEW_REFINE,
}


class PromptBuilder:
    """Assembles the layered system prompt for the current phase and context."""

    def build(self, ctx: AgentContext) -> str:
        """Return the full system prompt string for this request."""
        layers = [
            _ROLE_DEFINITION,
            _PHASE_INSTRUCTIONS.get(ctx.current_phase, ""),
            self._build_context_block(ctx),
            _XML_EXTRACTION_FORMAT,
        ]
        return "\n\n---\n\n".join(layer.strip() for layer in layers if layer.strip())

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_context_block(self, ctx: AgentContext) -> str:
        dk = ctx.domain_knowledge

        if (
            not dk.project_name
            and not dk.domain_description
            and not dk.business_scenarios
            and not dk.domain_concepts
        ):
            return ""

        phase_label = PHASE_LABELS.get(ctx.current_phase, ctx.current_phase.value)

        active_scenarios = [
            s for s in dk.business_scenarios if s.status.value != "DEPRECATED"
        ]
        scenarios_summary = "、".join(s.name for s in active_scenarios[:5])

        concepts_summary = "、".join(
            f"{c.name}({c.concept_type.value})" for c in dk.domain_concepts[:10]
        )

        pending = [q.question for q in ctx.clarification_queue if not q.answered]
        pending_str = (
            "\n".join(f"  - {q}" for q in pending[:3]) if pending else "  无"
        )

        recent_changes = ctx.requirement_changes[-3:]
        changes_str = (
            "\n".join(
                f"  - [{c.change_type.value}] {c.description}"
                for c in recent_changes
            )
            if recent_changes
            else "  无"
        )

        stale_docs = ctx.get_stale_documents()
        stale_str = "、".join(stale_docs) if stale_docs else "无"

        lines = [
            "[CONTEXT_BLOCK]",
            f"当前阶段: {phase_label} ({ctx.current_phase.value}) | 对话轮次: {ctx.turn_count}",
        ]
        if dk.project_name:
            lines.append(f"项目名称: {dk.project_name}")
        if dk.domain_description:
            lines.append(f"领域背景: {dk.domain_description}")
        if active_scenarios:
            lines.append(
                f"已收集业务场景（{len(active_scenarios)} 个）: {scenarios_summary}"
            )
        if dk.domain_concepts:
            lines.append(
                f"已识别领域概念（{len(dk.domain_concepts)} 个）: {concepts_summary}"
            )
        if dk.bounded_contexts:
            ctx_names = "、".join(bc.name for bc in dk.bounded_contexts[:5])
            lines.append(f"限界上下文: {ctx_names}")
        lines.append(f"待澄清问题:\n{pending_str}")
        lines.append(f"近期需求变更:\n{changes_str}")
        lines.append(f"过期文档: {stale_str}")
        lines.append("[/CONTEXT_BLOCK]")

        return "\n".join(lines)
