"""PhaseDocumentRenderer: deterministic Markdown renderer for each phase."""

from __future__ import annotations

from datetime import datetime, timezone

from app.agent.context import AgentContext, DocumentStatus, Phase, PHASE_LABELS


class PhaseDocumentRenderer:
    """Renders the current AgentContext as a phase-specific Markdown document.

    This renderer is purely deterministic — it does **not** call any AI.
    It runs after every turn and its output is stored as a PhaseDocument.
    """

    def render(self, ctx: AgentContext) -> str:
        """Return a Markdown string for the current phase document."""
        phase = ctx.current_phase
        if phase == Phase.ICEBREAK:
            return self._render_icebreak(ctx)
        if phase == Phase.REQUIREMENT:
            return self._render_requirement(ctx)
        if phase == Phase.DOMAIN_EXPLORE:
            return self._render_domain_explore(ctx)
        if phase == Phase.MODEL_DESIGN:
            return self._render_model_design(ctx)
        if phase == Phase.DOC_GENERATE:
            return self._render_doc_generate(ctx)
        if phase == Phase.REVIEW_REFINE:
            return self._render_review_refine(ctx)
        return f"# {PHASE_LABELS.get(phase, phase.value)}\n\n（暂无内容）"

    def get_title(self, ctx: AgentContext) -> str:
        """Return the document title for the current phase."""
        _TITLES = {
            Phase.ICEBREAK: "项目简介",
            Phase.REQUIREMENT: "业务需求草稿",
            Phase.DOMAIN_EXPLORE: "领域概念词汇表",
            Phase.MODEL_DESIGN: "领域模型草稿",
            Phase.DOC_GENERATE: "已生成文档列表",
            Phase.REVIEW_REFINE: "修订记录",
        }
        return _TITLES.get(ctx.current_phase, PHASE_LABELS.get(ctx.current_phase, ""))

    # ------------------------------------------------------------------
    # Phase-specific renderers
    # ------------------------------------------------------------------

    def _render_icebreak(self, ctx: AgentContext) -> str:
        dk = ctx.domain_knowledge
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
        lines = [f"# 项目简介\n\n> 更新时间：{now}  |  对话轮次：{ctx.turn_count}\n"]
        lines.append(
            f"**项目名称：** {dk.project_name or '（待填写）'}\n"
        )
        lines.append(
            f"**领域背景：** {dk.domain_description or '（待收集）'}\n"
        )
        return "\n".join(lines)

    def _render_requirement(self, ctx: AgentContext) -> str:
        dk = ctx.domain_knowledge
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
        active = [s for s in dk.business_scenarios if s.status.value != "DEPRECATED"]
        lines = [
            f"# 业务需求草稿\n",
            f"> 更新时间：{now}  |  对话轮次：{ctx.turn_count}  |  "
            f"已收集场景：{len(active)} / 3（最低要求）\n",
        ]
        if active:
            lines.append("## 业务场景\n")
            lines.append("| # | 场景名称 | 描述 | 状态 | 版本 |")
            lines.append("|---|----------|------|------|------|")
            for s in active:
                lines.append(
                    f"| {s.id} | {s.name} | {s.description or '—'} "
                    f"| {s.status.value} | v{s.version} |"
                )
            lines.append("")
        else:
            lines.append("_暂未收集到业务场景，请继续对话。_\n")

        pending = [q for q in ctx.clarification_queue if not q.answered]
        if pending:
            lines.append("## 待澄清问题\n")
            for q in pending:
                lines.append(f"- [ ] {q.id}: {q.question}")
            lines.append("")

        return "\n".join(lines)

    def _render_domain_explore(self, ctx: AgentContext) -> str:
        dk = ctx.domain_knowledge
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
        lines = [
            f"# 领域概念词汇表\n",
            f"> 更新时间：{now}  |  对话轮次：{ctx.turn_count}  |  "
            f"已识别概念：{len(dk.domain_concepts)} / 5（最低要求）\n",
        ]
        if dk.domain_concepts:
            lines.append("| 概念名称 | 类型 | 描述 | 置信度 |")
            lines.append("|----------|------|------|--------|")
            for c in dk.domain_concepts:
                confidence_bar = "★" * round(c.confidence * 5)
                lines.append(
                    f"| **{c.name}** | {c.concept_type.value} "
                    f"| {c.description or '—'} | {confidence_bar} |"
                )
            lines.append("")
        else:
            lines.append("_暂未识别到领域概念，请继续对话。_\n")

        return "\n".join(lines)

    def _render_model_design(self, ctx: AgentContext) -> str:
        dk = ctx.domain_knowledge
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
        lines = [
            f"# 领域模型草稿\n",
            f"> 更新时间：{now}  |  对话轮次：{ctx.turn_count}\n",
        ]
        if dk.bounded_contexts:
            lines.append("## 限界上下文\n")
            for bc in dk.bounded_contexts:
                lines.append(f"### {bc.name}\n")
                lines.append(f"{bc.description}\n")
                if bc.concepts:
                    lines.append("**包含概念：** " + "、".join(bc.concepts) + "\n")
        else:
            lines.append("_限界上下文尚未确定，请继续讨论。_\n")

        if dk.domain_concepts:
            lines.append("## 领域概念汇总\n")
            # Group by type
            from collections import defaultdict

            by_type: dict = defaultdict(list)
            for c in dk.domain_concepts:
                by_type[c.concept_type.value].append(c)
            for type_name, concepts in sorted(by_type.items()):
                lines.append(f"### {type_name}\n")
                for c in concepts:
                    lines.append(f"- **{c.name}**：{c.description or '（待描述）'}")
                lines.append("")

        if dk.relationships:
            lines.append("## 概念关系\n")
            for r in dk.relationships:
                lines.append(
                    f"- `{r.source}` —[{r.relation_type}]→ `{r.target}`"
                    + (f"：{r.description}" if r.description else "")
                )
            lines.append("")

        ts = ctx.tech_stack_preferences
        if ts.confirmed or not ts.is_empty():
            lines.append("## 技术栈偏好\n")
            if ts.skipped:
                lines.append("_用户跳过技术栈选择，由 AI 根据领域模型自动推荐。_\n")
            else:
                _LABEL = {
                    "frontend": "前端",
                    "backend": "后端",
                    "database": "数据库",
                    "infrastructure": "基础设施",
                    "messaging": "消息队列",
                    "custom": "其他",
                }
                has_any = False
                for category, label in _LABEL.items():
                    choices = getattr(ts, category)
                    if choices:
                        has_any = True
                        names = "、".join(
                            c.name + (f" ({c.version})" if c.version else "")
                            for c in choices
                        )
                        lines.append(f"- **{label}**：{names}")
                if not has_any:
                    lines.append("_技术栈信息采集中…_")
                lines.append("")
        elif ctx.current_phase.value == "MODEL_DESIGN":
            lines.append("## 技术栈偏好\n")
            lines.append(
                "_尚未采集。模型确认后 AI 将引导您选择技术栈，"
                "或输入 `/techstack` 随时触发。_\n"
            )

        return "\n".join(lines)

    def _render_doc_generate(self, ctx: AgentContext) -> str:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
        lines = [
            f"# 已生成文档列表\n",
            f"> 更新时间：{now}  |  对话轮次：{ctx.turn_count}\n",
        ]
        if ctx.generated_documents:
            lines.append("| 文档类型 | 生成时间 | 状态 |")
            lines.append("|----------|----------|------|")
            for doc in ctx.generated_documents:
                status_label = {
                    DocumentStatus.CURRENT: "✅ 最新",
                    DocumentStatus.STALE: "⚠️ 需更新",
                    DocumentStatus.SUPERSEDED: "🔄 已替换",
                }.get(doc.status, doc.status.value)
                generated_at = (
                    doc.generated_at.strftime("%Y-%m-%d %H:%M")
                    if doc.generated_at
                    else "—"
                )
                lines.append(
                    f"| {doc.document_type} | {generated_at} | {status_label} |"
                )
            lines.append("")
        else:
            lines.append("_尚未生成任何文档。_\n")

        stale = ctx.get_stale_documents()
        if stale:
            lines.append("## ⚠️ 需要更新的文档\n")
            for doc_type in stale:
                lines.append(f"- {doc_type}")
            lines.append("")

        return "\n".join(lines)

    def _render_review_refine(self, ctx: AgentContext) -> str:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
        lines = [
            f"# 修订记录\n",
            f"> 更新时间：{now}  |  对话轮次：{ctx.turn_count}\n",
        ]
        if ctx.requirement_changes:
            lines.append("## 需求变更历史\n")
            lines.append("| 变更类型 | 目标 | 描述 | 时间 |")
            lines.append("|----------|------|------|------|")
            for c in ctx.requirement_changes:
                changed_at = c.changed_at.strftime("%Y-%m-%d %H:%M")
                lines.append(
                    f"| {c.change_type.value} | {c.target_id or '—'} "
                    f"| {c.description} | {changed_at} |"
                )
            lines.append("")
        else:
            lines.append("_暂无需求变更记录。_\n")

        return "\n".join(lines)
