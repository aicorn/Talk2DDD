# Talk2DDD AI Agent 内核设计

## 1. 概述

### 1.1 设计目标

当前的 AI 对话功能仅将用户消息透传给第三方 AI 平台并返回原始响应，缺乏业务语义和引导能力。本文档设计一个具备完整业务语义的 **Talk2DDD AI Agent**，其核心目标是：

1. **引导式需求采集** — 通过结构化对话主动引导用户讲清楚业务背景、核心问题和关键概念。
2. **实时意图识别** — 识别用户话语中的 DDD 信号（实体、聚合、限界上下文等），在对话中即时建议。
3. **状态驱动的对话流** — 将"从零到 DDD 文档"拆分为若干阶段；AI 在阶段条件满足时提示用户点击「下一阶段」按钮手动推进，确保每个阶段边界清晰、对话内容与阶段保持一致。
4. **知识积累与上下文注入** — 将对话中提取的领域知识持久化，并在后续轮次中注入，保证上下文连贯。
5. **阶段文档自动持久化** — 每次用户发送消息后，阶段文档在聊天界面实时更新的同时，自动以 Markdown 文件的形式保存到"我的项目"中对应的项目里，无需额外操作；用户可随时退出聊天界面，在"我的项目"中查阅各阶段文档。
6. **需求变更管理** — 支持在任意阶段追加新需求、修改已有需求、废弃旧需求，并自动更新对应的阶段文档并重新持久化到项目中。
7. **阶段文档实时展示** — 每个对话阶段维护一份随对话持续更新的"阶段文档"，在聊天界面实时渲染；用户可切换查看任意阶段的文档，始终对当前状态一目了然。

### 1.2 核心约束

- **不修改三方 AI 接口** — Agent 在现有 `ai_service.py` 之上构建；底层仍可使用 OpenAI / DeepSeek / MiniMax。
- **无状态 HTTP 友好** — Agent 状态通过对话上下文序列化存储，每次请求可完整重建，便于水平扩展。
- **渐进增强** — Agent 功能可按阶段增量交付，初期只需 System Prompt 工程，后续叠加工具调用和状态机。

---

## 2. 整体架构

```
┌──────────────────────────────────────────────────────────────────────┐
│                         Talk2DDD AI Agent                            │
│                                                                      │
│  ┌─────────────┐   ┌──────────────────────────────────────────────┐  │
│  │             │   │              Agent 内核 (AgentCore)           │  │
│  │   用户请求   │──▶│                                              │  │
│  │  (消息列表   │   │  ┌────────────┐  ┌──────────────────────┐   │  │
│  │   + 元数据)  │   │  │ 阶段状态机  │  │   上下文管理器        │   │  │
│  └─────────────┘   │  │ PhaseEngine│  │  ContextManager      │   │  │
│                    │  └─────┬──────┘  └──────────┬───────────┘   │  │
│                    │        │                     │               │  │
│                    │  ┌─────▼──────┐  ┌──────────▼───────────┐   │  │
│                    │  │ 提示构建器  │  │   知识提取器           │   │  │
│                    │  │PromptBuilder│  │ KnowledgeExtractor   │   │  │
│                    │  └─────┬──────┘  └──────────────────────┘   │  │
│                    │        │                                     │  │
│                    │  ┌─────▼──────────────────────────────────┐ │  │
│                    │  │         记忆管理器 (MemoryManager)  ← 新  │ │  │
│                    │  │  • 即时记忆：最近 K 轮原文              │ │  │
│                    │  │  • 滚动摘要：AI 压缩旧轮次对话          │ │  │
│                    │  │  • 结构化记忆：DomainKnowledge 注入     │ │  │
│                    │  └─────┬──────────────────────────────────┘ │  │
│                    │        │                                     │  │
│                    │  ┌─────▼──────────────────────────────────┐ │  │
│                    │  │         工具调度器 (ToolDispatcher)      │ │  │
│                    │  │  • extract_domain_concepts              │ │  │
│                    │  │  • generate_document                    │ │  │
│                    │  │  • ask_clarification                    │ │  │
│                    │  │  • validate_ddd_model                   │ │  │
│                    │  └─────┬──────────────────────────────────┘ │  │
│                    │        │                                     │  │
│                    │  ┌─────▼──────────────────────────────────┐ │  │
│                    │  │    阶段文档渲染器 (PhaseDocumentRenderer) │ │  │
│                    │  │  每轮对话后将 AgentContext 渲染为         │ │  │
│                    │  │  当前阶段的 Markdown 文档（无 AI 调用）   │ │  │
│                    │  └─────┬──────────────────────────────────┘ │  │
│                    └────────│────────────────────────────────────┘  │
│                             │                                        │
│                    ┌────────▼────────────────────────────────────┐  │
│                    │         AI Provider 层 (现有 ai_service)     │  │
│                    │    OpenAI / DeepSeek / MiniMax               │  │
│                    └─────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 3. 对话阶段状态机

Agent 将整个需求—文档生命周期划分为 **5 个阶段**，以有限状态机（FSM）驱动。

```
                        ┌─────────────────────────────────────────────┐
                        │                                             │
          ┌─────┐  触发  ▼  ┌──────┐      ┌──────┐      ┌──────┐    │
  开始 ──▶ │ P1  │──────▶│ P2   │─────▶│ P3   │─────▶│ P4   │    │
           │ 破冰 │       │ 需求  │      │ 领域  │      │ 模型  │    │
           │ 引入 │       │ 收集  │      │ 探索  │      │ 设计  │    │
           └─────┘       └──▲───┘      └──────┘      └──────┘    │
                            │  ▲ 需求变更回溯                        │
                            │  └────────────────────────────────────┘
                         ┌──────────────────────────────────▼────┐
                         │                          ┌──────┐      │
                         │                    ──────│ P5   │──────┘
                         │                          │ 审阅  │
                         │                          │ 完善  │
                         │                          └──────┘
                         └────────────────────────────────────────┘
```

> **需求变更回溯**：在 P3~P5 任意阶段，用户说出"我们还有一个新需求…"或使用 `/change` 命令时，`PhaseEngine` 将触发 **需求变更回溯**，把阶段临时切回 P2（需求收集），采集完毕后重新推进，并自动重新渲染并保存受影响的阶段文档到项目中。

### 阶段定义

| 阶段 | 标识 | 名称 | 目标 | AI 建议推进时机（用户点击按钮后实际切换） | 阶段文档类型 |
|------|------|------|------|------------------------------------------|------------|
| 1 | `ICEBREAK` | 破冰引入 | 了解用户角色和项目背景 | 收集到项目名称、领域背景 | 项目简介 |
| 2 | `REQUIREMENT` | 需求收集 | 梳理业务流程和痛点 | 收集到 ≥3 个核心业务场景 | 业务需求草稿 |
| 3 | `DOMAIN_EXPLORE` | 领域探索 | 识别核心概念和术语 | 识别出 ≥5 个领域概念候选 | 领域概念词汇表 |
| 4 | `MODEL_DESIGN` | 模型设计 | 设计聚合、实体、值对象；**确认技术栈偏好** | 用户确认领域模型草稿 **且** 完成技术栈确认（或明确跳过） | 领域模型草稿 |
| 5 | `REVIEW_REFINE` | 审阅完善 | 根据反馈修订与完善各阶段文档 | 用户标记项目完成 | 修订记录 |

> **注意**：阶段不自动推进。AI 在对话中告知用户条件已满足时，由用户点击导航栏「下一阶段 →」按钮手动确认切换。这确保每个阶段的边界清晰，对话内容不会与当前阶段脱节。
>
> **阶段文档自动保存**：每轮对话发送后，当前阶段文档在更新右侧面板的同时，会自动以 Markdown 文件形式持久化到"我的项目"中对应的项目里，无需额外触发操作。用户可随时退出聊天界面，在"我的项目"中查阅各阶段文档。

### 阶段跳转规则

- **手动推进**：用户点击顶部导航栏「下一阶段 →」按钮（或输入 `/next` 指令）向前推进一个阶段。
- **手动回退**：用户点击「← 上一阶段」按钮（或输入 `/back` 指令）回退一个阶段。
- **快捷跳转**：用户可在任意阶段输入指令（`/model`）直接跳转到目标阶段。
- **需求变更回溯**：在 P3~P5 阶段检测到需求变更意图时，回溯至 P2 采集新需求，完成后重新推进至变更前的阶段；受影响的阶段文档自动重新渲染并保存到项目中。

---

## 4. 上下文管理器（ContextManager）

### 4.1 对话上下文数据结构

```
AgentContext
├── session_id: UUID                   # 对话会话 ID
├── project_id: UUID | None            # 关联项目（可为空）
├── current_phase: Phase               # 当前阶段
├── phase_before_change: Phase | None  # 需求变更回溯前的原始阶段
├── phase_history: List[PhaseTransition]  # 阶段切换记录
│
├── domain_knowledge: DomainKnowledge  # 提取的领域知识
│   ├── project_name: str
│   ├── domain_description: str
│   ├── business_scenarios: List[BusinessScenario]
│   │   ├── id: str
│   │   ├── name: str
│   │   ├── description: str
│   │   ├── status: ScenarioStatus     # ACTIVE | MODIFIED | DEPRECATED
│   │   └── version: int               # 每次变更递增
│   ├── domain_concepts: List[DomainConcept]
│   │   ├── name: str
│   │   ├── concept_type: ConceptType  # ENTITY | VALUE_OBJECT | SERVICE | EVENT
│   │   ├── description: str
│   │   └── confidence: float          # 0.0 ~ 1.0
│   ├── bounded_contexts: List[BoundedContext]
│   └── relationships: List[ConceptRelation]
│
├── requirement_changes: List[RequirementChange]  # 需求变更历史
│   ├── change_id: UUID
│   ├── change_type: ChangeType        # ADD | MODIFY | DEPRECATE
│   ├── target_id: str                 # 被变更的场景/概念 ID
│   ├── description: str               # 变更说明
│   ├── changed_at: datetime
│   └── affected_phases: List[str]     # 受影响的阶段列表（对应阶段文档需重新保存）
│
├── clarification_queue: List[Question]    # 待澄清问题队列
│
└── tech_stack_preferences: TechStackPreferences  # 技术栈偏好（P4 阶段采集）
    ├── confirmed: bool                    # 是否已经过用户明确确认（或明确跳过）
    ├── skipped: bool                      # 用户选择跳过，由 AI 自行推荐
    ├── frontend: List[TechChoice]         # 前端技术栈
    ├── backend: List[TechChoice]          # 后端技术栈
    ├── database: List[TechChoice]         # 数据库
    ├── infrastructure: List[TechChoice]   # 基础设施 / 部署
    ├── messaging: List[TechChoice]        # 消息 / 事件流
    └── custom: List[TechChoice]           # 其他自定义技术

    # TechChoice 子结构：
    # ├── name: str                        # 技术名称，如 "React"、"Spring Boot"
    # ├── category: str                    # 所属分类（同上层 key）
    # ├── version: str | None             # 版本约束（可选），如 ">=17"
    # ├── reason: str | None              # 选择原因（用户填写或 AI 推荐说明）
    # └── proficiency: str               # 用户熟悉程度: FAMILIAR | LEARNING | UNFAMILIAR
```

### 4.2 上下文注入策略

每次请求时，`ContextManager` 将当前已知的领域知识压缩成结构化摘要，注入到 System Prompt 的专用区块中：

```
[CONTEXT_BLOCK]
当前阶段: {phase}
已知项目: {project_name} — {domain_description}
核心概念: {concepts_summary}
待澄清: {pending_clarifications}
近期需求变更: {recent_changes_summary}   ← 最近 3 次变更的摘要
技术栈偏好: {tech_stack_summary}         ← 用户已确认的技术栈（未确认时为空）
[/CONTEXT_BLOCK]
```

这样即使 AI Provider 不支持持久化存储，每轮对话都能感知历史状态和最近的需求变化。

### 4.3 上下文持久化

```
HTTP 请求 (含 session_id)
    → 从 Redis/数据库加载 AgentContext
    → 执行 Agent 推理
    → 更新 AgentContext（增量合并）
    → 持久化回 Redis/数据库
    → 返回响应
