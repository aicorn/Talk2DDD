# Talk2DDD AI Agent 内核设计

## 1. 概述

### 1.1 设计目标

当前的 AI 对话功能仅将用户消息透传给第三方 AI 平台并返回原始响应，缺乏业务语义和引导能力。本文档设计一个具备完整业务语义的 **Talk2DDD AI Agent**，其核心目标是：

1. **引导式需求采集** — 通过结构化对话主动引导用户讲清楚业务背景、核心问题和关键概念。
2. **实时意图识别** — 识别用户话语中的 DDD 信号（实体、聚合、限界上下文等），在对话中即时建议。
3. **状态驱动的对话流** — 将"从零到 DDD 文档"拆分为若干阶段，Agent 自动推进并在阶段之间平滑过渡。
4. **知识积累与上下文注入** — 将对话中提取的领域知识持久化，并在后续轮次中注入，保证上下文连贯。
5. **文档生成触发** — 在信息充分时自动或按需生成各类 DDD 文档（业务需求、领域模型、用例、通用语言等）。
6. **需求变更管理** — 支持在任意阶段追加新需求、修改已有需求、废弃旧需求，并自动标记受影响的文档为"待更新"，引导用户完成增量修订。
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

Agent 将整个需求—文档生命周期划分为 **6 个阶段**，以有限状态机（FSM）驱动。

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
                         │                ┌──────┐      ┌──────┐  │
                         │          ──────│ P5   │─────▶│ P6   │──┘
                         │                │ 文档  │      │ 审阅  │
                         │                │ 生成  │      │ 完善  │
                         │                └──────┘      └──────┘
                         └────────────────────────────────────────┘
```

> **需求变更回溯**：在 P3~P6 任意阶段，用户说出"我们还有一个新需求…"或使用 `/change` 命令时，`PhaseEngine` 将触发 **需求变更回溯**，把阶段临时切回 P2（需求收集），采集完毕后重新推进，并自动标记受影响的已生成文档为 `STALE`（待更新）。

### 阶段定义

| 阶段 | 标识 | 名称 | 目标 | 退出条件 | 阶段文档类型 |
|------|------|------|------|----------|------------|
| 1 | `ICEBREAK` | 破冰引入 | 了解用户角色和项目背景 | 收集到项目名称、领域背景 | 项目简介 |
| 2 | `REQUIREMENT` | 需求收集 | 梳理业务流程和痛点 | 收集到 ≥3 个核心业务场景 | 业务需求草稿 |
| 3 | `DOMAIN_EXPLORE` | 领域探索 | 识别核心概念和术语 | 识别出 ≥5 个领域概念候选 | 领域概念词汇表 |
| 4 | `MODEL_DESIGN` | 模型设计 | 设计聚合、实体、值对象 | 用户确认领域模型草稿 | 领域模型草稿 |
| 5 | `DOC_GENERATE` | 文档生成 | 生成各类 DDD 文档 | 至少一类文档生成完成 | 已生成文档列表 |
| 6 | `REVIEW_REFINE` | 审阅完善 | 根据反馈修订文档 | 用户标记项目完成 | 修订记录 |

### 阶段跳转规则

- **顺序推进**：默认按 P1→P2→…→P6 线性推进。
- **手动跳转**：用户可在任意阶段输入指令（`/generate`, `/model`, `/back`）触发跳转。
- **回退**：在 P3~P6 阶段，用户可回退到前一阶段补充信息。
- **并行文档**：P5 可多次循环（生成不同类型文档），不强制转入 P6。
- **需求变更回溯**：在 P3~P6 阶段检测到需求变更意图时，回溯至 P2 采集新需求，完成后重新推进至变更前的阶段；已生成文档自动标记为 `STALE`。

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
│   └── affected_documents: List[str]  # 受影响的文档类型列表
│
├── generated_documents: List[DocumentRef]  # 已生成文档引用
│   ├── version_id: UUID
│   ├── document_type: str
│   ├── generated_at: datetime
│   └── status: DocumentStatus        # CURRENT | STALE | SUPERSEDED
│
└── clarification_queue: List[Question]    # 待澄清问题队列
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
过期文档: {stale_documents}              ← 标记为 STALE 的文档类型列表
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
│ Layer 3: 已积累的领域上下文（动态注入）                           │
│   "[CONTEXT_BLOCK] ... [/CONTEXT_BLOCK]"                       │
├────────────────────────────────────────────────────────────────┤
│ Layer 4: 工具调用格式说明（可选，按需开启）                        │
│   "当识别出新领域概念时，调用 extract_domain_concepts 工具..."    │
├────────────────────────────────────────────────────────────────┤
│ Layer 5: 输出格式约束（按阶段）                                   │
│   "每次回复末尾必须包含 [NEXT_QUESTION] 标记..."                  │
└────────────────────────────────────────────────────────────────┘
```

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
目标：引导用户确定聚合边界和上下文划分。
提问模板：
  - "{概念A}" 和 "{概念B}" 是否总是一起变化？（聚合判断）
  - 哪些操作必须保持原子性？（事务边界）
  - 不同团队负责哪些业务？（限界上下文边界）
