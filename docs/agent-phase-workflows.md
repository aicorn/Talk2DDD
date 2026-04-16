# Talk2DDD AI Agent 各阶段工作流程

## 概述

Talk2DDD AI Agent 将"从零到 DDD 文档"的完整过程划分为 **5 个对话阶段**，由有限状态机（FSM）驱动。每个阶段都有明确的目标、专属的 System Prompt 指令、独立的知识提取逻辑和对应的阶段文档。

**阶段一览：**

| 阶段 | 标识 | 名称 | 进度 | 阶段文档 |
|------|------|------|------|---------|
| P1 | `ICEBREAK` | 破冰引入 | 0% | 项目简介 |
| P2 | `REQUIREMENT` | 需求收集 | 25% | 业务需求草稿 |
| P3 | `DOMAIN_EXPLORE` | 领域探索 | 50% | 领域概念词汇表 |
| P4 | `MODEL_DESIGN` | 模型设计 | 75% | 领域模型草稿 |
| P5 | `REVIEW_REFINE` | 审阅完善 | 100% | 修订记录 |

---

## 每轮对话的通用处理流程

无论处于哪个阶段，每次用户发送消息后，Agent 均按以下步骤依次处理：

```
① 加载 AgentContext（从数据库恢复会话状态）
         ↓
② PhaseEngine.evaluate()
   处理斜线命令（/next、/back、/model、/techstack）
   触发阶段跳转（仅斜线命令触发；UI 按钮走 switch_phase 接口）
         ↓
③ PromptBuilder.build()
   组装 6 层 System Prompt（角色定义 / 阶段指令 / 记忆摘要 /
   领域上下文 / 工具格式说明 / 输出约束）
         ↓
④ 阶段开场建议处理（P2~P5）
   若存在 phase_suggestion，对用户消息进行意图分类
   （UserIntentClassifier），并将操作结果或越界提醒追加到
   System Prompt 末尾
         ↓
⑤ ai_service.chat_completion()
   发送 [system + 最近 K 轮历史 + 当前消息] 给 AI Provider
         ↓
⑥ KnowledgeExtractor.extract()
   解析 AI 回复中的 XML 标记（<concept>、<scenario>、
   <project_info>、<requirement_change>、<tech_stack> 等）
         ↓
⑦ 专项 Reconcile 调用（按阶段，非阻塞）
   P1：_reconcile_project_info()  — 确保项目名称与领域背景被提取
   P2：_reconcile_scenarios()     — 确保业务场景被提取
   P3：_reconcile_domain_concepts()— 确保领域概念被提取
         ↓
⑧ turn_count 递增
         ↓
⑨ PhaseDocumentRenderer.render()
   纯模板渲染，无 AI 调用，毫秒级完成
         ↓
⑩ 持久化 AgentContext + 本轮消息 + 阶段文档
   阶段文档自动写入"我的项目"（覆盖写）
         ↓
⑪ MemoryManager.maybe_compress()（异步后台）
   达到阈值时生成/更新滚动摘要（Layer 2 记忆）
         ↓
⑫ 返回响应给前端
   { reply, phase, phase_document, suggestions, ... }
```

---

## P1 — 破冰引入（ICEBREAK）

### 目标

收集「项目简介」所需的两项信息：**项目名称**和**领域背景**。

### Agent 行为

1. 热情欢迎用户，用一句话介绍 Talk2DDD 能帮助完成 DDD 建模。
2. 每次只问一个问题：先问项目名称，再问领域背景（一句话即可）。
3. 收集到两项信息后，告知用户「项目简介」已生成，并提示点击顶部导航栏的「下一阶段 →」按钮。

> **严格限制**：本阶段只收集项目名称和领域背景，不询问业务场景、用户角色、业务流程等内容（这些属于 P2 的工作）。

### 知识提取

- AI 回复中嵌入 `<project_info name="..." domain="..."/>` 标记。
- 每轮对话结束后，无论 AI 是否嵌入标记，`_reconcile_project_info()` 都会发起一次独立的轻量 AI 调用，从本轮对话中提取项目信息并合并到上下文（双重保障）。
- 仅当 `project_name` 和 `domain_description` 都已填充时，跳过 Reconcile 调用。