```

- **热存储**：Redis（TTL 24h），用于活跃会话的快速读写。
- **冷存储**：PostgreSQL `conversations` 表，持久化消息列表和关联的 `AgentContext` JSON 列。

---

### 4.4 记忆机制（MemoryManager）

#### 4.4.1 设计动机

LLM 具有固定的上下文窗口（Context Window），随着对话轮次增加，若将全部历史消息逐字传给 AI，会导致：

1. **Token 超限** — 消息总量超出 Provider 的 `max_tokens` 限制，请求直接报错。
2. **上下文稀释** — 大量早期消息"稀释"了近期关键信息（如项目名称、核心需求），AI 更关注最近的内容而"遗忘"更早的信息。
3. **费用增加** — 输入 Token 越多，API 费用越高；长期会话成本不可控。

> 上述问题即为用户反馈"只聊几轮就忘记了项目是什么"的根本原因。

解决方案是引入 **MemoryManager** 组件，实现三层记忆模型，在保留关键信息的同时压缩上下文体积。

---

#### 4.4.2 三层记忆模型

```
┌─────────────────────────────────────────────────────────────────┐
│                       三层记忆模型                               │
├───────────────┬─────────────────────────────────────────────────┤
│ Layer 1       │ 即时记忆（Immediate Memory）                      │
│ 最近 K 轮     │ 原文保留，逐字传入 messages 列表                   │
│ （默认 K=10） │ 保证 AI 完整感知最近对话上下文                      │
├───────────────┼─────────────────────────────────────────────────┤
│ Layer 2       │ 滚动摘要（Rolling Summary）                       │
│ 第 1～N-K 轮  │ 由 AI 压缩为 200~400 字的结构化摘要               │
│               │ 注入到 System Prompt 的 [MEMORY_SUMMARY] 区块    │
│               │ 每 M 轮（默认 M=5）或当 token 超阈值时重新压缩     │
├───────────────┼─────────────────────────────────────────────────┤
│ Layer 3       │ 结构化长期记忆（Structured Knowledge）            │
│ 全会话        │ AgentContext.domain_knowledge 中的领域知识        │
│               │ 以 JSON 结构化存储，始终完整注入 [CONTEXT_BLOCK]  │
│               │ 天然压缩：无论对话多长，token 占用固定且精简        │
└───────────────┴─────────────────────────────────────────────────┘
```

三层配合形成**完整记忆**：

```
System Prompt
  ├── [MEMORY_SUMMARY]  ← Layer 2：旧轮次摘要（动态）
  ├── [CONTEXT_BLOCK]   ← Layer 3：结构化领域知识（动态）
  └── 阶段指令 + 格式约束

Messages 列表
  ├── 最近 K 轮 user/assistant 消息  ← Layer 1（动态）
  └── 当前 user 消息
```

---

#### 4.4.3 压缩触发条件与算法

**触发条件**（满足任一即触发）：

| 条件 | 说明 | 默认阈值 |
|------|------|----------|
| 首次触发 | `turn_count >= SUMMARY_TRIGGER_TURNS`，首次启动压缩 | 10 轮 |
| Token 超预算 | 预估输入 token 超过 `MAX_INPUT_TOKENS` | 6000 tokens |
| 定期刷新 | 首次触发后，每满 `SUMMARY_REFRESH_INTERVAL` 轮增量刷新摘要 | 每 5 轮（即第 10、15、20 轮…） |

> **说明**：`SUMMARY_REFRESH_INTERVAL`（默认 5）是在首次触发（第 10 轮）之后的增量刷新频率，而非从第 1 轮开始计算。两个参数不冲突：前者控制"何时开始"，后者控制"之后多久刷新一次"。

**压缩算法**（逐步累积式）：

```
function compress_memory(history, existing_summary):
    # 待压缩消息 = 超过 K 轮的所有旧消息
    old_messages = history[:-K]

    # 构造压缩提示
    prompt = f"""
    你是记忆压缩助手。请将以下对话历史与已有摘要合并，
    生成一份不超过 400 字的结构化摘要，重点保留：
    1. 用户的项目名称和业务背景
    2. 已确认的核心需求和业务场景
    3. 用户的决策和偏好
    4. 尚未解决的问题或待澄清事项

    已有摘要：{existing_summary}
    新增对话：{old_messages}
    """

    # 调用轻量 AI 模型生成摘要（如 gpt-4o-mini）
    new_summary = ai_service.chat_completion(
        messages=[{"role": "user", "content": prompt}],
        model="summary",  # 可配置单独的摘要模型
    )

    return new_summary
```

**关键设计决策**：
- 采用**累积式摘要**（新摘要 = 旧摘要 + 新增消息）而非全量重压缩，减少 AI 调用量。
- 压缩操作**异步执行**，不阻塞主对话响应；若压缩未完成，降级为仅使用结构化记忆（Layer 3）。
- 摘要单独存储在 `AgentContext.conversation_summary` 字段，与 `domain_knowledge` 分离。

---

#### 4.4.4 AgentContext 数据结构扩展

在现有 `AgentContext` 中新增以下字段：

```
AgentContext
├── ...（现有字段不变）
│
├── conversation_summary: str         # Layer 2：当前的滚动对话摘要（AI 生成）
│                                      # 初始为空；首次压缩后更新
├── summary_last_updated_turn: int    # 最后一次更新摘要时的 turn_count
├── summary_covers_turns: int         # 摘要已覆盖的历史轮次数（用于判断是否需要刷新）
│
└── memory_config: MemoryConfig       # 记忆参数配置
    ├── immediate_memory_turns: int   # K 值（保留最近 K 轮原文），默认 10
    ├── min_immediate_memory_turns: int # K 值下限（token 超预算时自动缩减 K，但不低于此值），默认 2
    ├── summary_trigger_turns: int    # 首次压缩阈值（turn_count >= 此值时触发），默认 10
    ├── summary_refresh_interval: int # 首次压缩后每隔 M 轮增量刷新摘要，默认 5
    └── max_input_tokens: int         # 输入 token 预算，默认 6000
```

---

#### 4.4.5 MemoryManager 接口设计

```python
class MemoryManager:
    """管理 Agent 对话记忆的三层模型。"""

    async def get_messages_for_ai(
        self,
        ctx: AgentContext,
        db: AsyncSession,
    ) -> list[dict]:
        """
        返回应传给 AI Provider 的完整消息列表（Layer 1）。
        - 从 Message 表加载该 session 的全部历史消息
        - 仅返回最近 K 轮（immediate_memory_turns）的 user/assistant 消息
        - 确保不超过 max_input_tokens token 预算
        """

    async def get_summary_block(self, ctx: AgentContext) -> str:
        """
        返回 [MEMORY_SUMMARY] 区块内容（Layer 2）。
        - 若 conversation_summary 不为空，返回其内容
        - 若为空，返回 ""（PromptBuilder 将跳过该区块）
        """

    async def maybe_compress(
        self,
        ctx: AgentContext,
        db: AsyncSession,
        provider: str | None = None,
    ) -> None:
        """
        检查是否需要压缩记忆，若需要则异步执行压缩。
        - 更新 ctx.conversation_summary
        - 更新 ctx.summary_last_updated_turn
        - 不阻塞主对话；压缩失败时静默降级
        """

    def estimate_tokens(self, messages: list[dict]) -> int:
        """
        粗估消息列表的 token 数（按每字符 ~0.4 token 估算，
        无需引入 tiktoken 等额外依赖）。
        """
```

---

#### 4.4.6 与 PromptBuilder 的集成

`PromptBuilder.build()` 在组装 System Prompt 时需调用 `MemoryManager.get_summary_block()`，将摘要插入新的 Layer 3（原 Layer 3 上下文块改为 Layer 4）：

```
┌────────────────────────────────────────────────────────────────┐
│ Layer 1: 角色定义（固定）                                        │
├────────────────────────────────────────────────────────────────┤
│ Layer 2: 当前阶段指令（按阶段切换）                               │
├────────────────────────────────────────────────────────────────┤
│ Layer 3: 对话记忆摘要（动态，可选）          ← 新增              │
│   "[MEMORY_SUMMARY]                                            │
│    项目背景：用户想做一个个人博客网站…                            │
│    已确认需求：仅作者可发布，读者可评论…                          │
│    [/MEMORY_SUMMARY]"                                          │
├────────────────────────────────────────────────────────────────┤
│ Layer 4: 已积累的领域上下文（动态注入）                           │
│   "[CONTEXT_BLOCK] ... [/CONTEXT_BLOCK]"                       │
├────────────────────────────────────────────────────────────────┤
│ Layer 5: 工具调用格式说明（可选，按需开启）                        │
├────────────────────────────────────────────────────────────────┤
│ Layer 6: 输出格式约束（按阶段）                                   │
└────────────────────────────────────────────────────────────────┘
```

> **注意**：`[MEMORY_SUMMARY]` 区块仅在 `conversation_summary` 非空时插入，避免早期轮次引入无意义的空块。

---

#### 4.4.7 Token 预算管理

为确保不超过 Provider 的上下文窗口限制，MemoryManager 按以下优先级裁剪：

```
总 token 预算 (MAX_INPUT_TOKENS = 6000)
  ├── 系统提示 System Prompt              ~1200 tokens（固定）
  ├── [MEMORY_SUMMARY] 摘要区块           ~200  tokens（有则包含）
  ├── [CONTEXT_BLOCK] 结构化上下文        ~400  tokens（有则包含）
  └── 消息历史 Layer 1                    剩余预算 / 自动裁剪
        若剩余 < 即时消息所需，则减少 K 值（最少保留 2 轮）
```

---

## 5. 提示构建器（PromptBuilder）

### 5.1 System Prompt 分层结构

```
┌────────────────────────────────────────────────────────────────┐
│ Layer 1: 角色定义（固定）                                        │
│   "你是 Talk2DDD 专业 DDD 顾问，精通领域驱动设计..."              │
├────────────────────────────────────────────────────────────────┤
│ Layer 2: 当前阶段指令（按阶段切换）                               │
│   "当前处于「需求收集」阶段，你的任务是..."                        │
├────────────────────────────────────────────────────────────────┤
│ Layer 3: 对话记忆摘要（动态，可选）— 由 MemoryManager 提供        │
│   "[MEMORY_SUMMARY] 项目背景：... 已确认需求：...                │
│    [/MEMORY_SUMMARY]"                                          │
│   注：仅在 conversation_summary 非空时插入（见 §4.4.6）          │
├────────────────────────────────────────────────────────────────┤
│ Layer 4: 已积累的领域上下文（动态注入）                           │
│   "[CONTEXT_BLOCK] ... [/CONTEXT_BLOCK]"                       │
├────────────────────────────────────────────────────────────────┤
│ Layer 5: 工具调用格式说明（可选，按需开启）                        │
│   "当识别出新领域概念时，调用 extract_domain_concepts 工具..."    │
├────────────────────────────────────────────────────────────────┤
│ Layer 6: 输出格式约束（按阶段）                                   │
│   "每次回复末尾必须包含 [NEXT_QUESTION] 标记..."                  │
└────────────────────────────────────────────────────────────────┘
```

> **变更说明**：§4.4 中引入 MemoryManager 后，System Prompt 由原来的 5 层扩展为 6 层。Layer 3 新增对话记忆摘要区块 `[MEMORY_SUMMARY]`，原 Layer 3（领域上下文）顺移为 Layer 4，其余层依次后移。

### 5.2 各阶段 System Prompt 要点

#### P1 破冰引入
```
目标：让用户介绍项目背景，放松引导，不要一次提太多问题。
引导词：项目是做什么的？主要解决什么业务问题？谁是核心用户？
```

#### P2 需求收集
```
目标：逐一梳理主要业务流程，挖掘边界场景。
技巧：5W1H 提问法（谁、何时、何地、做什么、为什么、如何）
识别信号：用户描述动词（注册、下单、审批）→ 业务场景候选
```

#### P3 领域探索
```
目标：从需求中提炼领域术语，建立通用语言。
识别信号：名词（订单、商品、用户）→ 实体/值对象候选
          动词（提交、确认、取消）→ 领域事件候选
          规则（"必须"、"只有…才能"）→ 业务规则候选
