# Luminous Companion Runtime 目标架构

> 状态：目标架构的规范性文档
>
> 日期：2026-08-06
>
> 架构风格：Stateful Event-Driven Microkernel
>
> 适用范围：Luminous 后端运行时、后台任务、实时会话、设备端伴侣体验和能力扩展

## 1. 文档地位

本文档定义 Luminous 下一代虚拟伴侣运行平台的目标架构、模块边界、依赖规则和扩展契约。

它是目标架构的唯一规范性入口。其他文档仍有各自用途：

- `companion_app_architecture.md` 描述产品壳和早期 Companion Runtime 设想。
- `roleplay_companion_architecture.md` 描述角色拟合与陪伴底座的早期设计。
- `companion_foundation_implementation_roadmap.md` 记录阶段性实现路线和参考项目。
- `scheduler.md` 描述当前 scheduler 和 worker 的实现。
- `front_design/` 下的文档继续约束现有前端设计与实现。

当这些文档与本文讨论同一个目标架构问题且结论冲突时，以本文为准。本文不声称当前代码已经符合目标架构，也不替代迁移计划和具体实现契约。

## 2. 架构决策

Luminous 的总体架构不是广义 Agent Harness，也不是由 Memory、Harness、Tools、MCP 等平级系统拼接而成。

最终决策是：

> Luminous 是一个以长期存在的 Companion 为中心、有状态、事件驱动、可插拔的运行平台。

采用的架构风格是：

> **Stateful Event-Driven Microkernel Architecture**

核心判断如下：

1. `Companion` 是系统中心，模型调用不是系统中心。
2. 核心只拥有身份、状态一致性、事件、策略、生命周期和能力注册。
3. 记忆、语音、形象、陪看、日历等功能通过 Capability 接入，但核心领域状态有明确的唯一所有者。
4. Cognitive Harness 只是处理认知 Run 的一种核心 Capability。
5. Tool 是 Capability 的一种模型可见 handler。
6. MCP 是外部 Capability 的接入协议，不是内部架构。
7. Actor、Event Journal、Projection、Outbox 和 Workflow 是内部实现机制，不是并列产品架构。
8. 第一阶段使用模块化单体部署，不因采用微内核而提前拆成微服务。

## 3. 目标与非目标

### 3.1 目标

- 维持一个跨会话、跨设备、跨进程重启仍连续存在的 Companion 身份。
- 在文本、语音、点击、虚拟形象、共同观看和主动行为之间保持一致的关系与状态。
- 新增能力时主要增加 Capability，不修改 Kernel 的控制流。
- 允许本地 Python、MCP、远程 HTTP 和设备端能力使用同一套权限与追踪语义。
- 将模型输出视为候选意图，而不是未经验证的系统事实。
- 明确瞬时实时信号、会话状态和长期状态的不同生命周期。
- 支持幂等、重试、审批、恢复、审计、隐私删除和数据迁移。
- 保持模型提供商、实时传输、形象引擎和持久化实现可替换。

### 3.2 非目标

- 不把所有业务功能都改成模型 Tool。
- 不要求所有事件永久保留。
- 不要求第一阶段使用分布式 Actor、Kafka、Temporal 或微服务。
- 不让 LLM 直接拥有关系状态、记忆数据库、任务状态或外部凭据。
- 不把动画帧、音频包、鼠标移动等高频信号写入长期事件流。
- 不以多 Agent 协作为默认设计中心。
- 不通过抽象层兼容所有未知未来需求；扩展点必须服务于已识别的能力类别。

## 4. 统一术语

