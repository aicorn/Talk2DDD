"""PromptBuilder: constructs the layered system prompt for each phase."""

from __future__ import annotations

from typing import List

from app.agent.context import AgentContext, Phase, PHASE_LABELS, UserIntent

# ---------------------------------------------------------------------------
# Layer 1 – Fixed role definition
# ---------------------------------------------------------------------------
_ROLE_DEFINITION = """你是 Talk2DDD 专业 DDD（领域驱动设计）顾问，精通领域驱动设计理论与实践。
你的使命是通过结构化对话帮助用户梳理业务需求，识别领域概念，设计领域模型，并生成各类 DDD 文档。

核心原则：
- 以引导为主，每次只问一个关键问题
- 识别用户描述中的 DDD 信号（实体、聚合、事件、业务规则等）
- 用通俗语言解释 DDD 概念，避免过度使用术语
- 当阶段条件满足时，提示用户点击顶部导航栏的「下一阶段 →」按钮手动进入下一阶段（不要在对话中自动切换阶段）
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

问题已在对话中得到明确答案时，标记为已解决：
<clarification id="Q001" answered="true"/>

识别到项目基本信息时：
<project_info name="项目名称" domain="领域背景描述"/>

识别到需求变更时（P3~P5 阶段）：
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
    Phase.ICEBREAK: """【当前阶段：破冰引入 P1/5】
目标：收集「项目简介」文档所需的两项信息——项目名称和领域背景简述

本阶段文档仅包含两个字段：
  • 项目名称：项目的正式名称或简称
  • 领域背景：用 1~3 句话说明项目所处领域及其核心定位

任务：
1. 热情欢迎用户，用一句话介绍 Talk2DDD 能帮助他们完成 DDD 建模
2. 先问项目名称，再问领域背景（一句话即可）；每次只问一个问题
3. 收集到以上两项信息后，立即告知用户「项目简介」已生成，提示点击顶部导航栏右侧的「下一阶段 →」按钮进入需求收集阶段（不要自动切换阶段）

【严格限制】本阶段只收集项目名称和领域背景，不要询问业务场景、用户角色、核心功能、业务流程等内容，这些属于下一阶段（需求收集 P2）的工作。

当识别到项目名称和领域背景时，嵌入 <project_info> 标记。""",

    Phase.REQUIREMENT: """【当前阶段：需求收集 P2/5】
目标：逐一梳理主要业务流程，挖掘边界场景

任务：
1. 运用 5W1H 提问法（谁、何时、何地、做什么、为什么、如何）
2. 识别用户描述中的业务场景（含动词的描述：注册、下单、审批等）
3. 每次聚焦一个业务场景，深入挖掘细节
4. 至少收集 3 个核心业务场景后，告知用户条件已满足，提示点击「下一阶段 →」按钮进入领域探索阶段（不要自动切换阶段）

【重要】嵌入规则：
- 每当在对话中提到或讨论任何业务场景时，**必须**在回复末尾嵌入对应的 <scenario> 标记，不可遗漏。
- 若同一回复中涉及多个场景，每个场景各嵌入一个 <scenario> 标记。
- 若用户对已有场景进行补充说明，使用该场景已有的 id，用更新后的描述重新嵌入标记。
- 若当前轮次未涉及任何业务场景，则不需要嵌入任何 <scenario> 标记。""",

    Phase.DOMAIN_EXPLORE: """【当前阶段：领域探索 P3/5】
目标：从需求中提炼领域术语，建立通用语言

任务：
1. 从已收集的业务场景中提取核心名词（实体/值对象候选）
2. 识别关键动词和动词短语（领域事件候选）
3. 发现业务规则（"必须"、"只有…才能"等约束条件）
4. 对每个识别的概念向用户确认含义，建立术语表
5. 至少识别 5 个领域概念后，告知用户条件已满足，提示点击「下一阶段 →」按钮进入模型设计阶段（不要自动切换阶段）

当识别到领域概念时，嵌入 <concept> 标记。