提示：对每个识别的概念向用户确认含义，建立术语表。
```

#### P4 模型设计
```
目标：引导用户确定聚合边界和上下文划分；并在模型草稿确认后询问用户的技术栈偏好。
提问模板：
  - "{概念A}" 和 "{概念B}" 是否总是一起变化？（聚合判断）
  - 哪些操作必须保持原子性？（事务边界）
  - 不同团队负责哪些业务？（限界上下文边界）
技术栈询问时机：领域模型草稿经用户确认后，自然过渡询问：
  - "模型已经清晰了，接下来我们聊聊技术选型。你们前端打算用什么框架？"
  - "后端语言和框架有偏好吗？是 Java/Spring Boot、Python、Node.js 还是其他？"
  - "数据库方面有确定的选择吗？"
  - 如果用户无偏好，调用 confirm_tech_stack（skipped=true），由 AI 根据领域模型推荐。
输出：领域模型草稿（文字描述 + 树形结构）+ 技术栈偏好记录
```

#### P5 审阅完善
```
目标：收集用户对各阶段文档的反馈，定向修订，完善项目文档。
模式：diff 式修改（"第3节的聚合边界有误，请修改..."）
支持：全量重写 / 局部修订 / 版本回溯
提示：用户可在"我的项目"中随时查阅任一阶段的最新 Markdown 文档。
```

---

## 6. 知识提取器（KnowledgeExtractor）

知识提取器负责从 AI 的每轮回复（以及用户输入）中解析出结构化领域知识，供 `ContextManager` 持久化。

### 6.1 提取流程

```
AI 回复文本
    │
    ▼
①  结构化标记解析
    （解析 [CONCEPT]...[/CONCEPT]、[SCENARIO] 等 XML 标记）
    │
    ▼
②  NLP 兜底提取（当标记缺失时）
    （命名实体识别：抽取名词、动词短语）
    │
    ▼
③  置信度评估
    （规则打分 + AI 辅助验证）
    │
    ▼
④  增量合并到 DomainKnowledge
    （去重 + 相似度合并）
```

### 6.2 AI 辅助标记格式（嵌入在 AI 回复中）

当 `PromptBuilder` 开启工具模式时，要求 AI 在回复中嵌入结构化标记：

```xml
<!-- 概念识别 -->
<concept type="ENTITY" name="订单" confidence="0.9">
  用户在系统中发起的购买请求，包含商品列表和支付信息。
</concept>

<!-- 业务场景 -->
<scenario id="S001" name="用户下单">
  用户选择商品并填写收货信息，系统生成订单并通知支付。
</scenario>

<!-- 待澄清问题 -->
<clarification id="Q001">
  "订单取消"后库存是立即恢复还是异步恢复？
</clarification>
```

---

## 7. 工具调度器（ToolDispatcher）

Agent 支持通过 **Function Calling**（OpenAI / DeepSeek 均支持）调用以下内置工具：

| 工具名 | 触发时机 | 输入 | 输出 |
|--------|----------|------|------|
| `extract_domain_concepts` | AI 识别到新概念时 | 概念名称、类型、描述 | 更新后的 `DomainKnowledge` |
| `ask_clarification` | 存在歧义或信息缺失 | 问题文本、所属场景 | 加入 `clarification_queue` |
| `advance_phase` | 用户点击导航按钮或输入斜线命令时 | 目标阶段 | 新阶段 + 阶段引导消息 |
| `validate_ddd_model` | P4 阶段模型草稿完成后 | 领域模型 JSON | 验证结果 + 改进建议 |
| `record_requirement_change` | 检测到需求变更意图时 | 变更类型、目标场景/概念、变更描述 | `RequirementChange` 记录 + 受影响阶段列表 |
| `confirm_tech_stack` | P4 阶段模型确认后，采集用户技术栈偏好 | 各分类技术选择列表、`skipped` 标志 | 更新后的 `TechStackPreferences` |

### 工具调用示意（OpenAI Function Calling 格式）

```json
{
  "name": "extract_domain_concepts",
  "description": "将对话中识别到的领域概念提取并存储",
  "parameters": {
    "type": "object",
    "properties": {
      "concepts": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "name":        { "type": "string" },
            "type":        { "type": "string", "enum": ["ENTITY","VALUE_OBJECT","AGGREGATE","SERVICE","EVENT","POLICY"] },
            "description": { "type": "string" },
            "confidence":  { "type": "number", "minimum": 0, "maximum": 1 }
          },
          "required": ["name","type","description"]
        }
      }
    },
    "required": ["concepts"]
  }
}
```

```json
{
  "name": "record_requirement_change",
  "description": "记录用户提出的需求变更（新增、修改或废弃），并重新渲染受影响的阶段文档并保存到项目中",
  "parameters": {
    "type": "object",
    "properties": {
      "change_type": {
        "type": "string",
        "enum": ["ADD", "MODIFY", "DEPRECATE"],
        "description": "ADD=追加新需求; MODIFY=修改已有需求; DEPRECATE=废弃/删除需求"
      },
      "target_id": {
        "type": "string",
        "description": "被修改的业务场景或概念的 ID（ADD 时为空字符串）"
      },
      "description": {
        "type": "string",
        "description": "变更内容的自然语言描述"
      },
      "affected_phases": {
        "type": "array",
        "items": { "type": "string", "enum": ["ICEBREAK","REQUIREMENT","DOMAIN_EXPLORE","MODEL_DESIGN","REVIEW_REFINE"] },
        "description": "预计受影响的阶段列表（对应阶段文档将重新渲染并保存到项目中）"
      },
      "trigger_phase_rollback": {
        "type": "boolean",
        "description": "是否需要回溯到 REQUIREMENT 阶段重新采集细节（变更较大时为 true）"
      }
    },
    "required": ["change_type","description","affected_phases","trigger_phase_rollback"]
  }
}
```

```json
{
  "name": "confirm_tech_stack",
  "description": "记录用户确认（或跳过）的技术栈偏好，写入 P4 领域模型草稿文档",
  "parameters": {
    "type": "object",
    "properties": {
      "skipped": {
        "type": "boolean",
        "description": "true=用户无偏好，由 AI 根据领域模型自行推荐; false=用户有明确偏好"
      },
      "frontend": {
        "type": "array",
        "items": { "$ref": "#/definitions/TechChoice" },
        "description": "前端框架/库，如 React、Vue、Angular"
      },
      "backend": {
        "type": "array",
        "items": { "$ref": "#/definitions/TechChoice" },
        "description": "后端语言/框架，如 Spring Boot、Django、Express"
      },
      "database": {
        "type": "array",
        "items": { "$ref": "#/definitions/TechChoice" },
        "description": "数据库，如 PostgreSQL、MySQL、MongoDB、Redis"
      },
      "infrastructure": {
        "type": "array",
        "items": { "$ref": "#/definitions/TechChoice" },
        "description": "基础设施/部署，如 Docker、Kubernetes、AWS、阿里云"
      },
      "messaging": {
        "type": "array",
        "items": { "$ref": "#/definitions/TechChoice" },
        "description": "消息/事件流，如 Kafka、RabbitMQ"
      },
      "custom": {
        "type": "array",
        "items": { "$ref": "#/definitions/TechChoice" },
        "description": "其他自定义技术（不属于上述分类）"
      }
    },
    "definitions": {
      "TechChoice": {
        "type": "object",
        "properties": {
          "name":        { "type": "string", "description": "技术名称，如 'React'" },
          "version":     { "type": "string", "description": "版本约束（可选），如 '>=17'" },
          "reason":      { "type": "string", "description": "选择原因或说明（可选）" },
          "proficiency": { "type": "string", "enum": ["FAMILIAR","LEARNING","UNFAMILIAR"],
                           "description": "用户对该技术的熟悉程度" }
        },
        "required": ["name"]
      }
    },
    "required": ["skipped"]
  }
}
```

---

## 8. 需求变更管理（RequirementChangeManager）

### 8.1 需求变更的三种类型

| 类型 | 标识 | 典型用户话语示例 | 处理方式 |
|------|------|----------------|---------|
| 追加新需求 | `ADD` | "我们还需要支持…" / "另外有个场景…" | 回溯 P2 采集细节，更新 `business_scenarios`，追加相关概念，重新保存受影响阶段文档 |
| 修改已有需求 | `MODIFY` | "之前说的 X 其实应该是…" / "需求有变，Y 改成…" | 定位目标场景/概念，原地更新，版本号递增，重新渲染并保存受影响阶段文档 |
| 废弃旧需求 | `DEPRECATE` | "X 功能砍掉了" / "不需要…了" | 将目标场景状态改为 `DEPRECATED`，重新渲染并保存受影响阶段文档，从领域模型中移除或注释相关概念 |

### 8.2 变更检测信号

`PromptBuilder` 在 P3~P5 阶段的 System Prompt 中增加如下指令，使 AI 主动识别需求变更意图：

```
【需求变更检测】
当用户话语中出现以下信号时，立即调用 record_requirement_change 工具：
  • "还有一个需求"、"另外"、"补充一点" → ADD
  • "之前说的…其实"、"改一下"、"调整一下"、"变成了" → MODIFY  
  • "取消"、"砍掉"、"不需要了"、"去掉" → DEPRECATE
检测到变更时，先向用户确认变更范围，再调用工具记录。
```

### 8.3 需求变更处理流程

```
用户表达需求变更意图
        │
        ▼
① AI 识别变更类型（ADD / MODIFY / DEPRECATE）
        │
        ▼
② Agent 向用户确认变更范围
   "你是想新增「退款流程」这个场景，还是修改之前的「订单取消」？"
        │
        ▼
③ 调用 record_requirement_change 工具
   - 写入 RequirementChange 记录
   - 更新目标 BusinessScenario 的 status / version
   - 计算 affected_phases
        │
        ▼
④ 重新渲染受影响的阶段文档并保存到项目中
   （PhaseDocumentRenderer 对每个受影响阶段重新渲染，写入项目文档）
        │
        ▼
⑤ 判断是否需要阶段回溯
   ┌──────────────┬───────────────────────────────────────────────┐
   │ trigger=true │  PhaseEngine 回溯到 P2，采集新需求细节          │
   │              │  完成后推进至变更前的阶段（phase_before_change） │
   ├──────────────┼───────────────────────────────────────────────┤
   │ trigger=false│  当前阶段不变，直接将变更摘要注入下一轮 Prompt   │
   └──────────────┴───────────────────────────────────────────────┘
        │
        ▼
⑥ Agent 向用户展示变更影响摘要
   "已记录需求变更。受影响的阶段文档已重新渲染并保存到项目中：[需求收集, 领域探索]。"
```

### 8.4 冲突检测

当新增或修改需求时，`KnowledgeExtractor` 会将新需求与 `domain_knowledge` 中已有内容进行一致性比对：

| 冲突类型 | 示例 | 处理方式 |
|----------|------|---------|
| 概念重复 | 新增"客户"而已有"用户" | 提示用户确认是否为同一概念，合并或区分 |
| 规则矛盾 | 已有"订单不可修改"，新增"订单可在24h内修改" | 标记冲突，要求用户明确优先级 |
| 边界模糊 | 新场景涉及两个已有限界上下文 | 询问归属，或建议新增上下文 |

冲突以 `<clarification>` 标记输出，进入 `clarification_queue`，Agent 会在下一轮优先引导用户解决。

### 8.5 XML 标记扩展（需求变更）

```xml
<!-- 需求变更标记 -->
<requirement_change type="ADD" trigger_rollback="false">
  <description>新增「积分兑换」业务场景</description>
  <affected_phases>REQUIREMENT,DOMAIN_EXPLORE</affected_phases>
</requirement_change>

<requirement_change type="MODIFY" target_id="S003" trigger_rollback="true">
  <description>将「订单取消」改为支持部分取消</description>
  <affected_phases>REQUIREMENT,DOMAIN_EXPLORE,MODEL_DESIGN</affected_phases>