| 术语 | 定义 | 不是什么 |
|---|---|---|
| Companion Runtime Platform | Luminous 整体运行平台 | 不是单次模型请求包装器 |
| Kernel | 身份、生命周期、状态提交、事件路由、策略和能力注册的稳定核心 | 不包含具体语音、日历或形象业务 |
| Companion | 用户与一个虚拟伴侣之间长期存在的领域实体 | 不等同于聊天 session 或模型上下文 |
| Companion Actor | 对 Companion 命令进行有序处理的执行语义 | 不要求使用某个 Actor 框架 |
| Session | 一段有明确开始、参与者、渠道和结束条件的连续互动 | 不拥有长期关系事实 |
| Run | 对一个输入或后台触发进行的一次有界执行 | 不等同于整个 Companion 生命周期 |
| Capability | 可注册、可授权、可观测、可替换的功能单元 | 不一定对模型可见 |
| Cognitive Harness | 完成上下文组装、模型调用、Tool 循环、限额和结果验证的认知执行器 | 不是系统总体架构 |
| Tool | 允许模型在 Run 中选择调用的 Capability handler | 不是所有业务 API 的统一名称 |
| MCP | 连接外部 Capability Provider 的协议适配 | 不是内部模块之间的默认通信方式 |
| State Runtime | 拥有长期状态、记忆、投影、快照和保留策略的子系统 | 不是 LLM prompt 缓存 |
| Event Journal | 记录有领域意义且需要审计或重放的事件 | 不是所有日志和实时数据的永久仓库 |
| Projection | 从事件和权威记录计算出的当前读取视图 | 不是新的事实来源 |
| Act | Companion 对外产生的语义行为，如说话、表情、动作或通知 | 不是渲染引擎的逐帧参数 |
| Channel | Web、Android、语音、通知等输入输出通道 | 不拥有 Companion 状态 |

## 5. 系统上下文

```text
Users
  |
  v
Web / Android / Desktop / Voice / Notification
  |
  v
Channel and Device Adapters
  |
  v
+------------------------------------------------------+
| Luminous Companion Runtime Platform                  |
|                                                      |
| Kernel                                               |
|   -> Companion coordination                          |
|   -> command and event routing                       |
|   -> policy and capability registry                  |
|                                                      |
| State Runtime       Capability Runtime               |
| Cognitive Harness   Session and Realtime Runtime     |
| Workflow Runtime    Observability                    |
+------------------------------------------------------+
  |                 |                   |
  v                 v                   v
Models          MCP / HTTP          Database / Object Store
Providers       Providers           Notification / Media
```

系统由 Companion 驱动，而不是由 HTTP route、模型 SDK 或某个 Tool Registry 驱动。所有入口先被转换为 Command 或 Event，再进入相同的身份、策略、追踪和状态提交边界。

## 6. 核心领域对象

### 6.1 CompanionDefinition

描述一个 Companion 的稳定定义：

- `companion_id`
- 角色身份和人格配置引用
- 默认模型策略
- 默认 Capability 集合
- 安全和关系边界策略
- 形象与声音资源引用
- 版本和迁移信息

它描述“这个伴侣被如何定义”，不包含用户关系的动态状态。

### 6.2 CompanionInstance

描述某个用户与 Companion 的长期实例：

- `user_id + companion_id` 唯一身份
- 当前关系状态
- 当前情感和互动模式
- 记忆空间引用
- 开放话题和长期目标
- 已启用 Capability 和用户授权
- 当前状态版本

CompanionInstance 是长期状态的一致性边界。

### 6.3 Session

Session 表示一段连续互动，例如文本聊天、语音通话或共同观看：

- `session_id`
- CompanionInstance 引用
- 渠道和设备
- 会话参与者
- 开始、暂停和结束状态
- 瞬时上下文和媒体状态
- 活跃 Run 列表

Session 可以丢弃或压缩，不是长期关系的事实来源。

### 6.4 Run

Run 是一次有界执行：

- 用户消息 Run
- 语音 turn Run
- Tool continuation Run
- 主动行为评估 Run
- 记忆整理 Run
- 后台 Capability Run

每个 Run 必须具有：

- `run_id`、`trace_id` 和可选 `session_id`
- 输入事件或命令
- 可用 Capability 快照
- 权限和预算
- 状态读取版本
- 产生的候选 Act、事件和副作用意图
- 明确的完成、暂停、拒绝或失败状态

