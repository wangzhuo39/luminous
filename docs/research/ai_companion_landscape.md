# 栖光 luminous AI Companion 参考调研：从“角色拟合”到“长期陪伴”

本文面向 **栖光 luminous** 的产品实现阶段。`role-play` 是当前代码仓库名，栖光是产品名：在某个人身边停驻的一束光。当前前端只是 demo，不构成架构边界；真正需要稳定的是模型人格、记忆、关系状态、主动性、感知、语音和数据主权。

结论先行：

1. 小说角色拟合应该继续做，而且要进入模型内部，成为“人格与行为分布”的来源。
2. AI 伴侣不是 prompt 壳，也不是一次性聊天脚本，而是“模型 + 记忆 + 关系 + 主动性 + 感知 + 语音 + 生活节奏”的长期系统。
3. 没有一个开源项目能把所有层一次做全，最好的方式是按能力层拼装参考。
4. 在调研仓库里，最接近我们总体目标的项目是 `Aura`；最像运行时骨架的是 `AI Companion Runtime`；最值得借鉴的记忆架构是 `Paramecium` / `Aelios`；最值得借鉴的主动联系机制是 `revive-companion` / `dylan-heartbeat`。

## 1. 我们现在处在什么位置

当前仓库已经从“训练数据准备”进入“情感陪伴基础功能跑通”阶段。现在有三块基础：

- 角色数据侧：`luminous/training/pipeline/`、`luminous/training/data/`、`luminous/training/finetune/` 负责把小说文本加工成训练、推理与评估资产。
- 运行时侧：`luminous/runtime/` 已具备长期记忆、state engine、主动联系、提醒/日历、通知、worker、trace/outbox/export，以及任务、例行、活动会话、日记和统一时间线。
- 产品壳层：`apps/companion-web/` 是当前可用的网页入口；后续可演进为 PWA、app、Live2D/VRM、语音和伴侣空间。

现在的边界大致是：

- 已有：角色拟合数据管线、SFT 样本、长期记忆、关系/情绪/风险状态、主动联系、提醒/日历、通知适配、worker、导出、trace，以及日常任务/例行/活动/日记/时间线闭环。
- 后续缺口：可安装 PWA 与浏览器系统通知、共读等内容型共享活动、多角色/多关系槽位、语音、感知、app/Live2D 壳层，以及有真实用户需求后再做的数据导入/迁移 UI。

这意味着后续产品应该按“能力层”设计，而不是被当前 UI 结构锁死。

## 2. 参考仓库怎么分层看

我把 `awesome-ai-companion` 里最有价值的方向，拆成下面几层。

### 2.1 总体目标最接近的项目