</requirement_change>

<!-- 冲突检测标记 -->
<conflict type="RULE_CONTRADICTION" concepts="订单不可修改,订单可在24h内修改">
  两条规则存在矛盾，需用户明确优先级。
</conflict>
```

---

## 9. 阶段文档自动保存机制（PhaseDocumentPersistence）

每次用户发送消息并收到 AI 回复后，`PhaseDocumentRenderer` 渲染当前阶段文档（纯模板，无 AI 调用），渲染结果除更新右侧面板外，**同步写入"我的项目"中对应项目的阶段文档存储**，以 Markdown 文件形式持久化。

```
用户发送消息 → AI 回复 → KnowledgeExtractor 更新 AgentContext
        │
        ▼
PhaseDocumentRenderer.render(ctx)
  （纯模板渲染，毫秒级完成）
        │
        ├──▶ 更新右侧阶段文档面板（通过 chat 响应体 phase_document 字段）
        │
        └──▶ PhaseDocumentPersistence.save(project_id, phase, content)
               将 Markdown 内容写入 Project 对应的阶段文档记录
               （覆盖写：每轮对话只保留最新版本）
```

### 9.1 保存策略

- **触发时机**：每轮对话（`/chat` 和 `/switch-phase`）完成后自动触发，无需用户手动操作。
- **保存粒度**：每个阶段维护一份独立的 Markdown 文档，与 `PhaseDocument` 表一一对应。
- **覆盖写**：同一阶段的文档每轮都覆盖，仅保留最新渲染结果；历史变化通过 `PhaseDocument.turn_count` 和 `rendered_at` 字段追溯。
- **项目关联**：文档关联到 `AgentContext.project_id`；若项目尚未创建，`AgentCore` 在收集到足够的域知识（至少含项目名称）时自动创建项目。
- **需求变更时**：`record_requirement_change` 工具执行后，对受影响的所有阶段重新渲染并保存，确保项目文档始终反映最新状态。

### 9.2 用户访问路径

用户可通过以下两种方式查阅阶段文档：

1. **聊天界面右侧面板** — 实时展示当前阶段文档，可切换标签查看其他阶段。
2. **"我的项目"** — 退出聊天界面后，进入"我的项目"选择对应项目，查看各阶段 Markdown 文档。

### 9.3 各阶段文档与项目的对应关系

| 阶段 | 文档名（项目中显示） | Markdown 文件内容 |
|------|-------------------|-----------------|
| P1 `ICEBREAK` | 项目简介 | 项目名称、领域背景、核心用户 |
| P2 `REQUIREMENT` | 业务需求草稿 | 业务场景列表、待澄清问题 |
| P3 `DOMAIN_EXPLORE` | 领域概念词汇表 | 领域概念（名称、类型、描述） |
| P4 `MODEL_DESIGN` | 领域模型草稿 | 限界上下文、聚合/实体/值对象、技术栈偏好 |
| P5 `REVIEW_REFINE` | 修订记录 | 需求变更历史、修订说明 |

---

## 10. 阶段文档渲染器（PhaseDocumentRenderer）

### 10.1 设计原则

`PhaseDocumentRenderer` 是一个**纯模板渲染器**，不调用 AI，直接从 `AgentContext` 中已有的结构化数据生成当前阶段对应的 Markdown 文档。它在每轮对话的 `ContextManager.merge()` 完成后立即运行，将渲染结果写入 `PhaseDocument`（持久化）并在 API 响应中返回给前端；同时触发 `PhaseDocumentPersistence` 将文档保存到"我的项目"中。

**特点**：
- ⚡ **零延迟** — 无 AI 调用，毫秒级完成，不影响主流程响应时间
- 🔄 **每轮更新** — 每次对话后自动重新渲染，始终反映最新状态
- 💾 **自动保存** — 渲染后立即写入"我的项目"，用户无需手动触发
- 🗂 **五个阶段各有专属模板** — 模板与阶段绑定，仅渲染本阶段已收集到的内容

### 10.2 各阶段文档模板

| 阶段 | 阶段文档名称 | 模板包含的关键内容 |
|------|------------|-----------------|
| P1 `ICEBREAK` | **项目简介** | 项目名称、领域背景、核心用户、已知痛点（来自 `domain_knowledge.project_name` / `domain_description`） |
| P2 `REQUIREMENT` | **业务需求草稿** | 已收集业务场景列表（含状态和版本）、待澄清问题 |
| P3 `DOMAIN_EXPLORE` | **领域概念词汇表** | 所有已识别概念（名称、类型、描述、置信度），按类型分组 |
| P4 `MODEL_DESIGN` | **领域模型草稿** | 限界上下文列表、聚合/实体/值对象树形结构、概念关系、技术栈偏好 |
| P5 `REVIEW_REFINE` | **修订记录** | 所有需求变更历史、文档修订说明、版本对比摘要 |

### 10.3 P2 阶段文档示例输出

```markdown
# 业务需求草稿
**项目**：电商平台 · 当前阶段：需求收集 · 更新时间：2024-01-01 10:30

## 核心业务场景（3 / 3 已收集）

| # | 场景 | 状态 | 版本 |
|---|------|------|------|
| S001 | 用户注册与登录 | ✅ ACTIVE | v1 |
| S002 | 商品浏览与搜索 | ✅ ACTIVE | v1 |
| S003 | 订单提交与支付 | ⚠️ MODIFIED | v2 |

## 待澄清问题

- [ ] Q001：支付失败后订单是立即关闭还是保留15分钟？
- [ ] Q002：是否需要支持分期付款？
```

### 10.4 PhaseDocument 数据结构

```
PhaseDocument
├── id: UUID
├── conversation_id: UUID (FK)
├── phase: str                     # ICEBREAK | REQUIREMENT | ...
├── content: str                   # Markdown 正文
├── rendered_at: datetime          # 最后渲染时间（每轮对话后更新）
└── turn_count: int                # 对应的对话轮次序号
```

---

## 11. 完整请求处理流程

```
                   用户发送消息
                        │
                        ▼
              ① 加载 AgentContext
                (Redis / DB)
                        │
                        ▼
              ② MemoryManager.get_messages_for_ai()   ← 记忆机制
                从 Message 表加载历史消息
                仅保留最近 K 轮（Layer 1 即时记忆）
                超出预算时进一步裁剪
                        │
                        ▼
              ③ PhaseEngine.evaluate()
                处理斜线命令（/next, /back 等）
                检测需求变更回溯信号
                        │
                  ┌─────┴─────┐
                  │ 需要跳转?  │
                  └─────┬─────┘
                  是 │   │ 否
                     ▼   ▼
              advance_phase()  保持当前阶段
                （仅斜线命令和需求变更回溯触发；
                  退出条件满足时由 AI 在对话中提示用户
                  点击导航按钮手动切换）
                        │
                        ▼
              ④ PromptBuilder.build()
                Layer1~6 拼装 System Prompt
                含 [MEMORY_SUMMARY]（Layer 3）← 记忆机制
                        │
                        ▼
              ⑤ ai_service.chat_completion()
                发送 [system + history(K轮) + user] 给 AI Provider
                        │
                        ▼
              ⑥ KnowledgeExtractor.extract()
                解析 AI 回复中的结构化标记
                        │
                        ▼
              ⑦ ContextManager.merge()
                增量合并到 AgentContext
                        │
                        ▼
              ⑧ ToolDispatcher.dispatch()
                执行 AI 请求的工具调用（如有）
                        │
                        ▼
              ⑨ PhaseDocumentRenderer.render()
                从 AgentContext 渲染当前阶段文档
                （纯模板，无 AI 调用）
                        │
                        ▼
              ⑩ PhaseDocumentPersistence.save()
                将阶段文档 Markdown 保存到"我的项目"
                （覆盖写，无额外 AI 调用）
                        │
                        ▼
              ⑪ 持久化 AgentContext + PhaseDocument
                 + 追加本轮 user/assistant 消息到 Message 表
                        │
                        ▼
              ⑫ MemoryManager.maybe_compress()（异步）← 记忆机制
                 若满足压缩条件，后台调用 AI 生成滚动摘要
                 更新 ctx.conversation_summary（下轮生效）
                        │
                        ▼
              ⑬ 返回响应给前端
                { reply, phase, suggestions,
                  phase_document }
```

---

## 12. API 接口设计（Agent 层）

### 12.1 Agent 对话接口

```
POST /api/v1/agent/chat
```

**请求体：**
```json
{
  "session_id": "uuid",           // 必填，前端维护
  "project_id": "uuid",           // 可选，关联项目
  "message": "我们在做一个电商平台...",
  "provider": "openai"            // 可选，覆盖默认 Provider
}
```

**响应体：**
```json
{
  "reply": "听起来很棒！能告诉我这个平台主要服务哪些用户群体吗？",
  "session_id": "uuid",
  "phase": "REQUIREMENT",
  "phase_label": "需求收集",
  "progress": 0.35,               // 0~1 整体进度估算
  "suggestions": [                // 快捷回复建议（可选）
    "主要服务 B2C 消费者",
    "同时服务 B 端商家",
    "跳过，直接进入领域建模"
  ],
  "extracted_concepts": [         // 本轮新提取的概念
    { "name": "商品", "type": "ENTITY", "confidence": 0.85 }
  ],
  "requirement_changes": [],      // 本轮记录的需求变更
  "phase_document": {             // 当前阶段文档（每轮更新，同步保存到项目）
    "phase": "REQUIREMENT",
    "title": "业务需求草稿",
    "content": "# 业务需求草稿\n\n...",
    "rendered_at": "2024-01-01T10:30:00Z",
    "turn_count": 5
  }
}
```

### 12.2 Agent 上下文查询接口

```
GET /api/v1/agent/context/{session_id}
```

返回当前 `AgentContext` 摘要，供前端渲染进度和已提取概念。

### 12.3 需求变更历史接口

```
GET /api/v1/agent/requirement-changes/{session_id}
```

**响应体：**
```json
{
  "session_id": "uuid",
  "changes": [
    {
      "change_id": "uuid",
      "change_type": "ADD",
      "description": "新增「积分兑换」业务场景",
      "changed_at": "2024-01-02T10:00:00Z",
      "affected_phases": ["REQUIREMENT", "DOMAIN_EXPLORE"]
    }
  ]
}
```

### 12.4 阶段文档查询接口

```
GET /api/v1/agent/phase-document/{session_id}/{phase}
```

`phase` 取值：`ICEBREAK` | `REQUIREMENT` | `DOMAIN_EXPLORE` | `MODEL_DESIGN` | `REVIEW_REFINE`

**响应体：**
```json
{
  "session_id": "uuid",
  "phase": "DOMAIN_EXPLORE",
  "title": "领域概念词汇表",
  "content": "# 领域概念词汇表\n\n...",
  "rendered_at": "2024-01-01T11:00:00Z",
  "turn_count": 8
}
```

省略 `phase` 参数时返回当前阶段文档（与 chat 响应中的 `phase_document` 相同）。

---

## 13. 前端交互设计

### 13.1 Chat 页面整体布局

Chat 页面采用**双栏布局**：左侧为对话区（60%宽度），右侧为**阶段文档面板**（40%宽度）。

```
┌──────────────────────────────────────────────────────────────────┐
│  [P1 破冰] [P2 需求★] [P3 探索] [P4 模型] [P5 审阅]              │  ← 阶段标签栏
├─────────────────────────────┬────────────────────────────────────┤
│                             │  # 业务需求草稿                      │
│  ┌─────────────────────┐    │  **项目**: 电商平台 · P2 · 轮次 #5   │
│  │   AI 消息气泡        │    │  更新时间: 2024-01-01 10:30         │
│  └─────────────────────┘    │                                    │
│                             │  ## 核心业务场景（3 / 3）            │
│  ┌─────────────────────┐    │  | S001 | 用户注册 | ✅ |            │
│  │   用户消息气泡        │    │  | S002 | 商品浏览 | ✅ |            │
│  └─────────────────────┘    │  | S003 | 订单支付 | ⚠️ v2 |         │
│                             │                                    │
│  [快捷回复建议]              │  ## 待澄清（1）                      │
│  [输入框]  [发送]            │  - Q001: 支付失败后如何处理？         │
└─────────────────────────────┴────────────────────────────────────┘
```

- **标签栏**：显示全部 5 个阶段标签，当前阶段用「★」标注并高亮；已完成阶段用「✓」标注。
- **默认选中**：始终展示当前阶段文档；阶段跳转时自动切换标签。
- **用户切换**：点击任意阶段标签，调用 `GET /api/v1/agent/phase-document/{session}/{phase}` 异步加载该阶段文档。
- **每轮自动刷新**：对话发送后，右侧面板使用 chat 响应体中的 `phase_document` 无闪烁替换内容（无额外请求）；同时文档已自动保存到"我的项目"中。
- **渲染格式**：Markdown 渲染（支持表格、代码块、树形结构）。

### 13.2 Chat 页面增强要点

- **阶段进度条** — 顶部显示当前所处阶段（P1~P5）及整体进度。
- **概念面板** — 侧边栏实时展示已识别的领域概念，支持用户编辑。
- **快捷建议** — 对话框下方展示 `suggestions` 中的快捷回复按钮。
- **项目文档入口** — 在阶段文档面板提供「在"我的项目"中查看」链接，方便用户跳转。
- **需求变更时间轴** — 侧边栏可展开查看需求变更历史，了解每次变更影响了哪些阶段。
- **阶段手动控制** — 允许用户通过 `/next`、`/back` 等斜线命令手动控制阶段。

### 13.3 斜线命令

| 命令 | 功能 |
|------|------|
| `/next` | 强制进入下一阶段 |
| `/back` | 回退到上一阶段 |
| `/model` | 跳转到模型设计阶段 |
| `/status` | 显示当前上下文摘要 |
| `/reset` | 重置当前会话 |
| `/change` | 主动声明需求变更，触发 `record_requirement_change` 工具 |
| `/changes` | 查看本次对话的需求变更历史 |
| `/techstack` | 随时重新发起技术栈偏好确认流程 |

---

## 14. 数据库模型变更（概要）

在现有 `Conversation` / `Message` 模型基础上新增或扩展：

```
Conversation
├── ... (现有字段)
├── agent_phase: str              # 新增：当前阶段标识
├── agent_phase_before_change: str | None  # 新增：需求变更回溯前的阶段
└── agent_context: JSONB          # 新增：序列化的 AgentContext