### 6.5 Capability

Capability 是唯一的功能扩展单位。它通过 manifest 声明：

- 稳定 ID 和版本
- 输入和输出 schema
- handler 类型
- 所需权限和数据范围
- 是否有外部副作用
- 是否需要审批
- 超时、重试和幂等策略
- 可运行位置：server、worker、realtime 或 device
- 健康检查和依赖

### 6.6 DomainEvent 与 CompanionAct

`DomainEvent` 表示已经发生并被系统接受的事实，例如：

- `UserMessageReceived`
- `MemoryObserved`
- `MemorySuperseded`
- `BoundaryDeclared`
- `RelationshipTransitionCommitted`
- `ProactiveContactHeld`
- `NotificationDelivered`

`CompanionAct` 表示准备对外执行的语义行为，例如：

- `SpeakAct`
- `GestureAct`
- `ExpressionAct`
- `GazeAct`
- `NotifyAct`
- `MediaReactionAct`

模型可以提出 Act，但 Policy 和领域 handler 决定是否接受、修改、延迟或拒绝。

## 7. Kernel 边界

### 7.1 Kernel 负责

- CompanionDefinition 和 CompanionInstance 的定位。
- 每个 CompanionInstance 的命令排序和状态版本控制。
- Run、Session 和 Capability 的生命周期。
- Command Bus、Event Bus 和 Query Bus 的契约。
- Capability 注册、发现、启用、停用和版本检查。
- Policy 执行、审批状态和权限上下文。
- 领域事件提交和 Outbox 原子写入。
- Trace、审计字段和关联 ID 的传播。
- 故障分类、取消和资源预算。

### 7.2 Kernel 不负责

- 构建具体 prompt。
- 决定某条记忆是否重要。
- 实现 STT、TTS、Live2D、VRM 或媒体解析。
- 直接连接某个模型或 MCP server。
- 保存具体 Capability 的私有业务表。
- 包含日历、提醒、语音、陪看等 feature-specific 分支。
- 渲染 UI 或动画。

### 7.3 Companion Actor 语义

Kernel 为每个 CompanionInstance 提供逻辑 Actor 语义：

1. 需要修改权威状态的 Command 按 CompanionInstance 有序提交。
2. 状态写入携带版本，冲突时拒绝或重新计算。
3. 模型、网络和媒体等长时间 I/O 不占用状态提交锁。
4. 外部 I/O 先产生 intent，由 activity 执行，再把结果作为 Event 返回。
5. 同一外部结果通过幂等键最多提交一次。

第一阶段可以使用进程内 mailbox、数据库版本字段和事务实现，不要求部署分布式 Actor runtime。

## 8. State Runtime 边界

### 8.1 State Runtime 负责

- CompanionInstance 的权威状态和版本。
- 关系、情感、边界、开放话题和当前目标。
- Working Context、短期会话状态和长期记忆。
- Memory 的抽取、验证、合并、纠正、替代、遗忘和检索。
- Domain Event Journal、Snapshot 和 Projection。
- 数据来源、证据、置信度、观察时间和生效时间。
- 数据保留、导出、脱敏和删除。

Memory Engine 是 State Runtime 的固定内部模块，不作为可替换的通用 Capability 注册。Capability 可以通过受限 port 查询记忆视图或提交 `MemoryObservation`，但只有 Memory Engine 能验证并提交长期记忆。

### 8.2 State Runtime 不负责

- 执行模型 Tool。
- 管理 MCP 连接。
- 发送通知或调用外部 API。
- 运行形象动画和音频流。
- 把每个模型输出自动当作长期记忆。
- 把 Projection 当成独立事实来源。

### 8.3 状态层级