输出：领域模型草稿（文字描述 + 树形结构）
```

#### P5 文档生成
```
目标：基于积累的知识生成指定类型的 DDD 文档。
触发：用户明确请求 或 Agent 判断信息已充足。
生成类型（DocumentType）：
  - BUSINESS_REQUIREMENT  业务需求文档
  - DOMAIN_MODEL          领域模型文档
  - UBIQUITOUS_LANGUAGE   通用语言术语表
  - USE_CASES             用例说明
  - TECH_ARCHITECTURE     技术架构建议
```

#### P6 审阅完善
```
目标：收集用户对文档的反馈，定向修订。
模式：diff 式修改（"第3节的聚合边界有误，请修改..."）
支持：全量重写 / 局部修订 / 版本回溯
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
| `advance_phase` | 退出条件满足时 | 目标阶段 | 新阶段 + 阶段引导消息 |
| `generate_document` | P5 阶段触发 | `DocumentType`、上下文摘要 | 文档内容（Markdown） |
| `validate_ddd_model` | P4 阶段模型草稿完成后 | 领域模型 JSON | 验证结果 + 改进建议 |
| `record_requirement_change` | 检测到需求变更意图时 | 变更类型、目标场景/概念、变更描述 | `RequirementChange` 记录 + 受影响文档列表 |

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
  "description": "记录用户提出的需求变更（新增、修改或废弃），并标记受影响的已生成文档为 STALE",
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
      "affected_document_types": {
        "type": "array",
        "items": { "type": "string", "enum": ["BUSINESS_REQUIREMENT","DOMAIN_MODEL","UBIQUITOUS_LANGUAGE","USE_CASES","TECH_ARCHITECTURE"] },
        "description": "预计受影响的文档类型列表"
      },
      "trigger_phase_rollback": {
        "type": "boolean",
        "description": "是否需要回溯到 REQUIREMENT 阶段重新采集细节（变更较大时为 true）"
      }
    },
    "required": ["change_type","description","affected_document_types","trigger_phase_rollback"]
  }
}
```

---

## 8. 需求变更管理（RequirementChangeManager）

### 8.1 需求变更的三种类型

| 类型 | 标识 | 典型用户话语示例 | 处理方式 |
|------|------|----------------|---------|
| 追加新需求 | `ADD` | "我们还需要支持…" / "另外有个场景…" | 回溯 P2 采集细节，更新 `business_scenarios`，追加相关概念 |
| 修改已有需求 | `MODIFY` | "之前说的 X 其实应该是…" / "需求有变，Y 改成…" | 定位目标场景/概念，原地更新，版本号递增，标记关联文档 `STALE` |
| 废弃旧需求 | `DEPRECATE` | "X 功能砍掉了" / "不需要…了" | 将目标场景状态改为 `DEPRECATED`，标记关联文档 `STALE`，从领域模型中移除或注释相关概念 |

### 8.2 变更检测信号

`PromptBuilder` 在 P3~P6 阶段的 System Prompt 中增加如下指令，使 AI 主动识别需求变更意图：

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
   - 计算 affected_document_types
        │
        ▼
④ 标记受影响文档为 STALE
   DocumentRef.status = STALE
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
⑥ Agent 向用户展示变更影响摘要，并提示可以重新生成文档
   "已记录需求变更。以下文档需要更新：[业务需求文档, 用例说明]。
    输入 /generate 重新生成，或继续对话完善需求后再生成。"
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
  <affected_documents>BUSINESS_REQUIREMENT,USE_CASES</affected_documents>
</requirement_change>

<requirement_change type="MODIFY" target_id="S003" trigger_rollback="true">
  <description>将「订单取消」改为支持部分取消</description>
  <affected_documents>BUSINESS_REQUIREMENT,DOMAIN_MODEL,USE_CASES</affected_documents>
</requirement_change>

<!-- 冲突检测标记 -->
<conflict type="RULE_CONTRADICTION" concepts="订单不可修改,订单可在24h内修改">
  两条规则存在矛盾，需用户明确优先级。
</conflict>
```