DomainConcept                     # 新增表
├── id: UUID
├── project_id: UUID (FK)
├── conversation_id: UUID (FK)
├── name: str
├── concept_type: str
├── description: str
└── confidence: float

BusinessScenario                  # 新增表
├── id: UUID
├── project_id: UUID (FK)
├── conversation_id: UUID (FK)
├── name: str
├── description: str
├── status: str                   # ACTIVE | MODIFIED | DEPRECATED
└── version: int                  # 每次变更时递增

RequirementChange                 # 新增表，记录需求变更历史
├── id: UUID
├── conversation_id: UUID (FK)
├── project_id: UUID (FK)
├── change_type: str              # ADD | MODIFY | DEPRECATE
├── target_id: str | None         # 被变更的场景/概念 ID
├── description: str
├── affected_phases: JSONB        # List[str]，受影响的阶段列表
└── changed_at: datetime

PhaseDocument                     # 新增表，每轮对话后写入/覆盖（同时关联到 Project）
├── id: UUID
├── conversation_id: UUID (FK)
├── project_id: UUID (FK)         # 新增：关联到"我的项目"
├── phase: str                    # ICEBREAK | REQUIREMENT | DOMAIN_EXPLORE | MODEL_DESIGN | REVIEW_REFINE
├── content: str                  # Markdown 渲染结果（保存为项目文档）
├── rendered_at: datetime         # 最后渲染时间
└── turn_count: int               # 对应的对话轮次序号
```

---

## 15. 实现路线图

| 里程碑 | 内容 | 优先级 |
|--------|------|--------|
| M1 | System Prompt 分层 + 阶段静态切换 | 🔴 高 |
| M2 | AgentContext 设计与 Redis 持久化 | 🔴 高 |
| M3 | PhaseDocumentRenderer 五阶段模板 + PhaseDocument 持久化 | 🔴 高 |
| M4 | **PhaseDocumentPersistence：每轮自动保存阶段文档到"我的项目"** | 🔴 高 |
| M5 | 前端双栏布局：对话区 + 阶段文档面板（五阶段标签 + 自动刷新）+ 「在我的项目中查看」入口 | 🔴 高 |
| M6 | KnowledgeExtractor（基于 XML 标记解析） | 🟡 中 |
| M7 | **MemoryManager：三层记忆模型 + 滚动摘要压缩（见 §4.4）** | 🟡 中 |
| M8 | ToolDispatcher + Function Calling 集成 | 🟡 中 |
| M9 | 需求变更管理：record_requirement_change 工具 + 受影响阶段文档重渲染保存 | 🟡 中 |
| M10 | 需求变更冲突检测（概念重复、规则矛盾） | 🟡 中 |
| M11 | **技术栈确认：confirm_tech_stack 工具 + TechStackPreferences 存储（见 §17）** | 🟡 中 |
| M12 | 前端阶段进度条 + 概念面板 + 快捷建议 | 🟢 低 |
| M13 | 前端需求变更时间轴 | 🟢 低 |
| M14 | 斜线命令解析（含 `/change`, `/changes`, `/techstack`） | 🟢 低 |
| M15 | `validate_ddd_model` 工具（DDD 合规检查） | 🟢 低 |

---

## 16. 设计决策记录（ADR）

### ADR-001：为何不使用 LangChain / AutoGen 等 Agent 框架？

**决策**：自行实现轻量 Agent 内核，不引入重型 Agent 框架。

**原因**：
1. Talk2DDD 的 Agent 流程高度业务定制，框架的通用抽象反而增加复杂度。
2. 减少依赖，降低部署和版本兼容风险。
3. 现有 `ai_service.py` 已良好封装 Provider 切换，Agent 层只需在其上构建。

**代价**：需自行维护 PromptBuilder、KnowledgeExtractor 等组件。

---

### ADR-002：上下文压缩策略

**问题**：对话轮次增多后，注入的历史上下文会超出 Token 限制，AI 开始"遗忘"早期信息（如项目名称、核心需求）。

**决策**：采用三层记忆模型 + 滚动摘要策略（详见 §4.4）：
1. **即时记忆**：保留最近 K 轮完整对话原文（默认 K=10）直接传给 AI。
2. **滚动摘要**：第 1～N-K 轮的旧对话由 AI 压缩为 200~400 字的结构化摘要，注入为 System Prompt 的 `[MEMORY_SUMMARY]` 区块。
3. **结构化长期记忆**：`DomainKnowledge` 始终以结构化 JSON 形式存储，而非原始对话文本，天然压缩，不受对话长度影响。

**选择此方案而非其他方案的原因**：

| 方案 | 优点 | 缺点 | 结论 |
|------|------|------|------|
| 全量历史（无压缩） | 实现最简单 | Token 超限，费用失控 | ❌ 不可持续 |
| 固定窗口（仅保留最近 K 轮） | 简单，Token 可控 | 丢失早期关键信息（如项目名） | ⚠️ 短期可用，有风险 |
| 滚动摘要 | 保留核心信息，Token 可控 | 需额外 AI 调用，摘要有信息损失 | ✅ 最优平衡 |
| 外部向量检索（RAG） | 精准检索任意历史 | 架构复杂，引入向量 DB 依赖 | 🔮 未来演进 |

**代价**：
- 需维护 `MemoryManager` 组件和摘要 AI 调用逻辑。
- 摘要生成引入额外延迟，通过**异步后台执行**缓解（下一轮才生效）。
- 摘要本身有信息损失风险，通过`DomainKnowledge` 结构化备份核心信息。

---

### ADR-003：如何处理不支持 Function Calling 的 Provider？

**决策**：降级为"XML 标记模式"。

- 在 System Prompt 中指示 AI 在回复中嵌入 XML 标记（见第 6.2 节）。
- `KnowledgeExtractor` 用正则解析这些标记，效果次于 Function Calling 但兼容所有 Provider。
- MiniMax / 旧版 DeepSeek 默认使用 XML 标记模式；OpenAI GPT-4 / DeepSeek-V3 使用 Function Calling 模式。

---

### ADR-004：需求变更的原地更新 vs. 快照追加策略

**问题**：当用户修改已有需求时，是直接覆盖旧数据（原地更新），还是保留历史快照（追加新版本）？

**决策**：采用**混合策略**：

1. **`BusinessScenario` 原地更新 + `version` 递增**  
   - 活跃场景的 `description` 和 `status` 直接更新，同时 `version` 自增。  
   - 原因：减少查询复杂度，当前状态始终可通过主键读取。

2. **`RequirementChange` 作为完整审计日志**  
   - 每次 ADD / MODIFY / DEPRECATE 都写入一条不可变的 `RequirementChange` 记录。  
   - 原因：保留完整变更轨迹，支持"撤销最近一次变更"和"查看变更历史"功能。

3. **`RequirementChange` 记录受影响阶段**  
   - 变更触发后，`affected_phases` 列出所有需要重渲染的阶段；`PhaseDocumentRenderer` 对这些阶段重新渲染并保存到项目中。  
   - 原因：不需要维护文档版本状态机（STALE/SUPERSEDED），每次覆盖写最新版本即可。

**代价**：需要在 `ContextManager.merge()` 中实现"变更意图 → `BusinessScenario` 查找 → 更新/新增 → 写 `RequirementChange`"的事务逻辑。

---

### ADR-005：阶段文档渲染策略——模板渲染 vs. AI 生成

**问题**：阶段文档每轮都要更新，是用 AI 重新生成（高质量但慢），还是用模板引擎渲染（快但格式固定）？

**决策**：**阶段文档（PhaseDocument）全部采用模板渲染，渲染结果直接保存为项目文档。不另设单独的 AI 文档生成阶段。**

| 维度 | PhaseDocument（模板渲染，自动保存到项目） |
|------|----------------------------------------|
| 触发时机 | 每轮对话自动触发 |
| 延迟 | < 5ms（纯模板） |
| 内容质量 | 结构化展示，无润色 |
| 用途 | 实时了解当前状态 + 项目可交付文档 |
| 更新策略 | 覆盖写（仅保留最新一条） |

**原因**：
1. 每轮对话都触发 AI 生成会导致响应时间过长（用户需等待 10~30 秒），破坏对话体验。
2. 独立的"文档生成"阶段（P5）需要用户手动点击多个按钮，且因 AI 调用时间较长容易超时失败，用户体验差。
3. 阶段文档在对话过程中已积累了充分的结构化信息，模板渲染足以生成高质量的项目文档；用户无需等待，文档随时可在"我的项目"中查阅。
4. 去掉独立的文档生成阶段后，流程更简洁：P1→P2→P3→P4→P5，每个阶段都有对应文档自动保存。

**代价**：模板维护成本；阶段文档无法包含 AI 的叙述性润色（仅反映已提取的结构化数据）。对于需要更高质量输出的场景，可在 P5 审阅完善阶段由用户通过对话请求 AI 对特定内容进行二次润色。

---

### ADR-006：记忆压缩的执行时机——同步 vs. 异步

**问题**：记忆压缩（调用 AI 生成摘要）需要一次额外的 AI 调用（约 2~5 秒），执行时机有两个选择：在主对话响应前（同步）或主对话响应后（异步后台）。

**决策**：**摘要压缩异步执行，当前轮次返回前不等待，下一轮次开始生效。**

**原因**：
1. 对话延迟是用户体验的核心指标；同步执行会使每隔 `SUMMARY_REFRESH_INTERVAL` 轮出现一次明显的响应延迟高峰。
2. 摘要的"一轮延迟生效"对用户几乎无感知：压缩发生在第 N 轮之后，第 N+1 轮起即可使用新摘要；第 N 轮本身仍有 `[CONTEXT_BLOCK]` 结构化记忆兜底。
3. 若异步压缩失败（如 AI 超时），静默降级——继续使用上一次成功的摘要或纯结构化记忆，不影响功能。

**代价**：
- 在极少情况下（高并发同一 session），异步摘要可能发生竞态写入；通过 `summary_last_updated_turn` 字段做乐观检查，只保留最新轮次的摘要。
- 第一次压缩前的若干轮次（第 K+1～K+M 轮）无摘要保护；`DomainKnowledge` 结构化记忆作为兜底，保证核心信息不丢失。

---

## 17. 技术栈确认机制（TechStackConfirmation）

### 17.1 设计动机

在 DDD 的实践中，技术架构与领域模型密切相关——限界上下文的划分方式、聚合的事务边界、领域事件的发布机制，都与所选技术栈强相关。如果 AI 在生成 `TECH_ARCHITECTURE` 文档时不了解用户的技术背景，可能产生以下问题：

1. **推荐用户不熟悉的技术** — 例如向一个纯 Python 团队推荐 Spring Boot 微服务架构，导致文档可落地性极低。
2. **忽略已有技术约束** — 企业内部可能有既定的技术选型（如数据库必须用 Oracle），AI 不了解会给出冲突建议。
3. **过度推荐而非务实** — AI 倾向于推荐"最佳实践"组合，但用户需要的是"自己能驾驭的"技术方案。

> **核心目标**：在 P4 模型设计阶段完成后，通过自然对话的方式采集用户的技术栈偏好，让领域模型草稿（P4 阶段文档）中的技术栈部分真正贴合用户团队的能力边界，并在 P4 文档保存到"我的项目"时包含完整的技术栈信息。

---

### 17.2 确认时机与流程

技术栈确认嵌入在 **P4 阶段**，在领域模型草稿经用户确认后自然触发。

```
用户确认领域模型草稿
        │
        ▼