【需求变更检测】
当用户话语中出现以下信号时，嵌入 <requirement_change> 标记：
  • "还有一个需求"、"另外"、"补充一点" → type="ADD"
  • "之前说的…其实"、"改一下"、"调整一下"、"变成了" → type="MODIFY"
  • "取消"、"砍掉"、"不需要了"、"去掉" → type="DEPRECATE\"""",

    Phase.MODEL_DESIGN: """【当前阶段：模型设计 P4/5】
目标：引导用户确定聚合边界和限界上下文划分，并在模型确认后询问技术栈偏好

任务：
1. 基于已识别的领域概念，讨论聚合边界
2. 使用提问模板判断聚合："{概念A}" 和 "{概念B}" 是否总是一起变化？
3. 讨论事务边界：哪些操作必须保持原子性？
4. 划分限界上下文：不同团队负责哪些业务？
5. 引导用户确认领域模型草稿
6. **模型确认后**，自然过渡询问技术栈偏好：
   - "模型已经很清晰了！在进入审阅阶段前，想了解一下你们团队的技术偏好，这样模型草稿中的技术架构建议会更贴合实际情况。前端框架有偏好吗？"
   - 逐步询问：前端 → 后端 → 数据库 → 基础设施（可选）→ 消息队列（可选）
   - 如果用户说"不懂"、"你帮我选"或"跳过"，使用 <tech_stack skipped="true"/> 标记并告知 AI 将自动推荐
   - 确认完成后，告知用户可以点击「下一阶段 →」按钮进入审阅完善阶段（不要自动切换阶段）
7. 用户也可以随时输入 /techstack 重新发起技术栈确认

输出领域模型草稿（文字描述 + 树形或列表结构）。
技术栈确认后，嵌入 <tech_stack> 标记。

【需求变更检测】（同 P3 阶段规则）""",

    Phase.REVIEW_REFINE: """【当前阶段：审阅完善 P5/5】
目标：收集用户对各阶段文档的反馈，定向修订

任务：
1. 引导用户在「我的项目」中审阅已自动保存的各阶段文档
2. 支持局部修订（"领域模型草稿中的聚合边界有误，请修改…"）
3. 支持针对某个阶段的内容进行二次润色
4. 记录修订历史
5. 告知用户修改后相应阶段文档会自动重新保存到「我的项目」

可用指令：
  /techstack — 重新设置技术栈偏好
  /complete — 标记项目完成

【需求变更检测】（同 P3 阶段规则）""",
}

_CHANGE_DETECTION_PHASES = {
    Phase.DOMAIN_EXPLORE,
    Phase.MODEL_DESIGN,
    Phase.REVIEW_REFINE,
}

# ---------------------------------------------------------------------------
# Phase-switch instruction block – appended when phase_switch_trigger=True
# ---------------------------------------------------------------------------
_PHASE_SWITCH_INSTRUCTION = """【阶段切换模式】
本轮对话由用户手动切换阶段触发，而非普通对话输入。
请生成一段简短友好的「阶段引导消息」（100~200 字），内容包括：
1. 确认已进入的新阶段名称和总阶段序号（如「欢迎进入第 3 阶段：领域探索」）
2. 用一句话说明本阶段的核心目标
3. 简要总结上一阶段已完成的关键成果（如"已收集 4 个业务场景"）
4. 提出 1~2 个本阶段的首要行动项或引导问题
语气积极、简洁，避免重复已知信息，不要在回复中输出任何 XML 标记。"""

# Phase-specific override for DOMAIN_EXPLORE entry
_PHASE_SWITCH_INSTRUCTION_DOMAIN_EXPLORE = """【阶段切换模式 - 领域探索开场】
本轮对话由用户手动切换到「领域探索」阶段触发。系统已根据上一阶段的业务场景自动提炼了初版领域概念词汇表，并作为参考内容附在用户消息中。
请生成一段结构化的「领域探索开场消息」，内容包括：
1. 一句话欢迎进入第 3 阶段「领域探索」，说明本阶段目标（从业务场景中提炼领域术语，建立通用语言）
2. 告知用户：已根据已收集的业务场景自动提炼了初版领域概念词汇表
3. 完整展示用户消息中提供的初版领域概念词汇表（保持 Markdown 表格格式，如表格为空则说明尚未识别到概念）
4. 邀请用户提出修改意见：哪些概念需要调整？是否有遗漏的业务对象或业务规则？
5. 提出 1 个具体的引导问题，帮助用户进一步确认或补充领域概念
不要在回复中输出任何 XML 标记。"""