```text
Ephemeral Signal
  动画帧、音频包、鼠标移动、partial transcript
  -> 仅存在于 device/realtime session

Session State
  当前通话、播放进度、临时话题、未完成 turn
  -> 会话结束后丢弃或压缩

Domain Event
  已接受的用户行为、关系变化、投递结果
  -> 按保留策略进入 Event Journal

Durable State and Memory
  当前关系、边界、长期事实和共同经历
  -> 权威记录和 Projection
```

### 8.4 Event Journal 不是纯 Event Sourcing

Luminous 使用事件日志和投影，但不要求所有状态只能通过永久不可变事件重建：

- 高敏感原文允许删除或密钥销毁。
- 错误记忆可以 supersede、redact 或 forget。
- 大型媒体和音频不进入事件日志，只保存受控引用或摘要。
- Projection 可以从事件与权威记录共同构建。
- Snapshot 用于限制重放成本。

## 9. Capability Runtime 边界

### 9.1 Handler 类型

一个 Capability 可以实现一个或多个 handler：

| Handler | 触发方 | 典型用途 |
|---|---|---|
| ToolHandler | Cognitive Harness 中的模型 | 查询日历、创建提醒、搜索外部内容 |
| CommandHandler | 用户、API 或其他受信任调用方 | 更新设置、确认操作、删除数据 |
| EventHandler | Event Bus | 关系更新、反馈处理、会话收尾 |
| ContextProvider | Context Engine | 提供记忆、当前日程、设备状态 |
| BackgroundHandler | Workflow Runtime | 记忆整理、主动触达、投递重试 |
| DeviceHandler | 设备 Runtime | 录音、屏幕共享、触摸检测 |
| RenderHandler | 设备 Runtime | 表情、动作、语音和界面呈现 |

Tool 只是其中一种 handler。没有模型选择需求的功能不应为了统一而包装成 Tool。

### 9.2 Capability Runtime 负责

- 加载和验证 manifest。
- 注册 handler 和 schema。
- 根据用户、Companion、Run 和渠道过滤可用能力。
- 执行权限、审批、预算、超时和取消。
- 统一记录输入摘要、结果摘要、耗时和错误。
- 管理 Capability 生命周期和健康状态。
- 将 Local、MCP、HTTP 和 Device provider 适配到统一契约。

### 9.3 Capability Runtime 不负责

- 决定长期状态的最终写入。
- 绕过 Kernel 直接互相调用具体实现。
- 信任外部 provider 声明的安全等级。
- 向模型暴露所有已安装能力。
- 保存用户 API key 到 prompt、trace 或 Tool result。

### 9.4 Capability 之间的通信

Capability 不依赖其他 Capability 的具体类。跨 Capability 协作只能通过：

- Query：读取明确的只读视图。
- Command：请求有状态操作。
- Event：广播已经发生的事实。
- Shared contract：使用 Kernel 定义的稳定值对象。

禁止通过全局 service locator 任意获取其他 Capability 的内部服务。

## 10. Cognitive Harness 边界

Cognitive Harness 是内置 Capability，负责需要模型推理的 Run。

### 10.1 负责

- 根据 Run 和 State Runtime 构建有预算的上下文。
- 选择本轮允许暴露的 ToolHandler。
- 调用模型并保留结构化响应、Tool call 和 usage。
- 执行有硬上限的 model-tool-result 循环。
- 验证结构化输出和 CompanionAct proposal。
- 处理模型重试、降级、取消和超限。
- 生成可追踪的候选事件与候选 Act。

### 10.2 不负责

- 直接写入关系、记忆或任务数据库。
- 自行跳过审批或安全策略。
- 持有长期凭据。
- 直接发送通知、播放语音或驱动动画。
- 把 prompt history 当作系统长期状态。
- 决定所有非认知事件的路由。

### 10.3 有界循环

每个认知 Run 必须配置：

- 最大模型请求数。
- 最大 Tool call 数。
- 最大连续失败数。
- token、费用和墙钟时间预算。
- 允许的 Tool 风险等级。
- 是否允许并行 Tool。
- 取消和用户打断语义。