| 项目 | 成熟度 | 借鉴点 | 对我们可落的功能 |
|---|---:|---|---|
| [Aura](https://github.com/gqy20/Aura) | ready | 跨会话长期记忆、情绪状态机、关系模型、提醒、MCP、图像理解、可选本地推理 | 关系状态、情绪状态、长期记忆、提醒系统、移动端伴侣主线 |
| [AI Companion Runtime](https://github.com/yf0522/ai-companion-runtime) | infra | WebSocket 流式、intent/emotion/risk/memory 引擎、工具调度、模型路由、后台记忆任务、trace 可观测性 | 伴侣运行时骨架、状态流、风险层、记忆作业、可观测性 |
| [LumiMuse](https://github.com/in30mn1a/LumiMuse) | ready | persona 创建、对话管理、长期记忆抽取、图像生成、用户数据导出 | persona 编辑器、对话归档、记忆抽取、数据导出 |
| [My Raze](https://github.com/Do-fei/my-raze) | adapt | 多角色聊天、流式输出、语境自拍、TTS/STT、mood/intimacy、主动通知 | 亲密度/关系推进、多模态输出、主动提醒、多角色空间 |
| [AIRI](https://github.com/moeru-ai/airi) | ready | Live2D/VRM、实时语音、跨平台 app、外部服务集成 | 具身壳、语音模式、桌面/网页伴侣皮肤 |
| [SullyOS](https://github.com/qegj567-cloud/SullyOS) / [ZeroChat](https://github.com/sh1nny0u/ZeroChat) / [AI Virtual Phone](https://github.com/xiaolongbao0709/ai-virtual-phone) | adapt | 手机式伴侣入口、Moments、主动消息、任务、角色卡、世界观/剧本模式 | 伴侣首页、动态流、日常节奏、通知入口、社交空间 |

### 2.2 长期记忆与连续性

| 项目 | 成熟度 | 借鉴点 | 对我们可落的功能 |
|---|---:|---|---|
| [Paramecium](https://github.com/Shitsuten/paramecium) | infra | 原文优先，向量只做索引，不用摘要替代原始对话 | 记忆要保留原始语料，检索要能回到原句 |
| [Aelios](https://github.com/wusaki0723/Aelios) | infra | 分层写入、定期抽取、夜间整合、六层记忆、可视化管理 | 记忆生命周期、分层沉淀、夜间整理 |
| [ai-memory-gateway](https://github.com/garan0613/ai-memory-gateway) | infra | OpenAI 兼容记忆网关、pgvector、分区缓存、记忆整合 | 记忆网关/中间层，直接挂在模型服务前 |
| [Ombre-Brain](https://github.com/P0luz/Ombre-Brain) | infra | 情绪标签、遗忘曲线、向量 + BM25 检索 | 带情绪权重的回忆、记忆衰减 |
| [Memory Constellations](https://github.com/ClaraShafiq/MemoryConstellations) | infra | 事实 -> 主题 -> 叙事片段的自组织记忆 | 事实/主题/事件三层记忆 |
| [forge-reload](https://github.com/Vivi-Seth/forge-reload) | adapt | 会话续接、尾部事件复制、父子链修复 | 断点续聊、会话迁移、上下文续接 |

### 2.3 主动联系与陪伴节奏

| 项目 | 成熟度 | 借鉴点 | 对我们可落的功能 |
|---|---:|---|---|
| [revive-companion](https://github.com/pearthink123/revive-companion) | infra | 用概率/贝叶斯/信息增益决定何时打扰 | 主动联系时机，不靠固定 cron |
| [dylan-heartbeat](https://github.com/callie0313/dylan-heartbeat) | adapt | 周期唤醒、注入上下文、保留时间线、Bark 推送 | 心跳、低频主动问候、节奏连续性 |
| [astrbot_plugin_private_companion](https://github.com/menglimi/astrbot_plugin_private_companion) | ready | 连续 persona 状态、日程、重要日期、日记、低频主动消息 | 日常生活节奏、纪念日、日记、主动关怀 |
| [astrbot_plugin_proactive_chat](https://github.com/DBJD-CR/astrbot_plugin_proactive_chat) | ready | 上下文感知、DND、TTS、独立 WebUI | 可控打扰、免打扰、提醒策略 |

### 2.4 语音与具身存在

| 项目 | 成熟度 | 借鉴点 | 对我们可落的功能 |
|---|---:|---|---|
| [GPT-SoVITS](https://github.com/RVC-Boss/GPT-SoVITS) | infra | 少样本音色克隆 | 角色声音、声音一致性 |
| [Callhome](https://github.com/Cheiineeey/callhome) | adapt | 外呼、语音信箱、可取消挂断、睡前读物、情绪标签 | 电话式陪伴、可打断/可回退的通话体验 |
| [voice-mcp](https://github.com/Yinglianchun/voice-mcp) | adapt | `speak` 工具、TTS 供应商切换、音频播放器 | 语音能力作为工具层接入 |
| [AIRI](https://github.com/moeru-ai/airi) | ready | Live2D/VRM、语音、跨平台 | 具身化壳层和声音出口 |
| [Ghost Vessel](https://github.com/ghdtjrtka/ghost-vessel) | adapt | 低 GPU 的视频 avatar 参考 | 轻量视觉存在 |

### 2.5 感知与现实上下文

| 项目 | 成熟度 | 借鉴点 | 对我们可落的功能 |
|---|---:|---|---|
| [gaze](https://github.com/jiangxi1129/gaze) | adapt | 屏幕感知、OCR、截图、滚动上下文 | 看见用户在做什么 |
| [ears](https://github.com/eveacla11/ears) | adapt | 声音语气分析，和用户基线比较 | 识别疲惫、紧张、兴奋等语气变化 |
| [voice-familiarity](https://github.com/akinia0315/voice-familiarity) | infra | 说话人熟悉度/身份关系上下文 | 谁在说话、熟不熟、是不是常用联系人 |
| [always-here](https://github.com/Cheiineeey/always-here) | adapt | Apple Watch / iPhone 的心率、位置、活动、环境音、照片 | 现实状态输入，前提是用户同意 |
| [OpenCLI](https://github.com/jackwener/OpenCLI) | adapt | 浏览器、网站、Electron app 变成可控原语 | 外部应用与网页接入，作为环境感知和行动桥 |

### 2.6 共同行为、仪式感与日常陪伴

| 项目 | 成熟度 | 借鉴点 | 对我们可落的功能 |
|---|---:|---|---|
| [Phosphene](https://github.com/3lmglow/Phosphene) | ready | 任务、奖励、打卡、积分、奖励兑换、审计 | 共同完成任务、关系积分、仪式化互动 |
| [reading-nook](https://github.com/zzyyksl/reading-nook) | ready | 人和 AI 一起读书、做批注、保留章节上下文 | 共读、共批注、小说陪读 |
| [co-reading-kit](https://github.com/Youxuuuuu/co-reading-kit) | infra | 文本切块、只读相关片段、长期笔记 | 阅读记忆、内容引用、上下文导读 |
| [Duetto](https://github.com/avisforevelyn/Duetto) | adapt | 两人一起听歌，记住分享过的歌曲 | 一起听歌、共用歌单、回忆触发 |
| [Journal](https://github.com/BomBomLab/Journal) | infra | 时间线/日记/todo 可视化 | 伴侣时间线、共同生活日志 |

### 2.7 数据主权、人格可移植性与导出

| 项目 | 成熟度 | 借鉴点 | 对我们可落的功能 |
|---|---:|---|---|
| [character-card-spec-v2](https://github.com/malfoyslastname/character-card-spec-v2) / [v3](https://github.com/kwaroran/character-card-spec-v3) | infra | 人格卡标准化 | persona 可导入、可导出、可迁移 |
| [immortal-skill](https://github.com/agenmod/immortal-skill) | adapt | 从多源资料中蒸馏人格、记忆、风格 | 角色/用户资料蒸馏、带证据的人格包 |
| [chatgpt-exporter](https://github.com/pionxzh/chatgpt-exporter) / [Claude-Conversation-Exporter](https://github.com/socketteer/Claude-Conversation-Exporter) | ready | 对话导出 | 用户可控导出、备份、迁移 |

## 3. 最值得优先参考的组合

如果只选少数几个来做主参考，我建议这样搭：

1. 总体产品目标：`Aura`
2. 运行时与观测：`AI Companion Runtime`
3. 记忆底座：`Paramecium` + `Aelios` + `ai-memory-gateway`
4. 主动联系：`revive-companion` + `dylan-heartbeat`
5. 壳层/入口：`SullyOS` + `ZeroChat` + `AIRI` + `AI Virtual Phone`
6. 语音：`GPT-SoVITS` + `Callhome` + `voice-mcp`
7. 共享活动：`Phosphene` + `reading-nook` + `Duetto`

### 为什么 `Aura` 最贴近我们

`Aura` 不是最强的某一项，但它同时覆盖了：

- 长期记忆
- 情绪状态机
- 关系模型
- 提醒
- MCP
- 可选本地推理

这和我们真正想做的事情最接近：不是只让角色“像”，而是让伴侣“活着”，并且随着关系推进持续变化。

### 为什么 `AI Companion Runtime` 值得当骨架

它更像一个运行时框架，而不是单一应用。对我们最有价值的是它的思路：

- 输入不只是消息，还有情绪、风险、记忆、工具调用
- 输出不只是回复，还有 trace 和后台记忆任务
- 模型不是唯一能力，路由、调度、观测同样重要

这正适合做长期伴侣系统的后端中枢。

## 4. 我们应该补成什么功能

下面这组功能，基本可以视为“AI 伴侣完整度”的主干。

### P0：底座（已基本完成）

- 长期记忆：原文记录、事实记忆、主题记忆、事件记忆、可检索原句。
- 关系状态：亲密度、信任、依赖、边界感、共同历史。
- 情绪状态：当下 mood、疲劳、兴奋、低落、稳定度。
- 主动节奏：心跳、低频打招呼、提醒/日历、长时间未互动的自然关怀。
- 数据主权：导出、审计与编辑/遗忘已具备；导入、迁移留待真实需求出现后再做。
- 安全层：风险识别、越界提醒、可回溯 trace。

### P1：陪伴生活流（已完成基础闭环）

- 日记 / 时间线 / 重要日程 / 提醒（已实现）
- 睡前问候、早安、饭点等可配置的主动节奏（已具备调度基础）
- 共同任务、例行与共同打卡（已实现）；共读、共听歌留待后续。
- 个人偏好记忆、记忆编辑与遗忘控制（已实现）
- 多角色 / 多关系槽位（后续）

### P2：让它进入现实世界

- 语音对话
- 外呼 / 接听 / 语音信箱
- 屏幕感知、OCR、网页/应用上下文
- 语气识别、情绪识别、心率/活动等可选传感器输入
- 位置 / 天气 / 通勤 / 日程等生活上下文

### P3：让它有陪伴的生活感

- 共同看书、批注、复盘
- 一起听歌、做歌单
- 轻量任务和奖励系统
- 关系事件和纪念物
- 伴侣空间、房间、手机壳、桌宠、Live2D/VRM

## 5. 对当前仓库的建议架构

前端后期可以随时重做，所以建议把系统拆成下面几层：

1. `persona` 层：角色人格、语言风格、价值边界，尽量进入模型内部。
2. `memory` 层：原文日志、事实、主题、事件、长期回忆。
3. `state` 层：情绪、关系、疲劳、亲密度、共同历史。
4. `scheduler` 层：主动联系、提醒、节奏控制、DND。
5. `perception` 层：语音、屏幕、设备、位置、健康、环境输入。
6. `voice` 层：TTS/STT/电话通道。
7. `activity` 层：共读、共听、任务、打卡、日记、小游戏。
8. `client` 层：Web、手机、桌面、phone-shell、Live2D/VRM 都可以替换。

建议的 API 方向也应该从 demo 聊天接口，扩展成能力接口，而不是把所有状态都塞进一个 prompt 里：

- `/api/chat`
- `/api/state`
- `/api/memory/query`
- `/api/memory/write`
- `/api/relationship/update`
- `/api/proactive/tick`
- `/api/voice/speak`
- `/api/perception/ingest`
- `/api/export`

## 6. 最终判断

如果目标是“让喜欢的小说角色真正长在模型里”，那我们的核心工作仍然是训练与评估角色人格。

如果目标是“做一个真正可长期陪伴的 AI 伴侣”，那必须再叠上这几层：

- 记忆
- 关系
- 情绪
- 主动性
- 感知
- 语音
- 生活节奏
- 数据主权

所以我建议把项目目标表述为：

> 用小说角色作为人格起点，做成一个长期陪伴型 AI 伴侣系统。

这比“一个会像某个角色说话的聊天 API”更大，也更贴近最终产品。

## 7. 主要参考来源

- `awesome-ai-companion`：<https://github.com/DasterProkio/awesome-ai-companion>
- 当前项目总览：`docs/project_overview.md`
- 当前运行时：`luminous/runtime/server.py`、`luminous/runtime/service.py`、`luminous/runtime/presence.py`
- 当前 demo 前端：`apps/companion-web/README.md`