① Agent 自然过渡引出技术栈话题
  "模型已经清晰了！在进入审阅阶段之前，
   我想了解一下你们团队的技术偏好，
   这样领域模型草稿中的技术架构建议会更贴合实际情况。"
        │
        ▼
② 分类逐步询问（每次只问一个大类，避免信息轰炸）
  前端 → 后端 → 数据库 → 基础设施（可选） → 消息队列（可选）
        │
        ▼
③ 用户回应（三种模式）
  ┌─────────────────────────────────────────────────┐
  │ 模式 A：明确指定                                   │
  │  "前端用 React，后端用 Python FastAPI，            │
  │   数据库用 PostgreSQL"                             │
  ├─────────────────────────────────────────────────┤
  │ 模式 B：部分指定                                   │
  │  "后端肯定用 Java，前端和数据库你帮我推荐"            │
  ├─────────────────────────────────────────────────┤
  │ 模式 C：完全跳过                                   │
  │  "不懂技术，你帮我选" / "/techstack skip"          │
  └─────────────────────────────────────────────────┘
        │
        ▼
④ 调用 confirm_tech_stack 工具
  - 模式 A/B：记录用户指定的项，AI 填充未指定的推荐项
  - 模式 C：skipped=true，AI 根据领域模型全自动推荐
        │
        ▼
⑤ Agent 向用户展示确认摘要
  "好的，已记录你们的技术偏好：
   • 前端：React（你指定）
   • 后端：FastAPI / Python（你指定）
   • 数据库：PostgreSQL（你指定）
   • 消息队列：Redis Streams（AI 推荐，适合你们的事件量级）
   如果有调整，随时告诉我，或使用 /techstack 重新设置。"
        │
        ▼
⑥ tech_stack_preferences.confirmed = true
   P4 阶段文档重新渲染（含技术栈章节）并保存到项目中
   PhaseEngine 可推进到 P5（审阅完善）
```

---

### 17.3 对话示例

#### 场景 A：用户有明确偏好

```
AI:   模型已经很清晰了！在出技术架构方案前，想问问你们团队
      平时用什么技术栈？前端有偏好吗？

用户: 前端我们用 Vue3，后端 Java + Spring Boot，数据库
      用的是 MySQL，还有 Redis 做缓存。

AI:   了解！基础设施和部署方面有约束吗？比如是否要上 K8s，
      或者有指定的云平台？

用户: 我们用阿里云，但 K8s 还没有，现在都是 ECS 部署。

AI:   好的，已记录你们的技术偏好：
      • 前端：Vue 3
      • 后端：Java / Spring Boot
      • 数据库：MySQL + Redis（缓存）
      • 基础设施：阿里云 ECS
      接下来生成技术架构文档时，我会基于这个栈给出贴合
      你们实际情况的方案。需要修改可随时说，或用 /techstack。
```

#### 场景 B：用户希望 AI 推荐

```
AI:   模型已经很清晰了！你们团队的技术栈有没有特别的偏好
      或约束？没有的话我可以根据你们的领域复杂度来推荐。

用户: 我们是个小团队，2~3 个全栈，你帮我选吧。

AI:   好的，根据你们的领域规模（中等复杂度，3 个限界上下文），
      我会推荐一个适合小团队快速落地的技术栈，
      在生成 TECH_ARCHITECTURE 文档时一并说明推荐理由。
```

---

### 17.4 技术栈预设选项（前端 Quick Picks）

为了降低用户输入负担，在前端展示技术栈询问时可提供快捷选择按钮：

| 分类 | 快捷选项（示例） |
|------|----------------|
| 前端 | React · Vue · Angular · Next.js · 小程序 · 无前端 |
| 后端 | Java/Spring Boot · Python/FastAPI · Python/Django · Node.js · Go · .NET |
| 数据库 | PostgreSQL · MySQL · MongoDB · Oracle · SQLite · Redis |
| 基础设施 | Docker · K8s · 阿里云 · AWS · GCP · 裸金属 |
| 消息队列 | Kafka · RabbitMQ · Redis Streams · 不需要 |

> 用户可直接点击快捷按钮，也可以自由输入；两种方式均通过 AI 解析后调用 `confirm_tech_stack` 工具落库。

---

### 17.5 技术栈信息如何影响阶段文档

技术栈偏好确认后，写入 `AgentContext.tech_stack_preferences`，并在 P4 阶段文档（领域模型草稿）中以独立章节展示。下次对话时 `PhaseDocumentRenderer` 自动将技术栈信息渲染进 P4 文档并保存到项目中。

`PromptBuilder` 在构建 P4 阶段 System Prompt 时也会注入技术栈上下文块，供 AI 在讨论模型设计时参考：

```
[TECH_STACK_BLOCK]
用户确认的技术栈偏好（{confirmed_or_ai_recommended}）：
  • 前端：{frontend_summary}
  • 后端：{backend_summary}
  • 数据库：{database_summary}
  • 基础设施：{infrastructure_summary}
  • 消息队列：{messaging_summary}

约束说明：
  - 标注 "用户指定" 的项必须采用，不可替换。
  - 标注 "AI 推荐" 的项若有更优方案可建议，但需在对话中说明。
  - 用户熟悉程度为 LEARNING 或 UNFAMILIAR 的技术需补充学习建议或替代方案。
[/TECH_STACK_BLOCK]
```

**渲染策略**：

| `skipped` | `confirmed` | P4 文档技术栈章节内容 |
|-----------|-------------|---------------------|
| `false` | `true` | 展示用户指定的技术栈，AI 对未指定的分类给出推荐 |
| `true` | `true` | 展示 AI 根据领域模型全自动推荐的技术栈，并说明推荐理由 |
| `false` | `false` | 技术栈尚未采集，该章节显示"待补充"提示 |

---

### 17.6 技术栈变更处理

用户在 P4/P5 阶段可通过 `/techstack` 命令或直接在对话中说明重新调整技术栈。变更处理方式：

1. Agent 更新 `tech_stack_preferences` 中对应分类的 `TechChoice` 列表。
2. P4 阶段文档重新渲染（包含更新后的技术栈章节）并保存到项目中。

```
用户: 我们决定把数据库换成 PostgreSQL，不用 MySQL 了。

AI:   已更新数据库偏好为 PostgreSQL。
      P4 领域模型草稿已更新技术栈部分并保存到项目中。
      可在「我的项目」中查看最新文档。
```

---

### 17.7 前端 UI 扩展

在 Chat 页面的 **P4 阶段**，当 Agent 发起技术栈询问时，前端可额外展示：

- **技术栈快捷选择卡片** — 在对话输入框上方弹出分类按钮组，用户点击即可快速选择。
- **已选技术栈摘要栏** — 在阶段文档面板（右侧）的 P4 文档中追加"技术栈偏好"小节，实时展示已确认的技术选择（与领域模型草稿并排）。
- **`/techstack` 快捷入口** — 在 P5 阶段的阶段文档面板底部提供"修改技术栈偏好"链接，点击触发 `/techstack` 命令。

---

### ADR-007：技术栈确认——强制 vs. 可选

**问题**：技术栈确认是否应该作为 P4 的强制退出条件，还是可选步骤？

**决策**：**可选，但默认引导**。

| 方案 | 说明 | 结论 |
|------|------|------|
| 强制确认 | 不完成技术栈确认就无法进入 P5 | ❌ 增加用户摩擦；部分用户只需要领域模型，与技术栈无关 |
| 完全可选（不主动问） | 用户需要主动 `/techstack` 才能触发 | ❌ 大多数用户不知道有此功能 |
| 默认引导 + 可跳过 | 模型确认后 Agent 主动发起，但用户可一句话跳过 | ✅ 最优平衡 |

**实现方式**：
- 若用户明确表示"跳过"或"你帮我选"，立即调用 `confirm_tech_stack(skipped=true)`，不再追问。
- 若用户未回应技术栈相关问题而直接切换到下一阶段，Agent 同样触发 `confirm_tech_stack(skipped=true)` 并告知用户可通过 `/techstack` 补充。
- P4 的退出条件不强依赖技术栈确认：只要领域模型草稿经用户确认，即可推进 P5。

---

## 18. 阶段手动导航机制（Phase Navigation Buttons）

### 18.1 需求背景与设计目标

现有设计通过斜线命令（`/next`、`/back`）支持阶段手动跳转，但这种方式对普通用户不够直观——用户需要知道命令存在，并手动输入。

本节设计两个**显式导航按钮**（「⬅ 上一阶段」和「下一阶段 ➡」），让用户无需记忆命令即可自由切换阶段，同时：

1. **右侧阶段文档随之切换** — 按钮触发阶段变更后，右侧文档面板立即展示新阶段的文档内容。
2. **对话中自动发出阶段通知** — 聊天区域插入一条样式独特的「系统通知」气泡，说明已进入哪个新阶段。
3. **AI 切换上下文并给出阶段引导** — AI Agent 自动感知新阶段，向用户讲解本阶段目标和首要行动，不再延续旧阶段的讨论方向。

---

### 18.2 整体交互流程

```
用户点击「下一阶段」或「上一阶段」按钮
        │
        ▼
① 前端禁用按钮（防重复点击），显示 loading 状态
        │
        ▼
② POST /api/v1/agent/switch-phase
   { session_id, direction: "next" | "back", provider? }
        │
        ▼
③ 后端：PhaseEngine 计算新阶段
   若已是第一 / 最后阶段，返回 400（前端提前禁用可避免此情况）
        │
        ▼
④ 后端：advance_phase() 写入 PhaseTransition 记录
        │
        ▼
⑤ 后端：以新阶段系统提示 + 专用 phase_switch_trigger 指令
   调用 AI，生成阶段引导消息（约 100~200 字）
        │
        ▼
⑥ 后端：渲染新阶段文档（PhaseDocumentRenderer，无 AI 调用）
        │
        ▼
⑦ 后端：将「切换触发」和「AI 引导消息」追加到 Message 表
   （两条记录：role=system 触发消息 + role=assistant AI 引导）
        │
        ▼
⑧ 后端返回响应（与 /chat 响应结构相同，含 reply、phase、
   phase_label、progress、suggestions、phase_document）
        │
        ▼