Harness 返回 proposal，Kernel 和领域 handler 负责 commit。

## 11. MCP 和外部 Tool 边界

### 11.1 MCP 的定位

MCP 是 `CapabilityProviderAdapter`。外部 MCP Tool 在进入系统后必须转换为内部 ToolHandler，并附加本地策略。

```text
MCP Server
  -> MCP Client Adapter
  -> schema normalization
  -> local capability policy
  -> ToolHandler
  -> Cognitive Harness
```

### 11.2 必须执行的控制

- server allowlist 和连接级身份验证。
- 每个用户独立的授权与 secret scope。
- Tool 名称冲突和 namespace 处理。
- 输入 schema 二次验证。
- 输出大小限制、脱敏和内容验证。
- 超时、并发、频率和预算限制。
- 敏感操作审批。
- Tool 列表缓存失效与版本记录。
- 调用审计和 provider provenance。

内部 Capability 之间不默认使用 MCP。只有跨进程、第三方或需要协议隔离时才使用 MCP。

## 12. Session、Realtime 和 Device 边界

### 12.1 Session Runtime 负责

- 创建和结束文本、语音、共同观看等 Session。
- 管理参与者、渠道、设备、临时上下文和活动 Run。
- 将高频信号压缩成有领域意义的 Event。
- 维护 session lease、断线恢复和过期。

### 12.2 Realtime Runtime 负责

- 实时音频、视频和 data channel。
- VAD、turn detection、barge-in 和流式取消。
- partial transcript 和 streaming output。
- 媒体时间戳、播放同步和短期缓冲。
- 将实时结果转换为 Session Event。

Realtime Runtime 不拥有长期记忆和关系状态。

### 12.3 Device Runtime 负责

- 麦克风、摄像头、屏幕共享和设备权限。
- 本地形象渲染、hit test、表情和动作图。
- 音频播放、口型、viseme 和动画同步。
- 离线或弱网下的即时反馈。
- 设备端敏感数据的最小化上传。

点击角色时，设备应先完成低延迟反馈，再发送语义化 `TouchInteraction`；模型不参与逐帧渲染。

### 12.4 Embodiment Act

服务端产生语义 Act，而不是引擎参数：

```json
{
  "act_type": "speak_with_expression",
  "speech": "这个反转我也没想到。",
  "emotion": "surprised_amused",
  "gesture": "lean_forward",
  "gaze_target": "shared_media",
  "intensity": 0.7,
  "interruptible": true
}
```

设备端 RenderHandler 再映射到 Live2D、VRM 或其他形象引擎。

## 13. Workflow Runtime 边界

Workflow Runtime 处理跨请求、需要等待或恢复的执行：

- 主动联系评估与投递。
- reminder、routine 和 calendar 触发。
- 记忆整理和索引维护。
- 外部调用重试和补偿。
- 等待用户审批或反馈。
- 长时间共同活动的暂停与恢复。

Workflow Runtime 负责 durable timer、lease、retry、idempotency 和状态恢复，不负责认知决策本身。需要模型判断时，它启动 Cognitive Run；需要外部动作时，它启动 Capability activity。

## 14. Policy、Safety 和 Privacy 边界

Policy 是横切 Kernel 能力，任何入口和 Capability 都不能绕过。

### 14.1 Policy 负责

- 用户和设备身份。
- Capability enablement 和权限 scope。
- Tool 风险分级和审批。
- DND、冷却、频率和关系边界。
- 模型输入和输出安全检查。
- 屏幕、音频、媒体和位置等敏感上下文的同意。
- 数据保留、导出、删除和 redaction。
- 未成年人、高风险对话和现实支持策略。

### 14.2 信任边界

- 模型输出不可信。
- MCP server 和 Tool annotation 不可信。
- 客户端提交的审批结果必须通过服务端身份验证。
- 设备采集的数据只在明确授权的 Session 内有效。
- 外部内容不得自动成为用户事实或长期记忆。
- 日志和 trace 默认不记录 secret、完整 prompt 或敏感原文。

