# 栖光 luminous 伴侣底座架构

本文基于 [AI Companion 参考调研](../research/ai_companion_landscape.md) 和当前仓库实现，定义 **栖光 luminous** 的情感陪伴底座架构。

栖光，是在某个人身边停驻的一束光。`role-play` 仍是仓库名；栖光是产品名和运行时目标。

核心前提：

1. 小说角色拟合要进入模型内部，作为人格来源。
2. AI 伴侣底座要独立于具体前端；前端只是一个可替换的壳。
3. 现在先用 `.env` 里的 OpenAI 兼容 API 跑通整个陪伴底座，等训练好的模型 adapter 接入后，再把模型适配层替换掉。

## 1. 我们要做的不是一个聊天页

真正的目标是一个长期伴侣系统，最少包含这些能力：

- 人格：角色风格、边界、价值、语气、应答偏好
- 记忆：原始对话、事实、事件、主题、回忆检索
- 状态：情绪、关系、亲密度、疲劳、活跃度
- 节奏：主动联系、提醒、心跳、沉默管理
- 感知：语音、屏幕、环境、设备、现实上下文
- 互动：共读、共听歌、日记、任务、仪式感
- 安全：风险识别、越界控制、可审计输出

现在的 `luminous/runtime/` 已经从最小聊天闭环扩展为伴侣底座层；后续重点是把这些能力产品化为网页调试台、app、Live2D/VRM 和语音体验。

## 2. 目标分层

建议把系统拆成 6 层。

### 2.1 Persona 层

负责“她是谁”。

- 小说角色拟合后的人格分布
- 说话风格
- 价值边界
- 关系边界
- 输出格式约束

这层最终应该尽量进入模型权重，而不是长期挂在 prompt 上。

### 2.2 Domain 层

负责“世界里有哪些稳定对象”。

- `CompanionState`
- `RelationshipState`
- `ConversationEvent`
- `MemoryRecord`
- `ProactiveSignal`
- `PerceptionSignal`

这层是未来扩展记忆、状态机、调度器的共同语言。

### 2.3 Application 层

负责“接到用户消息后怎么处理”。

- 组装上下文
- 读取记忆
- 更新关系与状态
- 生成回复候选
- 写入事件日志
- 触发主动消息条件

### 2.4 Infrastructure 层

负责“怎么接模型、存储、HTTP、文件、外部服务”。

- OpenAI 兼容模型调用
- 本地或远端存储
- HTTP API
- 静态前端服务
- 后续的语音/感知/通知接入

### 2.5 Client 层

负责“人怎么接触这个伴侣”。

- Web demo
- 手机壳
- 桌面壳
- 语音通道
- 未来的 Live2D / VRM / 电话模式

### 2.6 Tooling 层

负责训练、清洗、导出、回归。

- 小说转 SFT 的数据管线
- 训练前清洗
- QA
- 导出到训练框架
- 回归测试

## 3. 目标目录结构

当前已经开始落成的 runtime 新结构是：

```text
roleplay_companion/
  config.py
  application/
    service.py
  domain/
    output.py
    presence.py
  infrastructure/
    client.py
    http.py
```

后续建议继续长成下面这样：

```text
roleplay_companion/
  application/
    memory_service.py
    relationship_service.py
    scheduler.py
    perception_service.py
    voice_service.py
    activity_service.py
  domain/
    state.py
    memory.py
    events.py
    persona.py
  infrastructure/
    stores/
    model_adapters/
    transports/
    notifications/
```

`luminous/runtime/` 只保留兼容入口，不再作为长期主实现目录。

## 4. 现在最先做什么

最先做的不是前端，也不是声线，也不是多模态。

第一步应该是把“伴侣底座”钉成一个稳定的核心合同：

1. 定义 `ConversationEvent`、`CompanionState`、`MemoryRecord`、`RelationshipState`。
2. 增加一个本地持久化层，先用 JSONL 或 SQLite 都可以。
3. 让 `/api/chat` 先走这套状态读写，再返回回复。
4. 记录每次对话带来的状态变化、记忆写入和风险标记。

这样做的好处是：

- 后面换模型，不用动状态层
- 后面换前端，不用动核心逻辑
- 后面加主动联系、提醒、语音和感知，只是在这个底座上加新能力

## 4.1 当前已经落地的最小底座

这次重构后，`roleplay_companion` 已经具备一个简化但可持续扩展的底座：

- `state.json`：当前 `CompanionState`，包括 mood、energy、relationship、support_need、风险等级和最近主题
- `memory.jsonl`：简化版长期记忆，保留原始句子、来源事件和标签，后续可以换成更强的向量/图谱层
- `events.jsonl`：事件 ledger，所有 user / assistant / state snapshot / proactive 事件都带 trace_id
- `/api/state`、`/api/memory`、`/api/ledger`、`/api/proactive/tick`：可直接读状态、查记忆、看事件和触发主动联系
- 主动联系决策：先用 idle 时间、关系强度、支持需求和风险层做 hazard-like 打分，满足阈值才生成主动消息

这和调研仓库里的做法是同一方向的简化版：

- `Aura` 的长期记忆 / 情绪 / 关系模型
- `AI Companion Runtime` 的 trace + 分析 + memory / risk 分层
- `Paramecium` 的原文优先、文件即数据库
- `revive-companion` 的时间驱动主动联系思路

## 5. 第一阶段建议

### Phase 0：底座成形

- 把 runtime 包拆成 `domain / application / infrastructure`
- 建立稳定的状态和事件模型
- 增加记忆存储接口
- 增加导出接口
- 用 `.env` 的 API 先跑通

### Phase 1：记忆和关系

- 长期记忆写入和检索
- 关系状态推进
- 重要日期和日记
- 记忆摘要和可视化

### Phase 2：主动陪伴

- 心跳与低频主动联系
- 免打扰策略
- 纪念日和任务提醒
- 共读、共听歌、共同活动

### Phase 3：现实感知

- 语音输入输出
- 屏幕/网页/设备上下文
- 生活信号和情绪信号
- 更自然的响应节奏

### Phase 4：替换模型

- 保持同一套 runtime contract
- 把本地训练好的角色模型接进来
- 继续沿用记忆、关系、主动性和安全层

## 6. 这次重构的边界

这次先不要做的事情：

- 不重写前端
- 不把所有能力都塞进一个大 prompt
- 不把“像某个角色”误当成“完整伴侣”
- 不因为模型还没到位就推迟底座建设

这次要做成的事情：

- 让 runtime 目录有清晰边界
- 让后续模块有地方长
- 让现在的 API 能稳定接上未来模型