### 阶段开场建议

P1 不生成阶段开场建议（`phase_suggestion` 始终为 `None`）。

### 阶段文档：项目简介

| 字段 | 来源 |
|------|------|
| 项目名称 | `domain_knowledge.project_name` |
| 领域背景 | `domain_knowledge.domain_description` |

### 推进至 P2 的方式

- 用户点击顶部导航栏「下一阶段 →」按钮（触发 `switch_phase("next")`）。
- 用户输入 `/next` 斜线命令。

---

## P2 — 需求收集（REQUIREMENT）

### 目标

逐一梳理主要业务流程，挖掘边界场景，收集至少 3 个核心业务场景。

### Agent 行为

1. 运用 **5W1H 提问法**（谁、何时、何地、做什么、为什么、如何）引导用户描述业务流程。
2. 识别用户描述中含有动词的业务场景（注册、下单、审批等）。
3. 对已收集到的场景逐一追问边界情况和异常处理。
4. 当收集到 ≥3 个业务场景时，提示用户可点击「下一阶段 →」进入领域探索。

### 知识提取

- AI 回复中嵌入 `<scenario id="S001" name="...">...</scenario>` 标记。
- `_reconcile_scenarios()` 在每轮对话后发起一次独立的轻量 AI 调用，从对话交换中提取业务场景并增量合并（防止漏提）。

### 阶段开场建议（Phase-Opening Suggestion）

进入 P2 时，`_generate_phase_opening_suggestion()` 根据 P1 已收集的背景信息，生成一份**业务场景细化建议表**（`ScenarioRefinementSuggestion`），存入 `ctx.phase_suggestion`。

该建议以 Markdown 表格呈现给用户，包含：

- 每个场景的细化问题及备选答案（`RefinementItem`）
- 用户可直接在对话中选择某项，Agent 会识别意图（`UserIntentClassifier`）并更新对应建议项的状态

**意图分类：**

| 用户意图 | 处理方式 |
|---------|---------|
| `MAKE_SELECTION` | 将选中项标记为已选，更新文档 |
| `REQUEST_MORE` | 引导 AI 补充更多建议 |
| `REQUEST_REFINE` | 针对某条建议进行细化讨论 |
| `REJECT_SUGGESTION` | 将该建议项标记为已忽略 |
| `PROVIDE_FEEDBACK` | 将反馈摘要注入上下文 |
| `OUT_OF_SCOPE` | 以友好提示告知当前焦点，不阻断对话 |

### 阶段文档：业务需求草稿

| 内容 | 来源 |
|------|------|
| 业务场景列表（名称、描述、状态、版本号） | `domain_knowledge.business_scenarios`（仅 ACTIVE/MODIFIED） |
| 待澄清问题 | `clarification_queue`（未回答 / 已回答） |

### 推进至 P3 的方式

- 用户点击「下一阶段 →」按钮或输入 `/next`。

---

## P3 — 领域探索（DOMAIN_EXPLORE）

### 目标

从业务场景中提炼领域术语，识别实体、值对象、领域事件、业务规则，建立通用语言（Ubiquitous Language），至少识别 5 个领域概念。

### Agent 行为

1. 识别用户描述中的领域信号：
   - **名词**（订单、商品、用户）→ 实体 / 值对象候选
   - **动词**（提交、确认、取消）→ 领域事件候选
   - **规则描述**（"必须"、"只有…才能"）→ 业务规则候选
2. 对每个识别出的概念，向用户确认含义并建立术语定义。
3. 当识别到 ≥5 个概念时，提示用户可点击「下一阶段 →」进入模型设计。

### 进入 P3 时的特殊行为（初始领域概念自动生成）

切换到 P3 时，`switch_phase()` 会在调用对话 AI 之前，先通过 `_generate_initial_domain_concepts()` 发起一次独立的 AI 调用，根据 P2 收集的业务场景自动提炼初版领域概念词汇表。

初版词汇表以完整 Markdown 文档的形式嵌入到触发消息中，AI 直接向用户展示并邀请修改意见，而非从零开始逐一询问。