## 15. 数据所有权

| 数据 | 唯一写入所有者 | 允许读取方 |
|---|---|---|
| CompanionDefinition | Kernel 配置管理 | Kernel、Context、Device adapter |
| CompanionInstance 版本 | Kernel / Companion coordinator | 所有经过授权的内部模块 |
| 关系、情感、边界 | State Runtime 的领域 handler | Context、Policy、Projection |
| 长期记忆 | State Runtime 的 Memory Engine | Context、用户数据管理、授权 Capability |
| Session 状态 | Session Runtime | Cognitive、Realtime、Channel |
| Run 状态 | Kernel | Capability、Workflow、Observability |
| Tool/MCP 调用记录 | Capability Runtime | Trace、审计、用户审批 UI |
| Workflow 状态 | Workflow Runtime | Kernel、运维和相关 Capability |
| 动画帧和实时音频缓冲 | Device / Realtime Runtime | 当前 Session，默认不持久化 |
| 外部 secret | Secret provider | 被授权的 adapter，禁止进入模型上下文 |

同一数据不得由两个模块作为权威来源并行维护。Projection 和缓存必须标明来源版本。

## 16. 依赖规则

### 16.1 静态依赖方向

```text
Domain Contracts
      ^
      |
Kernel Interfaces
      ^
      |
Capability / State / Session Interfaces
      ^
      |
Concrete Capabilities and Adapters
      ^
      |
HTTP / Worker / Realtime / Device Entrypoints
```

规则：

1. Domain 不依赖模型 SDK、HTTP、SQLite、MCP 或前端代码。
2. Kernel 不依赖具体 Capability。
3. Capability 只依赖 contracts 和显式注入的 ports。
4. Adapter 实现 ports，但不能反向定义领域语义。
5. Entry point 只负责装配、协议转换和生命周期启动。
6. 任何跨边界写操作必须通过 Command 或明确的 port。

### 16.2 禁止的依赖

- Kernel 中按 feature 名称编写 `if voice`、`if calendar` 等分支。
- Capability 直接 import 另一个 Capability 的 infrastructure。
- HTTP route 直接写数据库表。
- 模型 client 直接调用 StateStore。
- Device adapter 直接提交长期记忆。
- Background worker 绕过 Policy 调用外部副作用。

## 17. 关键运行流程

### 17.1 文本对话

```text
Channel receives message
  -> UserMessageReceived command
  -> Kernel resolves CompanionInstance and policy
  -> Session Runtime opens/resumes session
  -> Cognitive Harness builds context
  -> model and bounded Tool loop
  -> proposes reply, Acts and memory observations
  -> Policy and domain handlers validate
  -> atomic event + state version + outbox commit
  -> Channel renders public result
```

### 17.2 Tool 或 MCP 调用

```text
Model proposes ToolCall
  -> Capability Runtime resolves ToolHandler
  -> schema and permission validation
  -> optional approval pause
  -> provider call with timeout and idempotency key
  -> sanitized ToolResult
  -> result returned to Cognitive Harness
  -> trace and audit event recorded
```

### 17.3 语音会话

```text
Device opens realtime session
  -> audio stream and VAD
  -> partial/final turn event
  -> Cognitive Run
  -> streaming speech and semantic embodiment Acts
  -> device TTS/audio, lip sync and animation
  -> interruption cancels active output
  -> session summary produces durable candidate events
```

### 17.4 虚拟形象点击

```text
Device hit test
  -> immediate local reaction
  -> semantic TouchInteraction event
  -> Session handler decides whether cognition is needed
  -> optional CompanionAct
  -> only meaningful interaction summary reaches durable state
```

### 17.5 共同观看

```text
Authorized media provider or screen share
  -> sampled media observations
  -> Session context and content summary
  -> Event/Context handlers
  -> optional Cognitive Run and MediaReactionAct
  -> shared experience candidate at session close
  -> retention policy decides what is stored
```

