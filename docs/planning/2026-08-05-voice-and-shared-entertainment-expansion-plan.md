# 栖光下一阶段产品拓展计划：语音存在与共同刷内容

> 状态：当前产品主线  
> 制定日期：2026-08-05  
> 适用基线：长期记忆、关系/情绪状态、主动联系、Android 通知、来信、活动、日记和时间线已经具备基础实现  
> 上游调研：[开源 AI Companion 生态复调研](../research/ai_companion_open_source_refresh_2026-08-05.md)  
> 产品决策：原“共读优先”改为覆盖面更大的“共同刷内容”；读书可保留为未来内容类型，不再作为下一阶段主场景。

## 1. 目标与最终形态

下一阶段不再增加一批彼此独立的小功能，而是围绕一条完整的陪伴体验推进：

> 用户用声音和栖光交流 → 两个人一起刷帖子或看视频 → 对同一个内容产生反应和共同梗 → 有价值的瞬间进入共同记忆 → 栖光之后能自然提起、续看或发来相关来信。

这一阶段要让栖光从“能聊天、能记忆、会主动联系”进入：

- **能听见**：用户可以说话，栖光可以用稳定的角色声音回复或留下语音来信。
- **能一起消遣**：不是把链接扔进问答框，而是围绕同一条帖子、同一个视频时间点产生连续互动。
- **能形成共同历史**：记住的是“我们当时为什么笑、聊到了谁、以后想看什么”，而不只是平台标题和摘要。
- **能克制地在场**：用户决定栖光是安静陪看、偶尔回应还是积极讨论；不能每几秒打断内容。
- **能迁移到其他内容平台**：小红书、B 站、YouTube 或普通网页只是 adapter，不成为核心领域模型。

## 2. 交付顺序

建议按四个里程碑推进：

| 里程碑 | 核心结果 | 建议周期 | 是否阻塞下一阶段 |
| --- | --- | ---: | --- |
| M0：共享媒介底座 | 统一音频、帖子、视频、时间点和共同瞬间的数据语义 | 1–2 周 | 是 |
| M1：语音存在 v1 | 按住说话、转写校正、角色语音回复、主动语音来信 | 3–4 周 | 是 |
| M2：共同刷内容 v1 | 分享帖子/视频、共看会话、时间点互动、共同瞬间与回顾 | 4–6 周 | 是 |
| M3：平台与现实上下文 adapter | 视频字幕/元数据、网页内容、小红书等平台适配、低敏上下文 | 3–5 周 | 否，可逐项启用 |
| M4：稳定性与小规模验证 | 真机、真实模型、真实内容和真实通知的连续使用验证 | 2 周起 | 上线门禁 |

周期按单一主开发线估算，不包含第三方平台审核、模型采购、音色授权或应用商店审核时间。M1 与 M2 的界面探索可以并行，但数据模型、删除语义和公共 DTO 必须先在 M0 收敛。

如果需要压缩范围，保留顺序为：

1. 语音输入与语音回复；
2. 从 Android 分享帖子/视频到栖光；
3. 围绕单条内容建立共同会话；
4. 视频时间点互动；
5. 主动续看和跨平台 adapter。

## 3. 范围边界

### 本阶段必须完成

- Android 语音输入、转写确认、角色语音输出。
- 主动来信可附带语音，同时保留文本降级。
- Android 分享入口：用户可以把一个链接、标题、选中文本、图片或视频页面分享到栖光。
- 建立“共同刷内容”会话，而不是一次性链接总结。
- 帖子级和视频时间点级互动。
- 安静陪看、自然回应、积极讨论三种互动节奏。
- 共同瞬间、会话回顾、稍后再看和主动续接。
- 新媒介产生的记忆具有来源、可见范围和删除路径。
- 真实模型、真机、重启、断网、后台恢复和通知链路验收。

### 本阶段明确不做

- 不接管用户小红书账号，不自动点赞、收藏、评论、关注或发布。
- 不模拟无限滚动，不批量抓取推荐 feed，不绕过登录、验证码、平台签名或访问限制。
- 不默认录屏、常驻截图、后台麦克风或持续监听。
- 不保存完整视频副本；优先保存 URL、授权获得的元数据、时间点和用户主动保留的片段说明。
- 不默认做声音克隆、声纹识别或情绪诊断。
- 不做外呼电话、双工实时通话、Live2D/VRM、多人格和角色市场。
- 不用积分、连续签到或惩罚机制驱动用户刷内容。

## 4. M0：共享媒介底座

M0 的目标不是先做一个大而全的媒体系统，而是避免语音、帖子和视频分别形成一套互不相通的数据链路。