> **注意**：P3 不生成阶段开场建议（`PhaseSuggestion`）。

### 知识提取

- AI 回复中嵌入 `<concept type="ENTITY|VALUE_OBJECT|..." name="..." confidence="0.0~1.0">...</concept>` 标记。
- `_reconcile_domain_concepts()` 在每轮对话后发起独立轻量 AI 调用，从对话中提取领域概念并增量合并。

### 需求变更检测（P3~P5 通用）

从 P3 开始，System Prompt 中加入**需求变更检测**指令。当用户话语中出现变更信号时：

- AI 嵌入 `<requirement_change type="ADD|MODIFY|DEPRECATE" trigger_rollback="true|false">` 标记。
- `KnowledgeExtractor` 解析后写入 `RequirementChange` 记录，更新对应 `BusinessScenario` 的状态和版本号。
- 若 `trigger_rollback=true`，`PhaseEngine` 将当前阶段临时回溯至 P2 采集需求细节，完成后重新推进至变更前的阶段。
- 受影响的阶段文档自动重新渲染并保存到项目中。

### 阶段文档：领域概念词汇表

| 内容 | 来源 |
|------|------|
| 概念表格（名称、类型、描述、置信度星级） | `domain_knowledge.domain_concepts`（按概念类型分组） |

### 推进至 P4 的方式

- 用户点击「下一阶段 →」按钮、输入 `/next` 或 `/model`。

---

## P4 — 模型设计（MODEL_DESIGN）

### 目标

引导用户确定聚合边界、限界上下文划分；在领域模型草稿确认后，采集用户的技术栈偏好（可跳过）。

### Agent 行为

1. 围绕聚合、限界上下文提问：
   - "「概念A」和「概念B」是否总是一起变化？"（聚合判断）
   - "哪些操作必须保持原子性？"（事务边界）
   - "不同团队负责哪些业务？"（限界上下文边界）
2. 领域模型草稿经用户确认后，自然过渡到技术栈询问：
   - "模型已经清晰了，接下来聊聊技术选型。前端打算用什么框架？"
   - 若用户无偏好，AI 调用 `confirm_tech_stack(skipped=true)`，由 AI 根据领域模型自行推荐。
3. 技术栈确认（或明确跳过）后，提示用户点击「下一阶段 →」进入审阅完善。

**斜线命令支持：**
- `/techstack`：重新采集技术栈偏好（重置 `confirmed=false`，跳转到 MODEL_DESIGN）。
- `/techstack skip`：跳过技术栈选择（设置 `skipped=true, confirmed=true`）。

### 阶段开场建议（Phase-Opening Suggestion）

进入 P4 时，系统生成**聚合模型设计建议表**（`ModelDesignItem` 列表），包含：

- 每个建议项：限界上下文名称、聚合根、建议包含的实体和值对象、设计理由、备选方案
- 用户可直接选择、细化或拒绝各设计项

### 知识提取

- AI 回复中嵌入 `<tech_stack>` 标记，`KnowledgeExtractor` 解析并写入 `TechStackPreferences`。
- 技术选择包含：名称、分类（前端/后端/数据库等）、版本约束（可选）、选择原因（可选）、熟悉程度。

### 阶段文档：领域模型草稿

| 内容 | 来源 |
|------|------|
| 限界上下文列表（名称、描述、包含概念） | `domain_knowledge.bounded_contexts` |
| 领域概念汇总（按类型分组） | `domain_knowledge.domain_concepts` |
| 概念关系 | `domain_knowledge.relationships` |
| 技术栈偏好（前端/后端/数据库等） | `tech_stack_preferences` |

### 推进至 P5 的方式

- 用户确认领域模型草稿 **且** 完成技术栈确认（或明确跳过）后，点击「下一阶段 →」按钮或输入 `/next`。

---

## P5 — 审阅完善（REVIEW_REFINE）

### 目标

收集用户对各阶段文档的反馈，进行定向修订与完善，直至用户满意。

### Agent 行为