### 17.6 主动行为

```text
Durable timer or domain event
  -> Workflow resumes
  -> DND, cooldown, safety and relevance policy
  -> optional Cognitive Run drafts message
  -> NotifyAct written to outbox
  -> provider delivery
  -> receipt/feedback event
  -> state and strategy update
```

## 18. 一致性与可靠性

- 每次权威状态提交使用 CompanionInstance version。
- 状态、Domain Event 和 Outbox 在同一事务中提交。
- 外部副作用使用稳定 idempotency key。
- Tool、Workflow activity 和通知投递均有 timeout 和 retry policy。
- retry 只重试可安全重放或带幂等保护的操作。
- poison event 进入隔离队列，不能无限阻塞同一 Companion。
- Session 和 Workflow 使用 lease，进程退出后可重新认领。
- Cognitive Run 有硬预算，不能无限调用模型或 Tool。
- Realtime 丢包或断线不应破坏 durable state。
- Projection 可以重建，并记录 source version。

## 19. 可观测性与评测

统一关联字段：

- `trace_id`
- `run_id`
- `session_id`
- `companion_instance_id`
- `event_id`
- `capability_id`
- `tool_call_id`
- `workflow_id`

必须可观测：

- 模型调用、Tool 调用和审批链。
- 状态读取版本和提交版本。
- prompt/context 的结构摘要，而非默认记录完整敏感内容。
- Capability 延迟、错误、重试和熔断。
- Realtime 的首包延迟、打断响应和断线率。
- 主动行为的决策、hold、投递、回执和反馈。
- 记忆写入的来源、证据、纠正和删除。

架构验收不能只依赖单元测试数量。必须覆盖真实模型、真实 Capability、真实持久化、worker、设备通道和重启恢复链路。

## 20. 部署形态

### 20.1 第一阶段

采用模块化单体和少量独立进程：

```text
luminous-api
  Kernel + State + Capability + Cognitive + HTTP adapters

luminous-worker
  Workflow activities + outbox + maintenance

luminous-realtime-worker
  voice/media sessions; needed when realtime work begins

web/android device runtime
  capture + rendering + local interaction

SQLite or PostgreSQL + object storage
```

逻辑模块边界必须先成立，物理拆分延后。

### 20.2 拆分条件

只有出现以下证据时才拆出服务：

- Realtime 与 API 的资源模型和扩缩容需求明显不同。
- 某 Capability 需要独立安全边界或第三方运行环境。
- 单一数据库或进程已经成为经测量的吞吐瓶颈。
- 独立故障域带来的收益高于分布式一致性成本。
- 团队边界能够长期承担独立服务所有权。

## 21. 目标代码边界

目录名称可以在实施 ADR 中调整，但目标依赖关系应接近：

```text
luminous/companion/
  domain/             # values, commands, events, acts, policies
  kernel/             # coordination, lifecycle, buses, registry
  state/              # state ports, memory, journal, projections
  capabilities/       # capability contracts and first-party packages
  cognition/          # cognitive harness and model ports
  sessions/           # text, voice, media session orchestration
  workflows/          # durable workflow definitions and activities
  adapters/
    model/
    mcp/
    storage/
    notification/
    realtime/
    http/

apps/
  companion-web/
  companion-android/
```

`runtime_store.py` 一类大而全的存储实现应逐步拆成按所有权划分的 repository/port，但保持同一事务协调能力。

## 22. 扩展验收标准

新增一个 Capability 时，应满足：

1. 不修改 Kernel 领域控制流。
2. 通过 manifest 声明权限、风险、位置和生命周期。
3. 输入输出有版本化 schema。
4. 有超时、取消、错误和幂等语义。
5. 有最小权限的数据访问 port。
6. 有 trace、健康检查和审计摘要。
7. 外部副作用可审批、可恢复或可明确标记不可重试。
8. 删除 Capability 后，Kernel 和其他 Capability 仍可运行。
9. Capability 私有数据有迁移和删除策略。
10. 模型不可见的能力不注册为 Tool。