### 4.1 核心领域对象

#### `MediaArtifact`

表示用户与栖光共同接触的一项内容：

- `artifact_id`
- `kind`: `voice` / `post` / `short_video` / `long_video` / `webpage` / `image`
- `source_provider`: `xiaohongshu` / `bilibili` / `youtube` / `web` / `local`
- `canonical_url`
- `title`
- `creator`
- `duration_ms`
- `content_hash`
- `visibility`
- `capture_method`: `android_share` / `manual_url` / `provider_adapter`
- `created_at` / `updated_at`
- `deleted_at`

原则：核心只认识内容类型和来源，不认识某个平台的私有字段；平台字段进入 `provider_metadata`，不得直接渗入 memory/state 主模型。

#### `MediaAnchor`

表示双方谈论的准确位置：

- 帖子：正文片段、图片序号、评论引用。
- 短视频：毫秒时间点或时间范围。
- 长视频：时间点、字幕范围或章节。
- 网页：选中文本与稳定 selector 的组合。
- 图片：区域描述；首版不要求像素级框选。

任何进入共同记忆的内容反应都应尽可能关联 `anchor_id`，避免以后只剩一条无法核实的摘要。

#### `SharedMediaSession`

表示一次“一起刷/一起看”：

- `session_id`
- `activity_id`：关联现有 `ActivitySession`
- `status`: `planned` / `active` / `paused` / `completed` / `abandoned`
- `interaction_mode`: `quiet` / `natural` / `chatty`
- `artifact_ids`
- `started_at` / `last_active_at` / `ended_at`
- `resume_anchor_id`
- `summary`
- `memory_policy`

#### `CompanionReaction`

记录栖光针对某个 anchor 的反应，但不是所有反应都写长期记忆：

- `reaction_id`
- `anchor_id`
- `type`: `comment` / `question` / `laugh` / `association` / `silence`
- `content`
- `trigger`: `user_requested` / `natural_pause` / `session_end`
- `delivery_mode`: `text` / `voice` / `ambient`
- `trace_id`

`silence` 是正式结果：安静陪看时，系统应能记录“判断不打断”，而不是为了显示存在感强行生成内容。

#### `SharedMoment`

只有用户主动保留、双方明确形成共同意义或会话结束时确认的内容才进入共同历史：

- `moment_id`
- `session_id`
- `anchor_ids`
- `human_note`
- `companion_note`
- `why_it_matters`
- `memory_ids`
- `timeline_event_id`
- `privacy_scope`

### 4.2 复用现有模块

| 现有模块 | M0 中的复用方式 |
| --- | --- |
| `ActivitySession` | 承载共同刷内容会话的生命周期，不另建第二套活动状态机 |
| `Diary` / `Timeline` | 保存用户确认的共同瞬间和会话回顾 |
| `Reminder` | 稍后再看、续看、等更新和共同回顾 |
| Memory evidence | 关联 URL、anchor、会话和用户确认，而不是只存 LLM 摘要 |
| StateEngine | 只接收经过归一化的互动结果，不直接消费平台原始数据 |
| ProactiveEngine / outbox | 续看邀请、相关内容回想和语音来信；继续遵守 DND/cooldown |
| Action preview/confirm | 将来需要平台读取或外部操作时，复用预览与确认语义 |

### 4.3 M0 交付物

- 领域模型与序列化格式。
- SQLite/存储迁移和回滚。
- public DTO 与内部 trace 边界。
- artifact/anchor/session/moment 的增删改查服务。
- 来源与派生数据删除图。
- Android 分享 payload 的规范化接口。
- 单元测试、存储往返测试和删除测试。

### 4.4 开源参考