⑨ 前端：在聊天区注入「阶段切换」系统通知气泡（蓝色横幅）
   + AI 引导消息气泡（assistant 气泡）
        │
        ▼
⑩ 前端：更新阶段标签栏高亮、进度条、右侧文档面板
   恢复按钮可点击状态
```

---

### 18.3 UI 组件设计

#### 18.3.1 按钮位置

按钮位于**输入区上方、建议词条行的右侧**，与发送按钮同行（对话框右上角区域）：

```
┌──────────────────────────────────────────────────────────┐
│  [建议词 A] [建议词 B] [建议词 C]      ← 上一阶段  下一阶段 →  │
│  ┌─────────────────────────────────┐  ┌──────┐           │
│  │ 输入消息，按 Enter 发送…          │  │ 发送 │           │
│  └─────────────────────────────────┘  └──────┘           │
└──────────────────────────────────────────────────────────┘
```

按钮也可出现在阶段导航标签栏的两端：

```
[← 上一阶段]  [P1 破冰] [P2 需求★] [P3 探索] …  [下一阶段 →]   ████ 35%
```

两处都展示可覆盖更多操作习惯；实现时二选一即可，推荐**放在阶段导航标签栏两端**（视觉关联更强）。

#### 18.3.2 按钮样式与状态

| 状态 | 视觉样式 | 说明 |
|------|---------|------|
| 正常 | 灰底圆角按钮，有箭头图标 | 可点击 |
| 禁用（首阶段/末阶段） | 半透明 + cursor-not-allowed | 「上一阶段」在 P1 时禁用；「下一阶段」在 P5 时禁用 |
| 加载中 | 旋转 spinner 替代箭头，按钮禁用 | 等待 API 响应期间 |
| Hover | 浅蓝色背景 | 提示可交互 |

#### 18.3.3 阶段切换通知气泡

在聊天历史中插入一种特殊样式的「系统通知」消息，区别于普通的用户/助手气泡：

```
┌─────────────────────────────────────────────────────────┐
│  ────────────── 🔄 已进入「领域探索」阶段（P3/6）─────────── │
└─────────────────────────────────────────────────────────┘
```

- **样式**：水平居中，浅蓝色背景横幅，小号字体，无圆角气泡外框。
- **内容**：「已进入「{阶段名}」阶段（P{N}/6）」。
- **在 Message 表中不持久化**（`role=system` 仅前端本地渲染，不写入历史）；或写入一条 `role=system` 消息以便会话恢复时重现，实现时可按需选择。

---

### 18.4 新增 API 端点

#### 18.4.1 端点定义

```
POST /api/v1/agent/switch-phase
```

**请求体：**
```json
{
  "session_id": "uuid",           // 必填
  "direction": "next",            // 必填："next" | "back"
  "provider": "openai"            // 可选，覆盖默认 Provider
}
```

**响应体**（与 `/chat` 结构相同，额外字段 `phase_changed: true`）：
```json
{
  "reply": "欢迎进入「领域探索」阶段！…（AI 引导消息）",
  "session_id": "uuid",
  "phase": "DOMAIN_EXPLORE",
  "phase_label": "领域探索",
  "progress": 0.4,
  "suggestions": [
    "这些概念中哪些是核心业务对象？",
    "有哪些重要的业务规则？",
    "输入 /next 进入模型设计阶段"
  ],
  "extracted_concepts": [],
  "requirement_changes": [],
  "phase_document": {
    "phase": "DOMAIN_EXPLORE",
    "title": "领域概念词汇表",
    "content": "# 领域概念词汇表\n\n...",
    "rendered_at": "2024-01-01T11:00:00Z",
    "turn_count": 8
  },
  "phase_changed": true           // 标识本次响应是阶段切换触发的
}
```

**错误响应：**

| HTTP 状态 | 场景 |
|-----------|------|
| 400 | `direction` 非法，或已在首/末阶段无法继续跳转 |
| 502 | AI Provider 调用失败 |
| 404 | session_id 不存在（尚未初始化对话） |

#### 18.4.2 Schema 扩展

在 `AgentChatResponse` Schema 中新增可选字段 `phase_changed: bool = False`，使前端能区分普通聊天回复与阶段切换回复（用于触发通知气泡渲染）。

```python
# app/schemas/agent.py 中扩展
class AgentChatResponse(BaseModel):
    ...
    phase_changed: bool = False   # 新增：本次响应由阶段切换触发
```

---

### 18.5 后端处理流程（AgentCore 扩展）

在 `AgentCore` 中新增 `switch_phase()` 方法：

```python
async def switch_phase(
    self,
    session_id: str,
    direction: str,          # "next" | "back"
    db: AsyncSession,
    provider: Optional[str] = None,
) -> AgentResponse:
    """Manually advance or rewind one phase, then generate a phase intro message."""

    # 1. Load context
    ctx = await self._context_manager.load(session_id, db)

    # 2. Compute target phase
    if direction == "next":
        new_phase = self._phase_engine._next_phase(ctx)
    elif direction == "back":
        new_phase = self._phase_engine._prev_phase(ctx)
    else:
        raise ValueError(f"Invalid direction: {direction}")

    if new_phase is None:
        raise ValueError("Already at the boundary phase; cannot navigate further.")

    # 3. Apply transition
    reason = f"manual-switch ({direction}): {ctx.current_phase.value} → {new_phase.value}"
    self._phase_engine.advance_phase(ctx, new_phase, reason)

    # 4. Build phase-switch system prompt
    #    Adds PHASE_SWITCH_TRIGGER block to tell the AI to generate a welcoming intro
    summary_block = self._memory_manager.get_summary_block(ctx)
    system_prompt = self._prompt_builder.build(
        ctx,
        memory_summary_block=summary_block,
        phase_switch_trigger=True,          # ← 新参数
    )

    # 5. Call AI with trigger message
    history = await self._memory_manager.get_messages_for_ai(ctx, db)
    trigger_msg = _build_phase_switch_trigger(ctx.current_phase)
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history)
    messages.append({"role": "user", "content": trigger_msg})
    ai_reply = await chat_completion(messages=messages, provider=provider)

    # 6. Extract knowledge (lightweight; phase switch rarely yields new concepts)
    self._knowledge_extractor.extract(ai_reply, ctx)

    # 7. Increment turn counter
    ctx.turn_count += 1

    # 8. Render phase document for new phase
    phase_doc_content = self._doc_renderer.render(ctx)
    phase_doc_title = self._doc_renderer.get_title(ctx)
    phase_doc = PhaseDocumentResult(
        phase=ctx.current_phase.value,
        title=phase_doc_title,
        content=phase_doc_content,
        rendered_at=datetime.now(timezone.utc),
        turn_count=ctx.turn_count,
    )

    # 9. Persist context + messages
    await self._context_manager.save(ctx, db)
    # Persist the trigger message (role=system) and AI reply (role=assistant)
    await self._context_manager.append_messages(
        session_id, trigger_msg, ai_reply, db, user_role="system"
    )

    # 10. Async memory compression
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
        phase_changed=True,
    )
```

辅助函数 `_build_phase_switch_trigger()` 生成触发消息（此消息只传给 AI，不展示给用户）：

```python
_PHASE_SWITCH_TRIGGERS: dict[Phase, str] = {
    Phase.ICEBREAK:       "[系统] 用户手动切换回「破冰引入」阶段（P1）。请简短告知用户当前处于哪个阶段，说明此阶段的目标，并提出第一个引导问题。",
    Phase.REQUIREMENT:    "[系统] 用户手动进入「需求收集」阶段（P2）。请简短告知用户此阶段目标（梳理业务场景），总结已收集到的场景数量，并引导用户继续补充或澄清下一个场景。",
    Phase.DOMAIN_EXPLORE: "[系统] 用户手动进入「领域探索」阶段（P3）。请简短告知此阶段目标（识别领域概念、建立通用语言），总结已识别的概念，并提出第一个领域探索问题。",
    Phase.MODEL_DESIGN:   "[系统] 用户手动进入「模型设计」阶段（P4）。请简短告知此阶段目标（设计聚合、划定限界上下文），总结已有概念，并提出第一个聚合边界问题。",
    Phase.REVIEW_REFINE:  "[系统] 用户手动进入「审阅完善」阶段（P5）。请简短告知此阶段目标（审阅各阶段文档、收集反馈），告知用户可以在"我的项目"中查阅最新文档，并提出修改意见。",
}

def _build_phase_switch_trigger(phase: Phase) -> str:
    return _PHASE_SWITCH_TRIGGERS.get(phase, f"[系统] 用户切换到阶段 {phase.value}。")
```

---

### 18.6 PromptBuilder 扩展（phase_switch_trigger 参数）

在 `PromptBuilder.build()` 中新增 `phase_switch_trigger: bool = False` 参数。当为 `True` 时，在系统提示中追加一个 `[PHASE_SWITCH]` 指令块，明确告知 AI 这是一次阶段切换而非普通对话：

```python
_PHASE_SWITCH_INSTRUCTION = """【阶段切换模式】
本轮对话由用户手动切换阶段触发，而非普通对话输入。
请生成一段简短友好的「阶段引导消息」（100~200 字），内容包括：
1. 确认已进入的新阶段名称和总阶段序号（如「欢迎进入第 3 阶段：领域探索」）
2. 用一句话说明本阶段的核心目标
3. 简要总结上一阶段已完成的关键成果（如"已收集 4 个业务场景"）
4. 提出 1~2 个本阶段的首要行动项或引导问题
语气积极、简洁，避免重复已知信息，不要输出任何 XML 标记。"""
```

`build()` 修改：

```python
def build(
    self,
    ctx: AgentContext,
    memory_summary_block: str = "",
    phase_switch_trigger: bool = False,   # ← 新参数
) -> str:
    layers = [
        _ROLE_DEFINITION,
        _PHASE_INSTRUCTIONS.get(ctx.current_phase, ""),
        memory_summary_block,
        self._build_context_block(ctx),
        _XML_EXTRACTION_FORMAT,
    ]
    if phase_switch_trigger:
        layers.append(_PHASE_SWITCH_INSTRUCTION)   # 追加到最后，优先级最高
    return "\n\n---\n\n".join(layer.strip() for layer in layers if layer.strip())
