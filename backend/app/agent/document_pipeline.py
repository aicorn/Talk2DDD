"""DocumentGenerationPipeline: generates DDD documents via AI."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from app.agent.context import AgentContext, DocumentType
from app.agent.prompt_builder import PromptBuilder
from app.services.ai_service import chat_completion

_DOC_PROMPTS: dict[DocumentType, str] = {
    DocumentType.BUSINESS_REQUIREMENT: """请基于以下领域知识，生成一份完整的业务需求文档（Markdown 格式）。

文档结构：
1. 项目概述
2. 业务目标
3. 核心业务场景（每个场景包含：触发条件、主流程、异常流程）
4. 业务规则与约束
5. 词汇表（关键业务术语）
6. 待澄清问题

要求：
- 使用清晰的 Markdown 标题层次
- 业务场景用用例形式描述
- 列出所有已知的待澄清问题""",

    DocumentType.DOMAIN_MODEL: """请基于以下领域知识，生成一份完整的领域模型文档（Markdown 格式）。

文档结构：
1. 领域概述
2. 限界上下文（描述各上下文的职责和边界）
3. 聚合根（每个聚合包含：聚合根实体、包含的实体和值对象、业务不变量）
4. 领域事件
5. 领域服务
6. 仓储接口
7. 概念关系图（用文本或 Mermaid 图表示）

要求：
- 区分实体、值对象、聚合根、领域服务
- 说明聚合之间的关系
- 标注业务规则/不变量""",

    DocumentType.UBIQUITOUS_LANGUAGE: """请基于以下领域知识，生成一份通用语言术语表（Markdown 格式）。

文档结构：
1. 简介（说明通用语言的重要性）
2. 核心术语表（每个术语：名称、类型、定义、示例、相关术语）
3. 业务概念分类（按限界上下文分组）
4. 术语演进说明（如有变更记录）

要求：
- 每个术语必须有精确的业务定义
- 避免技术术语，使用业务语言
- 标注术语的限界上下文归属""",

    DocumentType.USE_CASES: """请基于以下领域知识，生成一份用例说明文档（Markdown 格式）。

文档结构：
1. 用例概览（用例列表和角色列表）
2. 详细用例（每个用例包含：用例编号、名称、参与者、前置条件、主成功场景、扩展/异常场景、后置条件）
3. 用例关系图（用文本表示 include/extend 关系）

要求：
- 覆盖所有已收集的业务场景
- 每个用例有明确的成功和失败路径
- 标注关键业务规则""",

    DocumentType.TECH_ARCHITECTURE: """请基于以下领域知识和技术栈偏好，生成一份技术架构建议文档（Markdown 格式）。

文档结构：
1. 架构原则
2. 整体架构（推荐的分层架构，如六边形架构/洋葱架构）
3. 模块划分（按限界上下文划分微服务或模块）
4. 数据持久化建议（每个聚合的存储策略）
5. 集成方式（限界上下文之间的通信方式：同步/异步）
6. 技术栈选型（严格遵循 [TECH_STACK_BLOCK] 中用户指定的技术；对未指定分类给出推荐并说明原因）
7. 部署建议

要求：
- 与领域模型保持一致
- 说明各架构决策的业务理由
- 如技术栈由 AI 推荐，需在每个选项后注明"（AI 推荐）"及推荐理由""",
}


class DocumentGenerationPipeline:
    """Generates a DDD document by building a specialized prompt and calling AI."""

    def __init__(self) -> None:
        self._prompt_builder = PromptBuilder()

    async def generate(
        self,
        ctx: AgentContext,
        document_type: DocumentType,
        provider: Optional[str] = None,
    ) -> str:
        """Generate a document of *document_type* and return Markdown content."""
        doc_prompt = _DOC_PROMPTS.get(document_type, "请生成对应的 DDD 文档。")
        context_summary = self._build_context_summary(ctx)

        system_prompt = (
            "你是 Talk2DDD 专业 DDD 文档撰写专家。"
            "请严格按照给定的文档结构和要求生成高质量的 DDD 文档。"
            "文档应基于提供的领域知识，内容完整、结构清晰、语言专业。"
        )

        user_prompt = f"{doc_prompt}\n\n## 领域知识摘要\n\n{context_summary}"

        # Inject tech stack block for TECH_ARCHITECTURE documents
        if document_type == DocumentType.TECH_ARCHITECTURE:
            tech_block = self._prompt_builder.build_tech_stack_block(ctx)
            if tech_block:
                user_prompt += f"\n\n{tech_block}"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        return await chat_completion(messages=messages, provider=provider)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_context_summary(self, ctx: AgentContext) -> str:
        dk = ctx.domain_knowledge
        lines = []

        if dk.project_name:
            lines.append(f"**项目名称：** {dk.project_name}")
        if dk.domain_description:
            lines.append(f"**领域背景：** {dk.domain_description}")

        active_scenarios = [
            s for s in dk.business_scenarios if s.status.value != "DEPRECATED"
        ]
        if active_scenarios:
            lines.append(f"\n**业务场景（{len(active_scenarios)} 个）：**")
            for s in active_scenarios:
                lines.append(f"- {s.id} {s.name}：{s.description}")

        if dk.domain_concepts:
            lines.append(f"\n**领域概念（{len(dk.domain_concepts)} 个）：**")
            for c in dk.domain_concepts:
                lines.append(f"- [{c.concept_type.value}] {c.name}：{c.description}")

        if dk.bounded_contexts:
            lines.append(f"\n**限界上下文：**")
            for bc in dk.bounded_contexts:
                concepts_str = (
                    "、".join(bc.concepts) if bc.concepts else "（待确定）"
                )
                lines.append(f"- {bc.name}：{bc.description}（包含：{concepts_str}）")

        if dk.relationships:
            lines.append(f"\n**概念关系：**")
            for r in dk.relationships:
                lines.append(
                    f"- {r.source} --[{r.relation_type}]--> {r.target}"
                )

        pending = [q.question for q in ctx.clarification_queue if not q.answered]
        if pending:
            lines.append(f"\n**待澄清问题：**")
            for q in pending:
                lines.append(f"- {q}")

        ts = ctx.tech_stack_preferences
        if ts.confirmed or not ts.is_empty():
            lines.append(f"\n**技术栈偏好：** {ts.summary()}")

        return "\n".join(lines) if lines else "（领域知识尚在收集中）"