## 23. 架构验证场景

目标架构至少通过以下纵向场景：

1. 文本消息经过真实模型、记忆、关系状态、trace 和持久化，重启后连续。
2. 模型调用一个只读 Local Tool 和一个 MCP Tool，权限、超时和结果验证生效。
3. 写 Tool 在审批前暂停，批准后只执行一次，拒绝后不产生副作用。
4. Web 和 Android 同时发送事件时，Companion 状态无丢失更新。
5. 语音会话支持流式响应和用户打断，会话结束后只写入语义摘要。
6. 点击形象可本地即时响应，并在需要时触发语义互动。
7. 共同观看只在明确授权下采集上下文，删除 Session 后相关媒体数据可清理。
8. 主动 Workflow 在进程重启后恢复，遵守 DND、冷却和安全策略。
9. 模型 provider 或形象 renderer 替换时，Domain 和 Kernel 不修改。
10. 用户导出、纠正和删除记忆后，Projection 和检索结果一致。

## 24. 实施顺序

### 阶段 A：建立基线

- 完成并验证当前语音消息纵向链路。
- 固化当前行为、公开 DTO、数据格式和测试基线。
- 不再向旧 `CompanionRuntime` 增加新的大领域功能。

### 阶段 B：先定义 contracts

- 建立 Companion、Run、Session、Capability、Command、Event 和 Act。
- 建立 State、Model、Capability、Workflow 和 Channel ports。
- 建立 trace、policy、idempotency 和 version 语义。

### 阶段 C：旁路实现 Kernel

- 在不删除旧 Runtime 的情况下实现新 Kernel。
- 先迁移文本对话、状态提交、事件和 trace。
- 使用 feature flag 或 shadow execution 对比结果。

### 阶段 D：迁移第一方 Capability

- Memory 和 relationship state。
- reminder、calendar、life flow。
- proactive、notification 和 worker activities。
- 语音消息和 voice provider。

### 阶段 E：只在新架构建设新体验

- Realtime voice。
- Avatar 和 Embodiment。
- Shared media / co-watch。
- 外部 MCP Capability。

### 阶段 F：切换和删除旧 Runtime

- 完成数据迁移和回滚演练。
- Web、Android、worker 全部切换。
- 真实端到端和重启恢复验证通过后删除旧路径。

## 25. 尚未绑定的技术选择

以下选择需要独立 ADR，不在本文中提前固定：

- Pydantic AI、自研 Runner 或其他 Cognitive Harness 实现。
- SQLite、PostgreSQL 及具体事件/投影表结构。
- 进程内 mailbox、Dapr Actor 或其他 Actor runtime。
- 自研 durable job、Temporal 或其他 Workflow engine。
- LiveKit、Pipecat 或其他 Realtime transport/pipeline。
- Live2D、VRM 或其他 Avatar renderer。
- FastMCP 或其他 MCP client/server SDK。

选择这些工具时，必须服从本文定义的所有权、依赖和信任边界；工具不能反向决定领域架构。

## 26. 最终边界摘要

```text
Product center:
  Companion continuity

Architecture:
  Stateful Event-Driven Microkernel

Stable core:
  identity + lifecycle + ordered state commit + events + policy + registry

Extensibility unit:
  Capability

Model execution:
  Cognitive Harness capability

Long-term ownership:
  State Runtime

External tool protocol:
  MCP adapter

Realtime ownership:
  Session / Realtime / Device runtimes

Durable asynchronous work:
  Workflow Runtime

Initial deployment:
  Modular monolith with separate workers where resource models differ
```

这组边界的最终目的，是让 Luminous 在持续增加能力时仍保持一个稳定、可信、连续的 Companion，而不是让不断增加的模型、Tool、设备和外部服务逐步成为系统的实际控制中心。
