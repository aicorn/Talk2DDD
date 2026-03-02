# Talk2DDD 通用语言（Ubiquitous Language）术语表

## 核心领域概念

### 用户相关

| 术语 | 英文 | 定义 |
|------|------|------|
| 用户 | User | 系统的使用者，包含身份认证信息和个人偏好 |
| 用户偏好 | UserSettings | 用户个性化设置，如语言、主题 |
| 认证令牌 | Token | JWT 访问令牌，用于身份验证 |

### 项目相关

| 术语 | 英文 | 定义 |
|------|------|------|
| 项目 | Project | DDD 文档项目，包含所有相关文档和对话 |
| 领域名称 | DomainName | 项目所在的业务领域名称 |
| 项目状态 | ProjectStatus | 项目当前状态（活跃/归档/完成） |

### 文档相关

| 术语 | 英文 | 定义 |
|------|------|------|
| 文档版本 | DocumentVersion | 文档的特定版本快照 |
| 文档类型 | DocumentType | 文档分类（需求/模型/用例/架构） |
| 通用语言 | UbiquitousLanguage | 团队共同使用的业务术语表 |
| 领域模型 | DomainModel | DDD 领域的核心概念图谱 |
| 用例 | UseCase | 系统功能的使用场景描述 |

### 步骤相关

| 术语 | 英文 | 定义 |
|------|------|------|
| 步骤 | Step | DDD 文档创建的工作步骤 |
| AI 建议 | AISuggestion | AI 对步骤内容的智能建议 |
| 置信度 | ConfidenceScore | AI 建议的可信程度（0-1） |

### 对话相关

| 术语 | 英文 | 定义 |
|------|------|------|
| 对话 | Conversation | 用户与 AI 的交互会话 |
| 消息 | Message | 对话中的单条消息 |
| 消息角色 | MessageRole | 消息发送者（用户/AI/系统） |
| 上下文 | Context | 对话的背景信息 |

## DDD 专业术语

| 术语 | 英文 | 定义 |
|------|------|------|
| 限界上下文 | Bounded Context | 特定模型的应用边界 |
| 聚合根 | Aggregate Root | 聚合的入口实体 |
| 领域事件 | Domain Event | 领域中发生的重要事件 |
| 值对象 | Value Object | 无唯一标识的领域概念 |
| 领域服务 | Domain Service | 跨聚合的业务逻辑 |
| 仓储 | Repository | 聚合的持久化接口 |