| 参考仓库 | 借鉴内容 | 不照搬 |
| --- | --- | --- |
| [Duetto](https://github.com/avisforevelyn/Duetto) | 同步媒体会话、歌词时间点、presence note 聚合为共同歌曲记忆 | 网易云账户和具体音乐 API 不进入核心模型 |
| [film-matinee](https://github.com/idleprocesscc/film-matinee) | 视频 visual sheet、字幕 sidecar、时间线切片和共享批注 | 不在首版复制完整影片处理管线 |
| [coread](https://github.com/meowmana/coread) | 稳定内容位置、双方批注、进度和导出语义 | 不把书籍/分页作为首发产品形态 |
| [Ocean](https://github.com/fishwithoctopus/Ocean) | 活动房间、通知、媒体与外部记忆的组合方式 | source-available 代码不直接复制 |

## 5. M1：语音存在 v1

### 5.1 用户体验

#### 语音输入

1. 用户在聊天页按住说话。
2. 松开后显示音频时长和转写进度。
3. 转写完成后允许用户校正，尤其是人名、时间、否定词和专有名词。
4. 用户确认后，校正文本进入现有 `CompanionRuntime.chat`。
5. 原音频、原始转写和校正文本保持可追溯但分开删除。

#### 语音回复

- 每条回复默认仍有文本。
- 用户可以手动播放角色语音，自动播放默认关闭。
- 支持语速和情绪强度的少量预设，不在首版开放复杂音色参数。
- TTS 失败时立即降级为文本，不重试到阻塞聊天。

#### 主动语音来信

- outbox 内容可附带一个延迟生成的语音 artifact。
- Android 通知只显示安全的文本摘要；点击后进入对应来信。
- 音频未生成成功不影响文本来信投递。
- 用户可以关闭“主动来信自动生成语音”，而不必关闭全部主动联系。

### 5.2 后端工作包

- `SpeechToTextProvider` 接口和首个中文实现。
- `TextToSpeechProvider` 接口和首个角色音色实现。
- `AudioArtifactStore`：路径、格式、时长、哈希、过期和删除。
- 上传大小、音频格式、时长和并发限制。
- ASR/TTS job、幂等键、重试和失败降级。
- 音频 DTO 脱敏，禁止本地路径、provider key 和内部 prompt 外泄。
- export/backup/restore 中音频的包含策略。

### 5.3 Android 工作包

- 麦克风权限说明、拒绝后的可恢复流程。
- 按住录制、取消手势、时长和音量反馈。
- 上传、转写、校正、发送和失败重试状态。
- 音频流式或分段播放、暂停、重播和耳机路由。
- 后台来信中的音频加载和深链。
- 锁屏、蓝牙耳机、来电打断、App 切后台和进程恢复测试。

### 5.4 记忆与安全约束

- 长期记忆的规范输入是用户确认后的文本，不是未经确认的 ASR。
- 原始音频默认不参与 embedding。
- 音高、语速、环境声和声纹默认不写长期状态。
- 声音情绪只能作为本轮低置信提示，不得自动推导“用户长期抑郁/焦虑”等结论。
- 角色专属音色需要记录素材来源和授权；不默认提供声音克隆。

### 5.5 开源参考

| 参考仓库 | 借鉴内容 | 不照搬 |
| --- | --- | --- |
| [AionsHome](https://github.com/death34018-hue/AionsHome) | Android 原生录音桥、WebRTC VAD、SenseVoice、CosyVoice、前台 WebSocket 恢复 | 不照搬 4,000 行级别的单体 push service 和常驻设备监控 |
| [Callhome](https://github.com/Cheiineeey/callhome) | 语音信箱、拒接原因、DND、挂断缓冲、通话记录和音频失败路径 | 外呼和 iOS 模拟铃声后置 |
| [ears](https://github.com/eveacla11/ears) | 使用用户自身中位数/MAD 的个人语气基线 | 首版不把语气识别作为核心状态输入 |
| [voice-mcp](https://github.com/Yinglianchun/voice-mcp) | TTS provider 切换、统一 `speak` 语义和播放面板 | 不把 MCP 作为 App 内部语音主协议 |
| [AIRI](https://github.com/moeru-ai/airi) | 实时音频、跨端输入输出和未来 lip-sync adapter | 不采用其未完成的 memory 路线 |

### 5.6 M1 验收门槛

- 文字与语音入口经过同一 runtime，人物设定、记忆召回和安全策略一致。
- 人名、时间、否定词的关键实体转写错误有独立统计。
- TTS/ASR 失败不会导致消息丢失或重复记忆写入。
- 删除原音频后，缓存、备份和临时文件按策略清理。
- 真机覆盖录音权限拒绝、断网、切后台、重启和耳机切换。
- 主动语音来信不会绕过 DND、daily limit、风险 hold 和用户关闭项。

## 6. M2：共同刷内容 v1

### 6.1 首版产品形态

共同刷内容不是在栖光里复制一个小红书或视频 App。首版只提供三个入口：

#### 入口 A：分享到栖光

用户在小红书、B 站、YouTube、浏览器或相册中点击系统分享，选择“栖光”：

- 接收 URL、标题、选中文本、预览图或本地图片。
- 创建或加入一个 `SharedMediaSession`。
- 栖光先确认“你想一起看看，还是只想让我记一下？”
- 用户选择安静陪看、自然回应或积极讨论。

这是必须优先做的入口，因为它不要求接管平台账户，也不会改变用户原有刷内容习惯。

#### 入口 B：一起看视频

- 用户粘贴或分享视频链接。
- App 展示可用的标题、封面、作者、时长和字幕状态。
- 播放时允许用户在当前时间点呼出栖光、说一句话或点“记住这个”。
- 栖光的回应绑定视频时间点；恢复会话时能回到对应位置。
- 无字幕时首版只使用用户主动提供的描述或选中片段，不假装看过完整视频。

#### 入口 C：内容卡片会话

对无法内嵌或不适合持续同步的平台内容：

- 以内容卡片呈现用户分享的信息。
- 用户可以追加截图、选中文本、语音说明或“我为什么想给你看”。
- 栖光只针对已得到的材料回应，并清楚表达自己没有看到的部分。
- 多条卡片可以形成一次“今晚一起刷了什么”的 session。

### 6.2 三种陪伴节奏

#### 安静陪看

- 默认不主动评论。
- 用户呼叫、暂停或明确标记时才回应。
- 结束时可生成一句轻量回顾。

#### 自然回应

- 只在内容自然停顿、用户明显反应或话题与已有共同历史强相关时回应。
- 连续两次未得到回应后自动降频。
- 默认推荐模式。

#### 积极讨论

- 用户明确开启后，栖光可以提出问题、联想旧事和推荐下一条相关内容。
- 仍受最大频率和会话内打断预算限制。
- 退出会话后自动恢复默认模式，不永久提高主动频率。

### 6.3 核心用户闭环

> 分享帖子或视频 → 选择陪伴节奏 → 围绕准确内容/时间点互动 → 用户标记共同瞬间 → session 结束生成可编辑回顾 → 进入 Timeline/Diary → 之后在合适时续看或提起。

例子：

- 用户分享一条小红书旅行笔记，说“这个房间好像我们之前聊过的那家民宿”。栖光基于用户共享的图片/文字和已有记忆回应，用户点击“留作共同瞬间”。两周后计划旅行时，栖光可以引用这条经过确认的 moment。
- 用户看 B 站视频到 08:42 时暂停，说“这段太像你了”。系统保存 08:42 的 anchor、用户话语和栖光回应，而不是把整个视频摘要写进长期记忆。
- 用户连续分享几条搞笑帖子。会话结束时，栖光生成“今晚我们笑得最久的是哪一条”的可编辑回顾；用户可以全部删除或只保留一条。

### 6.4 共同记忆策略

默认不把浏览历史全部记住。只允许以下内容进入长期记忆：

- 用户点击“记住这个”。
- 用户明确说“以后还想一起看/这对我很重要”。
- 双方完成一次 session 后，用户确认保留回顾。
- 已有 open loop 被内容明确承接，并通过证据校验。

默认不进入长期记忆：

- 平台推荐列表和连续滑动记录。
- 用户停留时长、滑动速度和隐式兴趣画像。
- 未经用户确认的评论区内容。
- 模型根据封面或标题猜测的内容。

### 6.5 主动续接

主动消息只允许基于明确来源：

- 用户保存了“稍后一起看”。
- session 中形成了未完成话题。
- 用户要求等待作者更新或某个时间继续。
- 某个共同瞬间与当前日程/纪念日明确相关。

主动来信示例应包含可理解原因：

> “你昨晚把那条猫咪视频留在了 08:42，还说想让我提醒你给朋友看。要继续吗？”

不能发送：

> “我发现你最近一直刷旅行内容，猜你想出去玩。”

后一种做法依赖隐式行为监控，不属于当前范围。

### 6.6 开源参考

| 参考仓库 | 借鉴内容 | 不照搬 |
| --- | --- | --- |
| [Duetto](https://github.com/avisforevelyn/Duetto) | 双方同步播放、歌词时间点提问、presence note 聚合为歌曲共同记忆 | 不绑定网易云或音乐账户体系 |
| [film-matinee](https://github.com/idleprocesscc/film-matinee) | 视频字幕 sidecar、visual sheet、按时间线读取和共享批注 | 不保存/分发完整版权视频 |
| [whale-browser-extension](https://github.com/whale-Yd00/whale-Yd00-whale-browser-extension) | 用户选择网页内容后注入 AI 上下文的浏览器桥 | 不默认读取整个浏览历史或页面隐私内容 |
| [Ocean](https://github.com/fishwithoctopus/Ocean) | 媒体房间、通知、音乐和 memory hook 组成长期活动 | 只借产品结构，避免直接复制 noncommercial source-available 代码 |
| [AionsHome](https://github.com/death34018-hue/AionsHome) | 音乐、聊天、多端和统一时间线的实际集成 | 不照搬其高度耦合的全功能主页 |
| [OpenCLI](https://github.com/jackwener/OpenCLI) | 将已登录浏览器页面转为结构化只读接口；可作为未来平台 adapter 研究样本 | 不把桌面 Chrome 登录态或任意网页控制作为 Android 首版依赖 |
| [coread](https://github.com/meowmana/coread) | 稳定内容位置、双方评论、进度和导出 | 只借 anchor/annotation 语义，不以读书作为首发受众 |

### 6.7 M2 验收门槛

- Android 分享入口覆盖 URL、文本、图片和异常 payload。
- 同一内容重复分享不会产生不可控的重复 artifact。
- 视频反应能稳定回到正确时间点；帖子反应能回到正确卡片/片段。
- 模型无法取得正文/字幕时，会明确说明材料不足，不编造“看过”。
- 三种互动节奏真实改变打断频率；安静模式零主动插话。
- session 回顾默认可编辑、可放弃，未确认内容不写长期记忆。
- 删除 artifact 时能预览并清理 anchor、moment、timeline 和派生 memory。
- 主动续接只使用明确的稍后再看/open loop，不从隐式刷帖行为推断。

## 7. M3：平台与现实上下文 adapter

### 7.1 Adapter 契约

每个平台 adapter 只负责把外部内容规范化为 `MediaArtifact` 和 `MediaAnchor`：

- `can_handle(input)`
- `resolve_metadata(input, consent)`
- `resolve_content(input, scope, consent)`
- `resolve_timed_text(input, consent)`
- `refresh(artifact_id, consent)`
- `revoke(consent_id)`
- `delete_derived_data(artifact_id)`

每次调用必须记录：来源、用户动作、授权范围、拿到的字段、失败原因和派生数据。adapter 不直接修改 memory、state 或 proactive；它只返回带来源的内容。

### 7.2 接入顺序

1. Android 分享的 URL/标题/文本/图片。
2. 普通网页的用户选中文本与页面元数据。
3. 视频公开元数据与可合法取得的字幕。
4. 小红书等登录态平台的用户主动分享内容。
5. 天气与只读日历，作为内容会话的低敏背景。
6. 一次性指定窗口/页面共享。

“连续刷推荐 feed”只有在存在稳定、合规、用户可见的授权路径后才评估；当前计划不以它作为 M2 交付依赖。

### 7.3 开源参考

| 参考仓库 | 借鉴内容 | 不照搬 |
| --- | --- | --- |
| [OpenCLI](https://github.com/jackwener/OpenCLI) | 网站、已登录浏览器和 Electron app 的结构化命令层 | 不开放任意 click/type/write；不依赖桌面扩展完成 Android 核心功能 |
| [Operit](https://github.com/AAswordman/Operit) | Android 权限、工具注册、远程 MCP 发现和工作流 | 不做 40+ 通用工具市场 |
| [gaze](https://github.com/jiangxi1129/gaze) | 指定窗口、隐私黑名单、反递归、找不到目标就 skip 的窄门默认 | 不默认全屏或持续采集 |
| [always-here](https://github.com/Cheiineeey/always-here) | 健康/位置/活动作为伴侣上下文的实验方法 | 健康与位置不进入前三个 adapter |
| [AionsHome](https://github.com/death34018-hue/AionsHome) | Android 摄像头、设备数据和多端桥接的恢复策略 | 不照搬常驻设备监管和大范围权限 |

## 8. 横向工作流：连续性、隐私和安全

这些工作不能等 M1/M2 完成后再补。

### 8.1 证据与记忆

- 语音记忆回到用户确认的 transcript 和音频 artifact。
- 帖子/视频记忆回到 artifact、anchor 和 session。
- 会话回顾与事实记忆分开；回顾是双方共同叙事，不自动覆盖事实。
- 内容删除或授权撤回时，可以遍历并处理派生 memory。

参考：

- [Memory Constellations](https://github.com/ClaraShafiq/MemoryConstellations)：事实、主题、叙事与源对话关联。
- [Nocturne Memory](https://github.com/Dataojitori/nocturne_memory)：结构化记忆与 rollback。
- [Ombre-Brain](https://github.com/P0luz/Ombre-Brain)：来源追踪、可读存储和情绪显著性。
- [Aelios](https://github.com/wusaki0723/Aelios)：分层整理和 curation。
- [Miru](https://github.com/kiyotakali/Miru)：可审计记忆、截图即弃的产品边界；完整后端尚未全部开源。

### 8.2 主动联系

- 语音来信和续看邀请继续使用现有 DND、cooldown、daily limit、risk hold、receipt 和 feedback。
- 未回复两次后降低相同主题的联系频率。
- 用户点“不想再聊这个”后，暂停对应 artifact/topic，而不是只隐藏一条消息。
- 主动原因向用户可见，且必须能回到 open loop、reminder 或 shared moment。

参考：

- [dylan-heartbeat](https://github.com/callie0313/dylan-heartbeat)：主动行为进入共同时间线、Bark/ntfy 和长期时间感。
- [astrbot_plugin_proactive_chat](https://github.com/DBJD-CR/astrbot_plugin_proactive_chat)：上下文、DND、动态情绪和 TTS。
- [Callhome](https://github.com/Cheiineeey/callhome)：DND、拒接和未接后的礼貌失败路径。

### 8.3 数据生命周期

必须定义以下独立开关：

- 是否保留原始音频。
- 是否保留 transcript。
- 是否允许某平台内容写入长期记忆。
- 是否保存共同刷内容历史。
- 是否允许基于 shared moment 主动联系。
- export 是否包含音频和第三方内容引用。

删除需要覆盖：原始文件、缓存、数据库记录、索引、备份策略、timeline、diary 和派生记忆；无法立即从旧备份清除的内容必须说明过期周期。

## 9. API 与模块建议

### 9.1 新模块

```text
luminous/runtime/domain/media.py
luminous/runtime/application/media_service.py
luminous/runtime/application/speech_service.py
luminous/runtime/application/content_provider.py
luminous/runtime/infrastructure/audio_store.py
luminous/runtime/infrastructure/providers/stt/
luminous/runtime/infrastructure/providers/tts/
luminous/runtime/infrastructure/providers/content/
apps/companion-web/companion-ui/js/features/voice/
apps/companion-web/companion-ui/js/features/shared-media/
apps/companion-android/  # 分享入口、录音、播放和权限桥
```

实际文件位置可在实施时按现有架构调整；核心要求是 domain/application/infrastructure 分层，不把平台逻辑塞进 `CompanionRuntime` 或 Android notification service。

### 9.2 建议公共 API

```text
POST   /api/audio
GET    /api/audio/{artifact_id}
DELETE /api/audio/{artifact_id}
POST   /api/speech/transcriptions
POST   /api/speech/synthesis

POST   /api/media/artifacts
GET    /api/media/artifacts/{artifact_id}
DELETE /api/media/artifacts/{artifact_id}
POST   /api/media/sessions
GET    /api/media/sessions/{session_id}
POST   /api/media/sessions/{session_id}/anchors
POST   /api/media/sessions/{session_id}/reactions
POST   /api/media/sessions/{session_id}/moments
POST   /api/media/sessions/{session_id}/complete
```

要求：

- 上传使用显式大小/时长限制。
- 所有创建接口支持幂等键。
- 外部 URL 不直接返回服务端内部抓取结果或认证信息。
- public DTO 不暴露 prompt、内部推理、文件路径、provider key、平台 cookie 或原始 trace。
- session 完成接口不能隐式批量写长期记忆；必须返回待确认的 moment proposals。

## 10. 测试与验收计划

### 10.1 单元测试

- 音频格式、时长、大小和哈希。
- ASR/TTS provider 错误映射和超时。
- artifact/anchor/session 状态转换。
- 同内容去重与跨平台 canonical URL。
- shared moment 确认和拒绝。
- 删除图与幂等。
- 互动节奏预算和降频。

### 10.2 契约测试

- Android 分享 payload → public API → artifact。
- transcript 校正 → chat → memory evidence。
- TTS 失败 → 文本降级。
- 视频时间点 → anchor → reaction → timeline。
- session 完成 → moment proposal → 用户确认 → memory。
- consent revoke → adapter 停止 → 派生数据处理。

### 10.3 端到端测试

- Android 真机录音、转写、发送和播放。
- 锁屏收到主动语音来信并深链到正确消息。
- 从浏览器、小红书、B 站/视频页面和相册分享至栖光。
- 断网分享、重试和幂等。
- 一起看视频时保存时间点，重启后恢复。
- 删除 session 后，时间线、记忆和附件行为符合预览。
- 用户关闭主动续接后不再出现相关来信。

### 10.4 关系质量回归

每次发布至少覆盖：

- 语音与文字人格一致。
- ASR 错词不会变成长期事实。
- 栖光没有材料时不假装看过帖子/视频。
- 栖光不会把平台推荐行为推断为用户稳定偏好。
- 安静陪看不插话。
- 用户明确说“不想聊这个”后，相关内容不再主动出现。
- 删除共同瞬间后，后续对话不会继续引用。
- 危机场景不会被娱乐内容或主动语音稀释安全响应。

## 11. 小规模验证与指标

### 11.1 验证阶段

#### Stage A：开发者自测

- 真实 Android 设备。
- 一个真实 LLM、一个真实 ASR、一个真实 TTS。
- 自己分享的公开帖子、视频和图片。
- 连续 3 天使用，覆盖重启、断网和后台恢复。

#### Stage B：内部小组

- 3–5 名明确知情的测试用户。
- 每人至少完成 5 次语音会话和 3 次共同刷内容 session。
- 重点收集转写错误、插话烦扰、内容理解错误和删除失败。

#### Stage C：受限 beta

- 10–30 名用户。
- 默认关闭自动播放、积极讨论和平台深度 adapter。
- 先验证 2–4 周关系连续性，再扩大范围。

### 11.2 核心指标

#### 语音

- 关键实体转写错误率。
- 用户校正率。
- 首个音频延迟和完整音频延迟。
- 文本降级成功率。
- 主动语音来信的播放、回复、关闭和删除。

#### 共同刷内容

- 分享后成功创建 session 的比例。
- 每次 session 的有效互动数，不以停留时长作为唯一指标。
- 用户主动保存共同瞬间的比例。
- session 回顾确认、编辑和放弃比例。
- 稍后再看/续看被真正承接的比例。
- 插话“太多/不合时宜”反馈率。
- 内容理解错误和“假装看过”事件数。

#### 连续性与控制感

- 共同瞬间在后续被正确承接的比例。
- 错误记忆纠正后复发率。
- 删除/撤权后仍被引用的事件数，目标为零。
- DND 和主动主题暂停违规数，目标为零。
- 用户能否说明“为什么栖光现在提起这条内容”。

### 11.3 不作为单一北极星的指标

- 总播放时长。
- 每日打开次数。
- 无限滚动深度。
- 通知点击率。
- 消息数量。

这些指标可以观察，但不能驱动插话、推送或内容推荐策略，否则栖光会从陪伴产品退化为注意力产品。

## 12. 风险清单与缓解

| 风险 | 影响 | 缓解 |
| --- | --- | --- |
| ASR 把错词写进记忆 | 关系事实污染 | 发送前校正；关键实体低置信提示；只写确认文本 |
| TTS 音色侵权或冒充 | 法律与信任风险 | 记录授权；默认通用角色音色；关闭任意声音克隆 |
| 小红书/视频平台接口变化 | 功能中断 | 核心以 Android 分享和标准 URL 为准；adapter 可替换 |
| 平台登录态泄漏 | 账户风险 | cookie/token 不进入模型、日志和 public DTO；首版不依赖登录态抓取 |
| 模型假装看过内容 | 体验与信任损伤 | content coverage 字段；材料不足时固定降级语义；回归测试 |
| 陪伴者插话过多 | 烦扰与流失 | 三种节奏；打断预算；未回复自动降频；一键安静 |
| 浏览行为变成隐式画像 | 隐私和操控风险 | 不记录 feed/滑动/停留；只保存用户主动分享和确认 moment |
| 第三方内容版权 | 法律风险 | 不保存完整视频；引用 URL/时间点；用户内容与缓存设过期策略 |
| 删除不完整 | 长期信任损伤 | 派生数据图、删除预览、集成测试和备份过期说明 |
| 新模块绕开安全链 | 危机场景失控 | 所有媒介最终进入同一 runtime、安全策略和 trace |

## 13. 开源仓库参考矩阵

| 新拓展能力 | 主要参考 | 次要参考 | 栖光的差异化实现 |
| --- | --- | --- | --- |
| Android 语音采集与后台恢复 | AionsHome | AIRI | 复用现有 Android realtime/outbox，不另建伴侣主链 |
| ASR/TTS provider 层 | voice-mcp、AionsHome | Callhome | 文本为规范记忆来源，音频可独立删除 |
| 语气与声音上下文 | ears | Callhome | 仅做用户个人基线的低置信提示，不做诊断 |
| 主动语音来信 | Callhome、dylan-heartbeat | astrbot_plugin_proactive_chat | 复用现有 DND、feedback、receipt 和深链 |
| 共同媒体会话 | Duetto | Ocean | 从音乐扩展到帖子/短视频/长视频，但不绑定平台账户 |
| 视频时间点与字幕上下文 | film-matinee | coread | 时间点 anchor + 共同瞬间 + 证据记忆 |
| 网页/帖子分享 | whale-browser-extension | OpenCLI | Android Sharesheet 优先，平台 adapter 后置 |
| 小红书等登录态内容研究 | OpenCLI | whale-browser-extension | 只读、用户主动分享、可撤销，不做账号自动化 |
| Android 工具和权限架构 | Operit | AionsHome | 只开放陪伴相关 allowlist，不做通用工具市场 |
| 指定页面/窗口上下文 | gaze | Miru | 窄门默认、目标不存在就 skip、首版不常驻 |
| 共同事件叙事 | Memory Constellations | Ombre-Brain | 叙事保留 artifact/anchor/原始证据 |
| 人格/记忆回滚 | Nocturne Memory | Aelios | 与模型升级和派生删除结合，不替换现有 L0–L4 |

## 14. 暂缓清单

以下方向在 M4 小规模验证完成前不启动：

- 双工实时语音、电话外呼和视频通话。
- 声音克隆市场。
- Live2D/VRM、桌宠、复杂换装。
- 自动刷小红书、自动评论/点赞/收藏。
- 个性化内容推荐算法和无限 feed。
- 默认常开屏幕、位置、健康和环境音感知。
- 通用 MCP/Skill 市场。
- 多角色群聊、角色广场和 UGC 剧情。
- 积分、抽卡、连续签到和排行榜。

重新评估条件：

- 语音与文字的人格/记忆一致性稳定。
- 共同刷内容至少完成一个受限 beta，且插话烦扰和内容误解处于可接受范围。
- 删除、撤权、DND 和主动主题暂停无已知违规。
- 用户确实提出更高沉浸度或平台自动化需求，而不是团队根据竞品列表推测。

## 15. Definition of Done

下一阶段不能以“页面做出来”或“provider 能返回结果”宣告完成。完成必须同时满足：

### 功能闭环

- 真机语音输入、文本校正、同一 runtime 回复和语音播放走通。
- 主动语音来信在锁屏、重连、重启和深链场景走通。
- 从真实内容 App 分享帖子/视频到栖光，建立并完成 session。
- 视频时间点或帖子片段能形成可回看的 shared moment。
- shared moment 能在之后被正确引用，并能完整删除。

### 可靠性

- 网络失败不丢消息、不重复写记忆、不重复展示通知。
- provider 失败有明确降级。
- 重启后 session、音频、稍后再看和删除状态一致。
- 幂等、重试、备份/恢复和清理任务有测试。

### 安全与隐私

- 没有平台 cookie、token、内部路径、prompt、trace 或原始推理进入公共响应。
- 没有默认后台麦克风、录屏或隐式浏览画像。
- 删除与撤权通过端到端验证。
- 主动内容遵守 DND、风险 hold 和主题暂停。

### 产品质量

- 安静模式不插话。
- 材料不足时不假装看过。
- 用户能理解每条主动续接的原因。
- 小规模真实用户验证没有发现阻断性人格漂移、记忆污染或烦扰问题。

## 16. 立即执行清单

按顺序启动以下工作，不需要等待所有平台细节确定：

1. 冻结 `MediaArtifact`、`MediaAnchor`、`SharedMediaSession`、`SharedMoment` v1 语义。
2. 写删除/撤权图和 public DTO 契约。
3. 选择首个中文 ASR 与 TTS provider，完成成本、延迟、许可和隐私对比。
4. 实现 `AudioArtifactStore` 与 provider 接口。
5. 做 Android 按住说话、转写校正和音频播放纵向切片。
6. 将 outbox 扩展为可选语音附件，保持文本降级。
7. 实现 Android Sharesheet 到 `MediaArtifact` 的纵向切片。
8. 做内容卡片 + `SharedMediaSession` + 三种互动节奏。
9. 做视频时间点 anchor 和“记住这个”。
10. 将完成回顾接入 Timeline/Diary，并要求用户确认后才写 memory。
11. 做稍后再看与主动续接，复用现有 reminder/proactive/outbox。
12. 先选一个视频来源和普通网页 adapter；小红书保持 Android 分享入口，不阻塞 M2。
13. 建立语音/共同刷内容关系质量回归集。
14. 完成真机 3 天自测后再进入 3–5 人内部测试。

最小可展示纵向切片应是：

> 用户分享一个视频 → 在 08:42 留下语音反应 → 栖光用角色声音回应 → 用户保存为共同瞬间 → 第二天栖光通过有原因的来信问要不要继续看 → 点击后回到同一 session 和时间点。

只要这条链真实走通，栖光就从“带记忆和主动联系的聊天产品”迈进了“能与用户共同消费内容、共同形成生活痕迹的伴侣产品”。