---

## 9. 文档生成管道（DocumentGenerationPipeline）

```
┌──────────────────────────────────────────────────────────────┐
│              DocumentGenerationPipeline                       │
│                                                              │
│  ① 上下文聚合                                                │
│     从 AgentContext 提取: domain_knowledge + phase_history   │
│                    │                                         │
│  ② 模板选择                                                  │
│     根据 DocumentType 选择对应的文档生成 Prompt 模板           │
│                    │                                         │
│  ③ AI 调用                                                   │
│     构建完整 Prompt（角色+模板+上下文），调用 ai_service       │
│                    │                                         │
│  ④ 后处理                                                    │
│     提取 Markdown 内容，去除 AI 前缀语、清理格式              │
│                    │                                         │
│  ⑤ 文档存储                                                  │
│     写入 DocumentVersion（关联 project_id + document_type）  │
│                    │                                         │
│  ⑥ 返回给前端                                                │
│     文档内容 + 版本 ID + 生成元信息                           │
└──────────────────────────────────────────────────────────────┘
```

### 9.1 文档类型与生成提示模板

| 文档类型 | 生成提示重点 | 输出格式 |
|----------|------------|---------|
| `BUSINESS_REQUIREMENT` | 核心目标、用户角色、功能需求、非功能需求 | 标准需求文档 Markdown |
| `DOMAIN_MODEL` | 限界上下文、聚合设计、领域事件、上下文映射 | 结构化 Markdown + 树形图 |
| `UBIQUITOUS_LANGUAGE` | 所有已识别概念及其定义、分类 | 术语表 Markdown |
| `USE_CASES` | 每个业务场景转化为标准用例格式 | 用例说明 Markdown |
| `TECH_ARCHITECTURE` | 基于领域模型推荐技术边界和分层 | 架构建议 Markdown |

---

## 10. 阶段文档渲染器（PhaseDocumentRenderer）

### 10.1 设计原则

`PhaseDocumentRenderer` 是一个**纯模板渲染器**，不调用 AI，直接从 `AgentContext` 中已有的结构化数据生成当前阶段对应的 Markdown 文档。它在每轮对话的 `ContextManager.merge()` 完成后立即运行，将渲染结果写入 `PhaseDocument`（持久化）并在 API 响应中返回给前端。

**特点**：
- ⚡ **零延迟** — 无 AI 调用，毫秒级完成，不影响主流程响应时间
- 🔄 **每轮更新** — 每次对话后自动重新渲染，始终反映最新状态
- 🗂 **六个阶段各有专属模板** — 模板与阶段绑定，仅渲染本阶段已收集到的内容

### 10.2 各阶段文档模板

