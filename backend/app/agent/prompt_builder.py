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
</requirement_change>

确认技术栈偏好时（P4 阶段模型确认后）：
<tech_stack skipped="false|true">
  <tech category="frontend|backend|database|infrastructure|messaging|custom" name="技术名称" version="版本（可选）" proficiency="FAMILIAR|LEARNING|UNFAMILIAR">选择原因（可选）</tech>
</tech_stack>
如用户无偏好，使用 <tech_stack skipped="true"/> 即可。"""

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
目标：引导用户确定聚合边界和限界上下文划分，并在模型确认后询问技术栈偏好

任务：
1. 基于已识别的领域概念，讨论聚合边界
2. 使用提问模板判断聚合："{概念A}" 和 "{概念B}" 是否总是一起变化？
3. 讨论事务边界：哪些操作必须保持原子性？
4. 划分限界上下文：不同团队负责哪些业务？
5. 引导用户确认领域模型草稿
6. **模型确认后**，自然过渡询问技术栈偏好：
   - "模型已经很清晰了！在生成技术架构文档前，想了解一下你们团队的技术偏好，这样推荐的方案会更贴合实际情况。前端框架有偏好吗？"
   - 逐步询问：前端 → 后端 → 数据库 → 基础设施（可选）→ 消息队列（可选）
   - 如果用户说"不懂"、"你帮我选"或"跳过"，使用 <tech_stack skipped="true"/> 标记并告知 AI 将自动推荐
   - 确认完成后提议进入文档生成阶段
7. 用户也可以随时输入 /techstack 重新发起技术栈确认

输出领域模型草稿（文字描述 + 树形或列表结构）。
技术栈确认后，嵌入 <tech_stack> 标记。

【需求变更检测】（同 P3 阶段规则）""",

    Phase.DOC_GENERATE: """【当前阶段：文档生成 P5/6】
目标：引导用户选择要生成的 DDD 文档类型，并通过点击页面按钮触发生成

任务：
1. 告知用户当前已积累了足够的领域知识，可以生成 DDD 文档
2. 介绍可生成的文档类型及其用途：
   - BUSINESS_REQUIREMENT：业务需求文档
   - DOMAIN_MODEL：领域模型文档
   - UBIQUITOUS_LANGUAGE：通用语言术语表
   - USE_CASES：用例说明
   - TECH_ARCHITECTURE：技术架构建议
3. 引导用户点击页面下方的「生成文档」按钮选择要生成的文档
4. **请勿**在对话中直接输出文档全文，文档由系统后台生成
5. 文档生成后，提议进入审阅完善阶段

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

    def build(self, ctx: AgentContext, memory_summary_block: str = "") -> str:
        """Return the full system prompt string for this request.

        Args:
            ctx: Current ``AgentContext``.
            memory_summary_block: The ``[MEMORY_SUMMARY]…[/MEMORY_SUMMARY]``
                block produced by ``MemoryManager.get_summary_block(ctx)``.
                Pass an empty string (the default) if no summary is available
                yet (early turns) – the layer will simply be omitted.
        """
        layers = [
            _ROLE_DEFINITION,
            _PHASE_INSTRUCTIONS.get(ctx.current_phase, ""),
            memory_summary_block,          # Layer 3 – rolling summary (optional)
            self._build_context_block(ctx),  # Layer 4 – structured knowledge
            _XML_EXTRACTION_FORMAT,         # Layers 5+6
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

        ts = ctx.tech_stack_preferences
        if ts.confirmed or not ts.is_empty():
            lines.append(f"技术栈偏好: {ts.summary()}")

        lines.append("[/CONTEXT_BLOCK]")

        return "\n".join(lines)

    def build_tech_stack_block(self, ctx: AgentContext) -> str:
        """Return a [TECH_STACK_BLOCK] for TECH_ARCHITECTURE document generation.

        Returns an empty string when no preferences have been confirmed yet.
        """
        ts = ctx.tech_stack_preferences
        if not ts.confirmed and ts.is_empty():
            return ""

        lines = ["[TECH_STACK_BLOCK]"]
        if ts.skipped:
            lines.append(
                "用户技术栈偏好：未指定（用户请求 AI 根据领域模型自行推荐）"
            )
            lines.append(
                "约束：请在文档中为每项技术选型提供充分的理由，并说明其与领域模型的关联。"
            )
        else:
            lines.append("用户已确认的技术栈偏好（标注「用户指定」的项必须采用）：")
            _LABEL = {
                "frontend": "前端",
                "backend": "后端",
                "database": "数据库",
                "infrastructure": "基础设施",
                "messaging": "消息队列",
                "custom": "其他",
            }
            for category, label in _LABEL.items():
                choices = getattr(ts, category)
                if choices:
                    for c in choices:
                        ver = f" ({c.version})" if c.version else ""
                        source = "用户指定"
                        prof = (
                            f"，熟悉程度：{c.proficiency.value}"
                            if c.proficiency.value != "FAMILIAR"
                            else ""
                        )
                        reason = f"，说明：{c.reason}" if c.reason else ""
                        lines.append(
                            f"  • {label}：{c.name}{ver} [{source}{prof}{reason}]"
                        )
            lines.append(
                "约束：标注「用户指定」的技术项必须采用，不可替换。"
                "熟悉程度为 LEARNING 或 UNFAMILIAR 的技术需在文档中补充学习资源或替代方案。"
            )
        lines.append("[/TECH_STACK_BLOCK]")
        return "\n".join(lines)