```

`[PHASE_SWITCH]` 指令放在所有层的末尾，使其在 AI 处理时具有最高的情境覆盖效果。

---

### 18.7 各阶段进入时的 AI 引导词模板

AI 的具体回复由 AI Provider 生成，但设计期望的输出结构如下：

| 进入阶段 | AI 引导消息结构示例 |
|---------|-------------------|
| P1 破冰引入 | "欢迎来到第 1 阶段：破冰引入！我的目标是帮你梳理项目背景。能先告诉我，你们正在做一个什么样的系统？主要解决什么业务问题？" |
| P2 需求收集 | "现在进入第 2 阶段：需求收集。目前已收集到 {N} 个业务场景，我们来继续梳理。接下来还有哪些核心业务流程想补充，或者需要深入讨论某个已有场景？" |
| P3 领域探索 | "进入第 3 阶段：领域探索。基于已有的 {N} 个业务场景，我们来提炼核心领域概念。「{概念示例}」这些词已经出现在你的描述中——它们是你们业务中的核心对象吗？能描述一下「{概念X}」在你们业务中的确切含义吗？" |
| P4 模型设计 | "进入第 4 阶段：模型设计。我们已经识别了 {N} 个领域概念，现在来讨论它们的边界关系。「{概念A}」和「{概念B}」在你们的业务中，是否总是作为一个整体一起变化？" |
| P5 审阅完善 | "进入第 5 阶段：审阅完善。各阶段文档已随对话自动保存到「我的项目」中，你可以随时查阅。如有需要修改的地方，直接告诉我（如「领域模型草稿中的聚合边界有误，应该…」），我会更新相应阶段文档并重新保存。" |

---

### 18.8 前端实现细节

#### 18.8.1 新增状态字段

```typescript
// 新增状态
const [phaseChanging, setPhaseChanging] = useState(false)
```

`phaseChanging` 为 `true` 时，导航按钮全部禁用（防重复点击），且与 `loading` 互斥（一次只能进行一种操作）。

#### 18.8.2 switchPhase 函数

```typescript
async function switchPhase(direction: 'next' | 'back') {
  if (phaseChanging || loading) return
  setPhaseChanging(true)
  setError(null)

  try {
    const res = await fetch(`${API_URL}/api/v1/agent/switch-phase`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
      body: JSON.stringify({ session_id: sessionId, direction, provider }),
    })

    if (!res.ok) {
      const data = await res.json().catch(() => ({}))
      throw new Error(data.detail ?? `HTTP ${res.status}`)
    }

    const data: AgentChatResponse & { phase_changed?: boolean } = await res.json()

    // 1. 插入「阶段切换」系统通知（本地，不写入 messages 持久化状态）
    const phaseLabel = data.phase_label ?? data.phase
    const systemNotice: Message = {
      role: 'system',           // 新增 'system' role（前端专用，不发给后端）
      content: `🔄 已切换至「${phaseLabel}」阶段`,
    }
    // 2. 插入 AI 引导消息
    const aiMsg: Message = { role: 'assistant', content: data.reply }
    setMessages((prev) => [...prev, systemNotice, aiMsg])

    // 3. 更新阶段状态
    setPhase(data.phase)
    setProgress(data.progress)
    setSuggestions(data.suggestions ?? [])
    if (data.tech_stack_preferences !== undefined) {
      setTechStackPreferences(data.tech_stack_preferences)
    }
    // 4. 更新阶段文档
    if (data.phase_document) {
      setPhaseDocument(data.phase_document)
      setShowPhaseDoc(true)
    }
  } catch (err: unknown) {
    setError(err instanceof Error ? err.message : '阶段切换失败，请重试')
  } finally {
    setPhaseChanging(false)
  }
}
```

#### 18.8.3 系统通知气泡渲染

在消息列表渲染中增加对 `role === 'system'` 的处理：

```tsx
{messages.map((msg, i) => (
  <div key={i} className={`flex ${
    msg.role === 'user' ? 'justify-end' :
    msg.role === 'system' ? 'justify-center' : 'justify-start'
  }`}>
    {msg.role === 'system' ? (
      // 阶段切换横幅通知
      <div className="w-full text-center py-1.5 px-3">
        <span className="inline-block px-4 py-1 text-xs text-blue-600 bg-blue-50
                         border border-blue-200 rounded-full font-medium">
          {msg.content}
        </span>
      </div>
    ) : msg.role === 'user' ? (
      /* 用户气泡 */
    ) : (
      /* 助手气泡 */
    )}
  </div>
))}
```

#### 18.8.4 导航按钮渲染

```tsx
{/* 阶段导航按钮 — 放在阶段导航标签栏两端 */}
<button
  onClick={() => switchPhase('back')}
  disabled={phaseChanging || loading || phaseIndex === 0}
  className="shrink-0 flex items-center gap-1 px-2.5 py-1 text-xs rounded-lg
             bg-white border border-gray-300 text-gray-600 hover:bg-gray-100
             disabled:opacity-40 disabled:cursor-not-allowed"
  aria-label="上一阶段"
>
  {phaseChanging ? '⏳' : '←'} 上一阶段
</button>

{/* ... 阶段标签列表 ... */}

<button
  onClick={() => switchPhase('next')}
  disabled={phaseChanging || loading || phaseIndex === PHASE_KEYS.length - 1}
  className="shrink-0 flex items-center gap-1 px-2.5 py-1 text-xs rounded-lg
             bg-white border border-gray-300 text-gray-600 hover:bg-gray-100
             disabled:opacity-40 disabled:cursor-not-allowed"
  aria-label="下一阶段"
>
  下一阶段 {phaseChanging ? '⏳' : '→'}
</button>
```

---

### 18.9 与 §13 更新点的对应关系

§13 中描述的现有前端设计与本节扩展内容的关系：

| §13 中的现有能力 | §18 的扩展/变更 |
|----------------|---------------|
| `/next`、`/back` 斜线命令 | 功能保留；按钮为其可视化替代，底层逻辑通过专用端点实现 |
| 阶段标签栏（只读展示） | 在标签栏两端各加一个导航按钮；标签本身保持不可点击切换阶段（点击只用于切换右侧文档查看，不改变当前阶段） |
| 右侧阶段文档面板 | 阶段切换后自动展示新阶段文档，无需用户手动刷新 |
| 快捷建议词条 | 阶段切换后 `suggestions` 随新阶段更新，展示新阶段的行动建议 |
| `loading` 状态 | 新增 `phaseChanging` 状态，两者互斥，避免并发操作 |

> **注意**：阶段标签栏的标签点击（已在 §13.1 中设计为查看该阶段文档）与阶段导航按钮（改变当前阶段）是两个不同的操作，需在 UI 上有明显区分：
> - **标签点击** → 右侧文档切换为该阶段文档（不改变 `phase` 状态，不触发 AI）
> - **导航按钮点击** → 改变 `phase` 状态，触发 AI 生成引导消息，更新文档面板

---

### 18.10 边界条件与错误处理

| 场景 | 处理方式 |
|------|---------|
| 已在 P1，点击「上一阶段」 | 按钮禁用，不可点击 |
| 已在 P5，点击「下一阶段」 | 按钮禁用，不可点击 |
| 并发：正在 loading（AI 回复中），点击导航 | 导航按钮全局禁用，与 `loading` 互斥 |
| AI Provider 超时或错误 | 与 `/chat` 相同的错误处理，显示重试提示；阶段不变（未 persist） |
| 切换后用户立即点击反方向按钮 | 正常处理，允许来回切换 |
| session_id 尚未初始化（未发送任何消息） | 后端尝试加载 AgentContext，若 Conversation 不存在则 404；前端提示用户先发送一条消息初始化 |

---

### ADR-008：阶段切换——专用 API vs. 复用 /chat 端点

**问题**：是新增 `POST /api/v1/agent/switch-phase` 端点，还是将按钮触发改写为向 `/chat` 发送 `/next` 或 `/back` 消息？

**决策**：**新增专用端点**。

| 方案 | 优点 | 缺点 | 结论 |
|------|------|------|------|
| 复用 /chat（发送 `/next`/`/back`） | 实现最简单，无需新端点 | 用户消息列表中会出现 `/next` 命令文本，影响可读性；无法区分「用户文字」和「系统操作」 | ⚠️ 可作为快速实现路径 |
| 新增 /switch-phase 端点 | 前后端语义分离；响应体可携带 `phase_changed` 标志；触发消息不出现在用户气泡中；后续可独立扩展（如添加阶段切换鉴权、限流）| 需要新增端点和 Schema | ✅ 推荐方案 |

**代价**：需要在 `AgentCore` 中新增 `switch_phase()` 方法，在 `PromptBuilder` 中增加 `phase_switch_trigger` 参数，并在路由层新增端点。复杂度增量可控。

**快速实现路径（可选）**：若需要最小化改动快速验证效果，可先让按钮向 `/chat` 发送隐式触发消息（`[SYSTEM] /next`），前端过滤掉该消息不展示为用户气泡，待功能稳定后再迁移到专用端点。

---

## 19. §12 和 §15 更新

### §12 补充：阶段切换接口

在现有 §12 的 API 接口列表中，新增以下端点（完整规范见 §18.4）：

```
POST /api/v1/agent/switch-phase
```

**请求体：**
```json
{
  "session_id": "uuid",
  "direction": "next",
  "provider": "openai"
}
```

**响应体**：与 `/chat` 结构相同，额外包含 `phase_changed: true`。

---

### §15 补充：实现路线图新增里程碑

| 里程碑 | 内容 | 优先级 |
|--------|------|--------|
| M16 | **阶段导航按钮**：前端「上一阶段/下一阶段」按钮 + `POST /api/v1/agent/switch-phase` 端点 + `phase_switch_trigger` 指令块 + 阶段切换系统通知气泡 | 🔴 高 |

---

## 20. P2 双角色场景提取机制（Dual-Role Scenario Extraction）

### 20.1 问题背景

在第二阶段（需求收集 P2）中，对话型 AI 有时会在回复正文中描述或讨论业务场景，但未能同步嵌入对应的 `<scenario>` XML 标记。这导致 `KnowledgeExtractor` 无法从回复中提取到这些场景，最终造成**对话中显示的业务项**与**阶段文档中记录的业务项**不一致。

### 20.2 设计方案：双角色模式

为解决上述问题，在 P2 阶段的每轮对话结束后，引入一个独立的**"场景提取器"角色**（Extractor Role）。两个角色各司其职：

| 角色 | 职责 | AI 调用 | 输出格式 |
|------|------|---------|----------|
| **对话者（Conversational Role）** | 理解用户意图、推进需求收集对话、引导深挖边界场景 | 第 1 次 AI 调用（现有流程） | 自然语言回复 + 可选 `<scenario>` XML 标记 |
| **提取器（Extractor Role）** | 从本轮对话片段中识别**所有**业务场景并结构化输出 | 第 2 次 AI 调用（新增） | 纯 JSON 数组 |

### 20.3 时序流程

```
用户消息
    │
    ▼
[第 1 次 AI 调用] 对话者角色
    │  system prompt = PromptBuilder.build()（含完整阶段指令）
    │  → 自然语言回复 + 可选 <scenario> 标记
    │
    ▼
KnowledgeExtractor.extract(ai_reply, ctx)   ← XML 标记提取（原有）
    │
    ▼
[第 2 次 AI 调用] 提取器角色（仅 P2 阶段）
    │  user prompt = PromptBuilder.build_scenario_extraction_prompt()
    │    ┌─ 本轮 user_message
    │    ├─ 本轮 ai_reply
    │    └─ ctx 中现有 business_scenarios（避免重复）
    │  → 纯 JSON 数组
    │
    ▼
KnowledgeExtractor.merge_scenarios_from_json(json_reply, ctx)
    │  • 已存在同名场景 → 补充空描述（不覆盖）
    │  • 新场景 → 追加到 ctx.domain_knowledge.business_scenarios
    │
    ▼
PhaseDocumentRenderer.render(ctx)  ← 阶段文档包含全部已对齐场景
```

### 20.4 实现细节

#### PromptBuilder.build_scenario_extraction_prompt()
- 输入：`ctx`（含现有场景列表）、`user_message`、`ai_reply`
- 输出：单条 `user` 角色消息字符串，指令简洁，要求只返回 JSON 数组
- 现有场景以 JSON 格式列出，提示提取器不重复添加但可补充描述

#### KnowledgeExtractor.merge_scenarios_from_json()
- 容错地从文本中提取第一个 JSON 数组（支持 AI 偶尔夹杂无关文字的情况）
- 按场景 name 去重：同名场景仅补充空描述，不覆盖已有数据
- 解决 id 冲突：新场景若与现有 id 重复，自动分配新 id
- 返回新增场景数量（用于日志和测试断言）

#### AgentCore._reconcile_scenarios()
- 在 `chat()` 方法步骤 5（XML 提取）之后、步骤 7（文档渲染）之前调用
- 仅在 `ctx.current_phase == Phase.REQUIREMENT` 时触发
- 任何异常均静默记录为 DEBUG 日志，不影响主流程响应

### 20.5 性能考量

第 2 次 AI 调用使用专注的短 prompt（无完整系统提示、无历史消息），推理 token 消耗远低于主对话调用。可以通过以下策略进一步优化：

- **条件触发**：若第 1 次 AI 回复已包含 `<scenario>` 标记且数量与对话内容一致，可跳过第 2 次调用（未来优化项）。
- **低优先级模型**：提取器调用可配置为使用响应更快、成本更低的 AI 模型（未来优化项）。

### 20.6 §15 补充：实现路线图新增里程碑

| 里程碑 | 内容 | 优先级 |
|--------|------|--------|
| M17 | **P2 双角色场景提取**：`build_scenario_extraction_prompt()` + `merge_scenarios_from_json()` + `_reconcile_scenarios()` + 加强版 P2 系统提示 | 🔴 高 |