| 阶段 | 阶段文档名称 | 模板包含的关键内容 |
|------|------------|-----------------|
| P1 `ICEBREAK` | **项目简介** | 项目名称、领域背景、核心用户、已知痛点（来自 `domain_knowledge.project_name` / `domain_description`） |
| P2 `REQUIREMENT` | **业务需求草稿** | 已收集业务场景列表（含状态和版本）、待澄清问题 |
| P3 `DOMAIN_EXPLORE` | **领域概念词汇表** | 所有已识别概念（名称、类型、描述、置信度），按类型分组 |
| P4 `MODEL_DESIGN` | **领域模型草稿** | 限界上下文列表、聚合/实体/值对象树形结构、概念关系 |
| P5 `DOC_GENERATE` | **已生成文档索引** | 已生成文档列表（类型、版本、生成时间、状态），STALE 文档标红 |
| P6 `REVIEW_REFINE` | **修订记录** | 所有需求变更历史、文档修订说明、版本对比摘要 |

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
              ② PhaseEngine.evaluate()
                判断当前阶段，检查退出条件
                        │
                  ┌─────┴─────┐
                  │ 需要跳转?  │
                  └─────┬─────┘
                  是 │   │ 否
                     ▼   ▼
              advance_phase()  保持当前阶段
                        │
                        ▼
              ③ PromptBuilder.build()
                Layer1~5 拼装 System Prompt
                        │
                        ▼
              ④ ai_service.chat_completion()
                发送 [system + history + user] 给 AI Provider
                        │
                        ▼
              ⑤ KnowledgeExtractor.extract()
                解析 AI 回复中的结构化标记
                        │
                        ▼
              ⑥ ContextManager.merge()
                增量合并到 AgentContext
                        │
                        ▼
              ⑦ ToolDispatcher.dispatch()
                执行 AI 请求的工具调用（如有）
                        │
                        ▼
              ⑧ PhaseDocumentRenderer.render()   ← 新增
                从 AgentContext 渲染当前阶段文档
                （纯模板，无 AI 调用）
                        │
                        ▼
              ⑨ 持久化 AgentContext + PhaseDocument
                        │
                        ▼
              ⑩ 返回响应给前端
                { reply, phase, suggestions, documents,
                  phase_document }              ← 新增字段
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
  "stale_documents": [],          // 因变更而过期的文档类型
  "pending_documents": [],        // 可以生成的文档类型
  "phase_document": {             // 当前阶段文档（每轮更新）
    "phase": "REQUIREMENT",
    "title": "业务需求草稿",
    "content": "# 业务需求草稿\n\n...",
    "rendered_at": "2024-01-01T10:30:00Z",
    "turn_count": 5
  }
}
```

### 12.2 文档生成接口

```
POST /api/v1/agent/generate-document
```

**请求体：**
```json
{
  "session_id": "uuid",
  "project_id": "uuid",
  "document_type": "DOMAIN_MODEL",
  "provider": "openai"
}
```

**响应体：**
```json
{
  "document_type": "DOMAIN_MODEL",
  "content": "# 领域模型\n\n...",
  "version_id": "uuid",
  "generated_at": "2024-01-01T00:00:00Z"
}
```

### 12.3 Agent 上下文查询接口

```
GET /api/v1/agent/context/{session_id}
```

返回当前 `AgentContext` 摘要，供前端渲染进度和已提取概念。

### 12.4 需求变更历史接口

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
      "affected_documents": ["BUSINESS_REQUIREMENT", "USE_CASES"]
    }
  ],
  "stale_documents": ["BUSINESS_REQUIREMENT", "USE_CASES"]
}
```

### 12.5 阶段文档查询接口

```
GET /api/v1/agent/phase-document/{session_id}/{phase}
```

`phase` 取值：`ICEBREAK` | `REQUIREMENT` | `DOMAIN_EXPLORE` | `MODEL_DESIGN` | `DOC_GENERATE` | `REVIEW_REFINE`

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
│  [P1 破冰] [P2 需求★] [P3 探索] [P4 模型] [P5 文档] [P6 审阅]    │  ← 阶段标签栏
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

- **标签栏**：显示全部 6 个阶段标签，当前阶段用「★」标注并高亮；已完成阶段用「✓」标注；有 STALE 文档的阶段显示「⚠️」。
- **默认选中**：始终展示当前阶段文档；阶段跳转时自动切换标签。
- **用户切换**：点击任意阶段标签，调用 `GET /api/v1/agent/phase-document/{session}/{phase}` 异步加载该阶段文档。
- **每轮自动刷新**：对话发送后，右侧面板使用 chat 响应体中的 `phase_document` 无闪烁替换内容（无额外请求）。
- **渲染格式**：Markdown 渲染（支持表格、代码块、树形结构）；STALE 文档类型以橙色背景标记。

### 13.2 Chat 页面增强要点

- **阶段进度条** — 顶部显示当前所处阶段（P1~P6）及整体进度。
- **概念面板** — 侧边栏实时展示已识别的领域概念，支持用户编辑。
- **快捷建议** — 对话框下方展示 `suggestions` 中的快捷回复按钮。
- **文档生成按钮** — 当 `pending_documents` 非空时，显示"生成 XXX 文档"按钮。
- **STALE 文档提示** — 当 `stale_documents` 非空时，在文档面板标签上显示橙色「⚠️ 需更新」徽标，并提示用户重新生成。
- **需求变更时间轴** — 侧边栏可展开查看需求变更历史，了解每次变更影响了哪些文档。
- **阶段手动控制** — 允许用户通过 `/next`、`/back`、`/generate` 等斜线命令手动控制阶段。

### 13.3 斜线命令

| 命令 | 功能 |
|------|------|
| `/next` | 强制进入下一阶段 |
| `/back` | 回退到上一阶段 |
| `/generate [类型]` | 立即生成指定文档 |
| `/model` | 跳转到模型设计阶段 |
| `/status` | 显示当前上下文摘要 |
| `/reset` | 重置当前会话 |
| `/change` | 主动声明需求变更，触发 `record_requirement_change` 工具 |
| `/changes` | 查看本次对话的需求变更历史 |
| `/regenerate [类型]` | 重新生成指定类型的 STALE 文档 |

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
├── affected_document_types: JSONB  # List[str]
└── changed_at: datetime