1. 告知用户可在「我的项目」中查阅各阶段最新 Markdown 文档。
2. 接受差异式修改请求，例如："第3节的聚合边界有误，请修改..."。
3. 支持三种修改模式：
   - **全量重写**：重新生成某一阶段文档。
   - **局部修订**：对特定场景、概念或关系进行修改。
   - **版本回溯**：触发需求变更回溯，重新采集并推进。
4. 记录所有需求变更到 `RequirementChange`，受影响阶段文档自动重新渲染并保存。

### 阶段开场建议（Phase-Opening Suggestion）

进入 P5 时，系统生成**文档审阅修订建议表**（`ReviewItem` 列表），包含：

- 每个审阅项：严重程度（高/中/低）、问题类型（一致性问题/边界问题等）、问题描述、修订建议、备选方案
- 用户可逐项处理或一次性给出反馈

### 需求变更管理（延续 P3/P4）

P5 中同样持续监听需求变更信号，处理流程与 P3/P4 相同（检测 → 确认 → 记录 → 重新渲染 → 可选回溯）。

### 阶段文档：修订记录

| 内容 | 来源 |
|------|------|
| 需求变更历史表（变更类型、目标、描述、时间） | `requirement_changes` |

---

## 阶段切换机制

### 手动推进（通过 UI 按钮）

用户点击「下一阶段 →」按钮时，前端调用 `POST /api/v1/agent/switch-phase/async`，Agent 执行以下步骤：

```
① 计算目标阶段（当前阶段 +1）
② 调用 PhaseEngine.advance_phase() 更新 ctx.current_phase
③ 构建带 phase_switch_trigger=True 的 System Prompt
④ 生成阶段开场建议（P2/P4/P5 生成 PhaseSuggestion；P3 生成初版领域概念）
⑤ 构造触发消息（嵌入阶段建议或初版文档）
⑥ 调用 AI 生成阶段引导回复
⑦ 渲染阶段文档 → 持久化 → 返回响应
```

> 触发消息是内部系统消息，**不写入**用户可见的消息历史。

### 斜线命令（通过对话输入）

| 命令 | 效果 |
|------|------|
| `/next` | 前进一个阶段 |
| `/back` | 回退一个阶段 |
| `/model` | 直接跳转到 MODEL_DESIGN（P4） |
| `/techstack` | 重新采集技术栈，跳转到 MODEL_DESIGN |
| `/techstack skip` | 跳过技术栈采集，当前阶段不变 |

### 需求变更回溯

在 P3~P5 阶段检测到较大需求变更时（`trigger_rollback=true`）：

```
① AI 嵌入 <requirement_change trigger_rollback="true">
② PhaseEngine 记录 ctx.phase_before_change = 当前阶段
③ 回溯至 P2，采集新需求细节
④ 完成后重新推进至 phase_before_change
⑤ 受影响阶段文档自动重新渲染并保存
```

---

## 记忆机制（跨阶段）

Agent 使用三层记忆模型，确保长对话不丢失上下文：

| 层级 | 内容 | 持续性 |
|------|------|--------|
| Layer 1：即时记忆 | 最近 K 轮（默认 10 轮）原文消息 | 随对话滚动 |
| Layer 2：滚动摘要 | AI 压缩旧轮次为 200~400 字摘要（`[MEMORY_SUMMARY]`）| 每 M 轮（默认 5 轮）异步刷新 |
| Layer 3：结构化记忆 | `AgentContext.domain_knowledge` 全量注入（`[CONTEXT_BLOCK]`）| 全会话持久 |

- 首次压缩触发条件：`turn_count >= 10`。
- Token 超预算时，自动缩减 K 值（最少保留 2 轮）。
- 压缩操作**异步执行**，不阻塞主对话响应。

---

## 阶段文档自动保存

每轮对话（无论是普通对话还是阶段切换）完成后，`PhaseDocumentRenderer` 在毫秒级内纯模板渲染当前阶段文档，并同步写入"我的项目"中对应的阶段文档记录（覆盖写）：

- 用户**无需手动触发**任何保存操作。
- 同一阶段每轮都覆盖，仅保留最新版本。
- 若项目尚未创建，Agent 在收集到足够领域知识（至少含项目名称）后自动创建项目。
- 需求变更发生后，受影响的所有阶段文档立即重新渲染并保存。