class PromptBuilder:
    """Assembles the layered system prompt for the current phase and context."""

    def build(self, ctx: AgentContext, memory_summary_block: str = "", phase_switch_trigger: bool = False) -> str:
        """Return the full system prompt string for this request.

        Args:
            ctx: Current ``AgentContext``.
            memory_summary_block: The ``[MEMORY_SUMMARY]…[/MEMORY_SUMMARY]``
                block produced by ``MemoryManager.get_summary_block(ctx)``.
                Pass an empty string (the default) if no summary is available
                yet (early turns) – the layer will simply be omitted.
            phase_switch_trigger: When ``True``, append a ``[PHASE_SWITCH]``
                instruction block that directs the AI to generate a structured
                phase-intro message instead of continuing the previous topic.
        """
        layers = [
            _ROLE_DEFINITION,
            _PHASE_INSTRUCTIONS.get(ctx.current_phase, ""),
            memory_summary_block,          # Layer 3 – rolling summary (optional)
            self._build_context_block(ctx),  # Layer 4 – structured knowledge
            _XML_EXTRACTION_FORMAT,         # Layers 5+6
        ]
        if phase_switch_trigger:
            switch_instruction = (
                _PHASE_SWITCH_INSTRUCTION_DOMAIN_EXPLORE
                if ctx.current_phase == Phase.DOMAIN_EXPLORE
                else _PHASE_SWITCH_INSTRUCTION
            )
            layers.append(switch_instruction)
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

        pending_qs = [q for q in ctx.clarification_queue if not q.answered]
        pending_str = (
            "\n".join(f"  - [{q.id}] {q.question}" for q in pending_qs[:3])
            if pending_qs
            else "  无"
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

    def build_initial_domain_concept_extraction_prompt(self, ctx: AgentContext) -> str:
        """Build a prompt for extracting initial domain concepts from business scenarios.

        Called once when the session first enters DOMAIN_EXPLORE so that a
        seed set of concepts is available for the opening phase document.
        Returns an empty string when there are no active scenarios to work from.
        """
        active = [
            s for s in ctx.domain_knowledge.business_scenarios
            if s.status.value != "DEPRECATED"
        ]
        if not active:
            return ""

        scenarios_text = "\n".join(
            f"- {s.id}: {s.name}：{s.description}" for s in active
        )
        return (
            "你是领域概念提取助手，负责从业务场景中识别并结构化领域概念。\n\n"
            "请从以下业务场景中提取所有核心领域概念（实体、值对象、领域事件、聚合等），"
            "以 JSON 数组格式返回。每个元素包含：\n"
            '  - "name"：概念名称（简洁名词或名词短语）\n'
            '  - "type"：ENTITY/VALUE_OBJECT/SERVICE/EVENT/AGGREGATE/REPOSITORY/DOMAIN_SERVICE 之一\n'
            '  - "description"：1~2 句描述\n'
            '  - "confidence"：置信度 0.0~1.0\n\n'
            "重点：核心业务对象（名词）为 ENTITY；描述不变属性的概念为 VALUE_OBJECT；"
            "表示已发生事情的动词短语（如『下单』→ OrderPlaced）为 EVENT；多个对象的一致性边界为 AGGREGATE。\n"
            "只返回 JSON 数组，不要任何其他文字或 Markdown 标记。\n\n"
            "---\n"
            f"业务场景列表：\n{scenarios_text}"
        )

    def build_domain_concept_reconcile_prompt(
        self,
        ctx: AgentContext,
        user_message: str,
        ai_reply: str,
    ) -> str:
        """Build a focused extraction prompt for the dedicated concept reconciler.

        Sent as a second lightweight AI call after each Phase 3 turn whose sole
        job is to identify ALL domain concepts mentioned in the exchange and
        return them as JSON.  The result is merged into
        ``ctx.domain_knowledge.domain_concepts``.

        Returns a single user-role message string.
        """
        existing = ctx.domain_knowledge.domain_concepts
        if existing:
            existing_lines = "\n".join(
                f'  {{"name": "{c.name}", "type": "{c.concept_type.value}", '
                f'"description": "{c.description}"}}'
                for c in existing
            )
            existing_block = (
                f"已有领域概念（仅供参考，系统会自动去重）：\n[\n{existing_lines}\n]"
            )
        else:
            existing_block = "已有领域概念：[]（尚无）"

        return (
            "你是领域概念提取助手，负责从对话片段中识别并结构化领域概念。\n\n"
            f"{existing_block}\n\n"
            "请从下面这轮对话中提取**所有**提到、讨论过或确认过的领域概念，"
            "以 JSON 数组格式返回。每个元素包含：\n"
            '  - "name"：概念名称\n'
            '  - "type"：ENTITY/VALUE_OBJECT/SERVICE/EVENT/AGGREGATE/REPOSITORY/DOMAIN_SERVICE\n'
            '  - "description"：1~2 句描述\n'
            '  - "confidence"：置信度 0.0~1.0\n\n'
            "**重要**：如果 AI 回复中包含 `<concept>` XML 标签，请务必将其中的概念也包含在"
            "返回结果中——XML 解析可能因格式问题失败，本提取器是兜底保障。\n"
            "系统会自动对已有概念去重，无需担心重复。\n"
            "如果本轮对话未涉及任何领域概念，返回空数组 []。\n"
            "只返回 JSON 数组，不要任何其他文字或 Markdown 标记。\n\n"
            "---\n"
            f"用户说：\n{user_message}\n\n"
            f"AI 回复：\n{ai_reply}"
        )

    def build_project_info_reconcile_prompt(
        self,
        ctx: AgentContext,
        user_message: str,
        ai_reply: str,
    ) -> str:
        """Build a focused extraction prompt for the dedicated Phase 1 reconciler.

        Sent as a second lightweight AI call after each ICEBREAK turn whose sole
        job is to identify the project name and domain background mentioned in
        the exchange and return them as a JSON object.  The result is merged
        into ``ctx.domain_knowledge`` so that the P1 phase document stays in
        sync with what was discussed even when the conversational AI omitted
        ``<project_info>`` tags.

        Returns a single user-role message string.
        """
        dk = ctx.domain_knowledge
        if dk.project_name or dk.domain_description:
            current_block = (
                "当前已提取信息：\n"
                f'  project_name: "{dk.project_name or "（未填写）"}"\n'
                f'  domain_description: "{dk.domain_description or "（未填写）"}"\n\n'
                "只补充尚未填写的字段；已有值请保持不变，对应字段返回空字符串。"
            )
        else:
            current_block = "当前已提取信息：（尚无）"

        return (
            "你是项目信息提取助手，负责从对话片段中识别项目名称和领域背景。\n\n"
            f"{current_block}\n\n"
            "请从下面这轮对话中提取项目名称和领域背景，以 JSON 对象格式返回：\n"
            '  {"project_name": "项目名称", "domain_description": "领域背景描述"}\n\n'
            "如果本轮对话未提及相关信息，或该字段已有值，对应字段返回空字符串。\n"
            "只返回 JSON 对象，不要任何其他文字或 Markdown 标记。\n\n"
            "---\n"
            f"用户说：\n{user_message}\n\n"
            f"AI 回复：\n{ai_reply}"
        )

    def build_scenario_extraction_prompt(
        self,
        ctx: AgentContext,
        user_message: str,
        ai_reply: str,
    ) -> str:
        """Build a focused extraction prompt for the dedicated scenario extractor.

        This prompt is sent as a second, lightweight AI call whose sole
        responsibility is to identify ALL business scenarios mentioned in the
        current exchange and return them as a JSON array.  The result is then
        merged into ``ctx.domain_knowledge.business_scenarios`` so that the
        phase document stays in sync with the conversational content.

        Returns a single user-role message string.
        """
        existing = ctx.domain_knowledge.business_scenarios
        if existing:
            existing_lines = "\n".join(
                f'  {{"id": "{s.id}", "name": "{s.name}", "description": "{s.description}"}}'
                for s in existing
            )
            existing_block = f"已有业务场景（仅供参考，系统会自动去重）：\n[\n{existing_lines}\n]"
        else:
            existing_block = "已有业务场景：[]（尚无）"

        return (
            "你是业务场景提取助手，负责从对话片段中识别并结构化业务场景。\n\n"
            f"{existing_block}\n\n"
            "请从下面这轮对话中提取**所有**提到、讨论过或确认过的业务场景，"
            "以 JSON 数组格式返回。每个元素包含：\n"
            '  - "id"：场景编号（已有场景保持原 id；新场景使用 S001、S002 等格式，'
            "若与已有 id 冲突则系统会自动重新分配，无需担心）\n"
            '  - "name"：简洁动宾短语（如"用户注册"、"订单审批"）\n'
            '  - "description"：1~2 句描述\n\n'
            "**重要**：如果 AI 回复中包含 `<scenario>` XML 标签，请务必将其中的场景也包含在"
            "返回结果中——XML 解析可能因格式问题失败，本提取器是兜底保障。\n"
            "系统会自动对已有场景去重，无需担心重复。\n"
            "如果本轮对话未涉及任何业务场景，返回空数组 []。\n"
            "只返回 JSON 数组，不要任何其他文字或 Markdown 标记。\n\n"
            "---\n"
            f"用户说：\n{user_message}\n\n"
            f"AI 回复：\n{ai_reply}"
        )

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
                "约束：标注「用户指定」的技术项必须采用，不可替换。 "
                "熟悉程度为 LEARNING 或 UNFAMILIAR 的技术需在文档中补充学习资源或替代方案。"
            )
        lines.append("[/TECH_STACK_BLOCK]")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # §21 Phase-opening structured suggestion helpers
    # ------------------------------------------------------------------

    def build_intent_classification_prompt(
        self,
        ctx: AgentContext,
        user_message: str,
    ) -> str:
        """Build a lightweight prompt for the ``UserIntentClassifier``.

        The classifier is a separate, stateless AI call that reads only the
        current user message and the active ``PhaseSuggestion`` content.  It
        returns a JSON ``IntentClassification`` object.

        Returns a single user-role message string (no history needed).
        """
        suggestion = ctx.phase_suggestion
        if suggestion is None:
            suggestion_text = "（当前阶段无开场建议）"
        else:
            # Render a compact text representation of pending items
            lines = [f"当前阶段开场建议（phase={suggestion.phase.value}，状态={suggestion.status.value}）："]
            for sr in suggestion.scenario_refinements:
                lines.append(f"\n场景：{sr.scenario_id} {sr.scenario_name}")
                for item in sr.items:
                    if item.selected is None and not item.dismissed:
                        state = "⏳"
                    elif item.selected:
                        state = "✅"
                    else:
                        state = "❌"
                    lines.append(
                        f"  [{item.index}] {state} {item.question} | 备选：{' / '.join(item.options)}"
                        + (f" | 已选：{item.selected}" if item.selected else "")
                    )
            suggestion_text = "\n".join(lines) if len(lines) > 1 else "（建议模板为空）"

        return (
            "你是意图分类助手，负责将用户消息分类为以下意图之一：\n\n"
            "  MAKE_SELECTION     — 用户选择了某个备选方案\n"
            "  REQUEST_MORE       — 用户要求更多建议或问题\n"
            "  REQUEST_REFINE     — 用户要求对某条问题进一步细化\n"
            "  REJECT_SUGGESTION  — 用户拒绝/跳过某条建议\n"
            "  PROVIDE_FEEDBACK   — 用户提供了开放性反馈（与建议相关但不符合上述类型）\n"
            "  OUT_OF_SCOPE       — 用户请求与当前建议内容完全无关\n\n"
            "返回 JSON 对象，字段说明：\n"
            '  "intent"           : 以上意图之一（必填）\n'
            '  "target_index"     : 涉及哪个序号的建议条目（整数，无则 null）\n'
            '  "selected_option"  : MAKE_SELECTION 时提取的选择文字（无则 null）\n'
            '  "raw_feedback"     : PROVIDE_FEEDBACK 时的原文摘要（无则 null）\n'
            '  "out_of_scope_hint": OUT_OF_SCOPE 时对用户意图的简短描述（无则 null）\n\n'
            "只返回 JSON 对象，不要任何其他文字或 Markdown 标记。\n\n"
            "---\n"
            f"{suggestion_text}\n\n"
            "---\n"
            f"用户消息：\n{user_message}"
        )

    def build_phase_opening_suggestion_prompt(self, ctx: AgentContext) -> str:
        """Build a prompt that generates the phase-opening structured suggestion JSON.

        Called once at the start of each phase (P2–P5) by
        ``AgentCore._generate_phase_opening_suggestion()``.  The AI returns
        a JSON object matching the ``PhaseSuggestion`` schema for the target
        phase.

        Returns an empty string when the phase does not use this mechanism
        (e.g. ``ICEBREAK``).
        """
        phase = ctx.current_phase
        dk = ctx.domain_knowledge

        if phase == Phase.REQUIREMENT:
            # P2: generate per-scenario refinement questions
            active = [s for s in dk.business_scenarios if s.status.value != "DEPRECATED"]
            if not active:
                return ""
            scenarios_text = "\n".join(
                f"- {s.id}（{s.name}）：{s.description}" for s in active
            )
            return (
                "你是 DDD 需求细化助手。请根据以下业务场景，为每个场景生成 3~5 个待细化问题，"
                "每个问题提供 2~4 个备选方案供用户选择。\n\n"
                "返回 JSON 数组，格式如下（scenario_refinements 字段）：\n"
                '{\n  "scenario_refinements": [\n'
                '    {\n      "scenario_id": "S001",\n      "scenario_name": "场景名称",\n'
                '      "items": [\n'
                '        {"index": 1, "question": "细化问题", "options": ["方案A", "方案B"]},\n'
                '        ...\n      ]\n    },\n    ...\n  ]\n}\n\n'
                "注意：\n"
                '- question 应为具体的业务决策问题（如"定时发布是否需要支持设置日期和时间？"）\n'
                '- options 应为 2~4 个具体的备选答案（如 ["是", "否"] 或 ["30秒", "1分钟", "手动保存"]）\n'
                "- index 从 1 开始，跨场景连续编号（S001 第1~4条，S002 第5~8条，依此类推）\n"
                "- 只返回 JSON 对象，不要任何其他文字或 Markdown 标记。\n\n"
                "---\n"
                f"业务场景列表：\n{scenarios_text}"
            )

        if phase == Phase.DOMAIN_EXPLORE:
            # P3: suggest bounded-context groupings
            concepts = dk.domain_concepts
            if not concepts:
                return ""
            concepts_text = "\n".join(
                f"- {c.name}（{c.concept_type.value}）：{c.description}" for c in concepts
            )
            return (
                "你是 DDD 限界上下文划分助手。请根据以下领域概念，建议合理的限界上下文分组方案。\n\n"
                "返回 JSON 对象，格式如下（context_groupings 字段）：\n"
                '{\n  "context_groupings": [\n'
                '    {\n      "index": 1,\n      "context_name": "内容管理上下文",\n'
                '      "concepts": ["文章", "草稿", "分类"],\n'
                '      "rationale": "均属于内容生命周期管理",\n'
                '      "alternatives": ["合并到用户上下文", "拆分为 ArticleContext + MediaContext"]\n'
                '    },\n    ...\n  ]\n}\n\n'
                "- index 从 1 开始连续编号\n"
                "- alternatives 提供 1~3 个备选分组方案\n"
                "- 只返回 JSON 对象，不要任何其他文字或 Markdown 标记。\n\n"
                "---\n"
                f"领域概念列表：\n{concepts_text}"
            )

        if phase == Phase.MODEL_DESIGN:
            # P4: suggest aggregate/entity/value-object design per context
            bounded = dk.bounded_contexts
            concepts = dk.domain_concepts
            if not concepts:
                return ""
            concepts_text = "\n".join(
                f"- {c.name}（{c.concept_type.value}）：{c.description}" for c in concepts
            )
            contexts_text = (
                "\n".join(f"- {bc.name}：包含概念 {', '.join(bc.concepts[:5])}" for bc in bounded)
                if bounded
                else "（尚未划分限界上下文）"
            )
            return (
                "你是 DDD 模型设计助手。请根据以下领域概念和限界上下文，"
                "为每个上下文建议聚合根/实体/值对象划分方案。\n\n"
                "返回 JSON 对象，格式如下（model_designs 字段）：\n"
                '{\n  "model_designs": [\n'
                '    {\n      "index": 1,\n      "context_name": "内容管理上下文",\n'
                '      "aggregate_root": "Article",\n'
                '      "entities": ["Draft", "Category"],\n'
                '      "value_objects": ["Slug", "PublishTime"],\n'
                '      "rationale": "Article 是内容生命周期的核心聚合",\n'
                '      "alternatives": ["将 Draft 设为 Article 的值对象", "将 Category 提升为独立聚合根"]\n'
                '    },\n    ...\n  ]\n}\n\n'
                "- 只返回 JSON 对象，不要任何其他文字或 Markdown 标记。\n\n"
                "---\n"
                f"限界上下文：\n{contexts_text}\n\n"
                f"领域概念：\n{concepts_text}"
            )

        if phase == Phase.REVIEW_REFINE:
            # P5: review the current domain model and suggest revision points
            concepts = dk.domain_concepts
            bounded = dk.bounded_contexts
            if not concepts:
                return ""
            summary = f"领域概念（{len(concepts)} 个）：" + "、".join(c.name for c in concepts[:10])
            contexts_summary = (
                "限界上下文：" + "、".join(bc.name for bc in bounded[:5])
                if bounded else "（尚未划分限界上下文）"
            )
            return (
                "你是 DDD 模型审阅助手。请对以下领域模型做一致性检查，"
                "列出潜在问题和建议的修订点。\n\n"
                "返回 JSON 对象，格式如下（review_items 字段）：\n"
                '{\n  "review_items": [\n'
                '    {\n      "index": 1,\n      "severity": "高|中|低",\n'
                '      "issue_type": "一致性问题|边界问题|命名问题|遗漏项",\n'
                '      "description": "问题描述",\n'
                '      "suggestion": "修订建议",\n'
                '      "options": ["接受建议", "标记为无需处理", "自定义修订"]\n'
                '    },\n    ...\n  ]\n}\n\n'
                "- 按 severity 降序排列（高→中→低）\n"
                "- 只返回 JSON 对象，不要任何其他文字或 Markdown 标记。\n\n"
                "---\n"
                f"{summary}\n{contexts_summary}"
            )

        return ""  # ICEBREAK and unknown phases: no suggestion

    def build_structured_reply_instruction(
        self,
        ctx: AgentContext,
        applied_changes: List[str],
        pending_items_text: str,
    ) -> str:
        """Build the three-part structured reply format instruction.

        Injected into the main conversational AI's system prompt when
        ``PhaseDocumentEditor`` executed at least one write this turn.

        ``applied_changes`` is a list of human-readable change descriptions
        (one per write operation performed this turn).
        ``pending_items_text`` is a pre-rendered Markdown block of the items
        still awaiting user confirmation; pass an empty string if none remain.

        Degrades gracefully:
        - No applied_changes → omit 【已确定内容】 block.
        - No pending_items_text → omit 【待确认内容】 block.
        - Both empty → the instruction is not injected at all (caller guards
          against calling this with both empty).
        """
        sections: List[str] = []

        if applied_changes:
            confirmed_lines = "\n".join(f"• ✅ {c}" for c in applied_changes)
            sections.append(
                "【已确定内容】\n"
                "以下条目已在本轮写入文档：\n"
                f"{confirmed_lines}"
            )

        if pending_items_text:
            sections.append(
                "【待确认内容】\n"
                "以下建议条目仍待用户选择或说明：\n"
                f"{pending_items_text}"
            )

        if not sections:
            return ""

        sections.append(
            "【其他回答与引导】\n"
            "回答用户的其他问题（如有），并说明当前阶段进度，引导用户继续。"
        )

        body = "\n\n─────────────────────────────────────────\n\n".join(sections)
        return (
            "[STRUCTURED_REPLY_FORMAT]\n"
            "请按以下三段式结构输出本轮回复：\n\n"
            "─────────────────────────────────────────\n\n"
            + body
            + "\n\n─────────────────────────────────────────\n"
            "[/STRUCTURED_REPLY_FORMAT]"
        )
