# Talk2DDD DDD 领域模型设计

## 限界上下文

### 1. 用户身份上下文（Identity Context）
- **聚合根**：User
- **职责**：用户注册、认证、授权
- **对外接口**：用户 ID、邮箱、角色

### 2. 项目管理上下文（Project Context）
- **聚合根**：Project
- **职责**：项目创建、管理、归档
- **对外接口**：项目 ID、名称、状态

### 3. 文档管理上下文（Document Context）
- **聚合根**：DocumentVersion
- **职责**：文档版本创建、管理、发布
- **对外接口**：版本 ID、内容、类型

### 4. AI 对话上下文（Conversation Context）
- **聚合根**：Conversation
- **职责**：管理与 AI 的对话历史
- **对外接口**：对话 ID、消息列表

### 5. 步骤工作流上下文（Workflow Context）
- **聚合根**：Step
- **职责**：管理文档创建的工作步骤
- **对外接口**：步骤 ID、类型、状态

## 聚合设计

### User 聚合
```
User (聚合根)
├── id: UUID
├── email: Email (值对象)
├── username: Username (值对象)
├── hashed_password: HashedPassword (值对象)
├── is_active: bool
└── settings: UserSettings (值对象)
    ├── preferred_language: Language
    └── theme: Theme
```

### Project 聚合
```
Project (聚合根)
├── id: UUID
├── name: ProjectName (值对象)
├── domain_name: DomainName (值对象)
├── owner_id: UserId (引用)
└── status: ProjectStatus (枚举)
    - active
    - archived
    - completed
```

### DocumentVersion 聚合
```
DocumentVersion (聚合根)
├── id: UUID
├── project_id: ProjectId (引用)
├── version_number: VersionNumber (值对象)
├── content: DocumentContent (值对象)
├── document_type: DocumentType (枚举)
└── is_current: bool
```

### Conversation 聚合
```
Conversation (聚合根)
├── id: UUID
├── user_id: UserId (引用)
├── project_id: ProjectId (引用, 可选)
├── title: ConversationTitle (值对象)
├── status: ConversationStatus (枚举)
└── messages: Message[] (实体列表)
    ├── id: UUID
    ├── role: MessageRole (枚举)
    └── content: MessageContent (值对象)
```

## 领域事件

- `UserRegistered` - 用户注册完成
- `UserAuthenticated` - 用户登录成功
- `ProjectCreated` - 项目创建完成
- `DocumentVersionCreated` - 文档版本创建
- `ConversationStarted` - 对话开始
- `MessageSent` - 消息发送
- `AISuggestionGenerated` - AI 建议生成
- `StepCompleted` - 步骤完成

## 上下文映射

```
Identity ──(共享内核)──> Project
Identity ──(共享内核)──> Conversation
Project  ──(开放主机)──> Document
Project  ──(开放主机)──> Workflow
Conversation ──(合规者)──> AI Service
Workflow ──(合规者)──> AI Service
```