DocumentVersion (扩展)
├── ... (现有字段)
└── staleness_status: str         # 新增：CURRENT | STALE | SUPERSEDED

PhaseDocument                     # 新增表，每轮对话后写入/覆盖
├── id: UUID
├── conversation_id: UUID (FK)
├── phase: str                    # ICEBREAK | REQUIREMENT | ...
├── content: str                  # Markdown 渲染结果
├── rendered_at: datetime         # 最后渲染时间
└── turn_count: int               # 对应的对话轮次序号
```

---

## 15. 实现路线图

| 里程碑 | 内容 | 优先级 |
|--------|------|--------|
| M1 | System Prompt 分层 + 阶段静态切换 | 🔴 高 |
| M2 | AgentContext 设计与 Redis 持久化 | 🔴 高 |
| M3 | PhaseDocumentRenderer 六阶段模板 + PhaseDocument 持久化 | 🔴 高 |
| M4 | 前端双栏布局：对话区 + 阶段文档面板（六阶段标签 + 自动刷新） | 🔴 高 |
| M5 | KnowledgeExtractor（基于 XML 标记解析） | 🟡 中 |
| M6 | ToolDispatcher + Function Calling 集成 | 🟡 中 |
| M7 | DocumentGenerationPipeline 完整实现 | 🟡 中 |
| M8 | 需求变更管理：record_requirement_change 工具 + STALE 标记 | 🟡 中 |
| M9 | 需求变更冲突检测（概念重复、规则矛盾） | 🟡 中 |
| M10 | 前端阶段进度条 + 概念面板 + 快捷建议 | 🟢 低 |
| M11 | 前端 STALE 文档提示 + 需求变更时间轴 | 🟢 低 |
| M12 | 斜线命令解析（含 `/change`, `/changes`, `/regenerate`） | 🟢 低 |
| M13 | `validate_ddd_model` 工具（DDD 合规检查） | 🟢 低 |

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

**问题**：对话轮次增多后，注入的历史上下文会超出 Token 限制。

**决策**：采用"滚动摘要"策略：
1. 保留最近 N 轮完整对话（N=10）。
2. 更早的对话由 AI 总结为结构化摘要，注入为 System Prompt 的一部分。
3. `DomainKnowledge` 始终以结构化 JSON 形式存储，而非原始对话文本，天然压缩。

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

3. **`DocumentVersion` 保留历史版本，新版标记 `CURRENT`，旧版标记 `SUPERSEDED`**  
   - 变更触发文档进入 `STALE` 状态；用户触发重新生成后，新版本标记为 `CURRENT`，旧版本改为 `SUPERSEDED`。  
   - 原因：文档版本管理是已有功能，复用现有设计，不引入额外复杂度。

**代价**：需要在 `ContextManager.merge()` 中实现"变更意图 → `BusinessScenario` 查找 → 更新/新增 → 写 `RequirementChange`"的事务逻辑。

---

### ADR-005：阶段文档渲染策略——模板渲染 vs. AI 生成

**问题**：阶段文档每轮都要更新，是用 AI 重新生成（高质量但慢），还是用模板引擎渲染（快但格式固定）？

**决策**：**阶段文档（PhaseDocument）采用模板渲染；正式 DDD 文档（DocumentGenerationPipeline）保留 AI 生成。**

| 维度 | PhaseDocument（模板渲染） | 正式 DDD 文档（AI 生成） |
|------|-------------------------|------------------------|
| 触发时机 | 每轮对话自动触发 | 用户明确请求或 Agent 判断信息充足 |
| 延迟 | < 5ms（纯模板） | 5~30s（AI 调用） |
| 内容质量 | 结构化展示，无润色 | 专业文档，AI 润色 |
| 用途 | 让用户实时了解当前状态 | 最终可交付的 DDD 文档 |
| 更新策略 | 覆盖写（仅保留最新一条） | 追加写（保留历史版本） |

**原因**：
1. 每轮对话都触发 AI 生成会导致响应时间过长（用户需等待 10~30 秒），破坏对话体验。
2. 阶段文档的目的是"状态可视化"而非"可交付文档"，模板渲染已足够满足需求。
3. 两者分离，互不干扰：阶段文档随时可看，正式文档按需生成。

**代价**：模板维护成本；阶段文档无法包含 AI 的洞察或建议（仅反映已提取的结构化数据）。
