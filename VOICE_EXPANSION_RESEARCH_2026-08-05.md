# Luminous 语音能力拓展调研与实施建议

日期：2026-08-05

## 0. 调研边界

本结论只基于两类证据：

1. Luminous 当前源码、配置、清单和测试，不使用 `/home/wz/luminous/docs/` 下的任何现有文档。
2. `DasterProkio/awesome-ai-companion` 当前清单，以及其中候选项目的 README、许可证和真实源码。

工作区中已经存在的两份未跟踪语音/开源调研文档没有被读取，也没有作为本报告依据。

## 1. 结论

Luminous 下一步不应直接做“实时电话 + 声音克隆 + 情绪识别”的大集成。正确顺序是：

1. **P0：可编辑转写的语音消息 + 伴侣语音回复**。先走通录音、转写、现有文本对话、语音合成、播放、失败回退和隐私清理。
2. **P1：半双工免按键语音会话**。加入 VAD、自动分段、局部转写、会话状态机、播放队列和取消。
3. **P2：可打断的实时通话**。加入二进制 WebSocket、流式 ASR、流式 TTS、回声抑制、断线恢复和延迟监控。
4. **P3：伴侣特有能力**。在用户明确选择后，再加主动来电、拒接原因、免打扰、未接留言、睡前朗读、相对个人基线的语气线索和合规的角色声线。

核心架构原则是：**语音层只负责音频与文本之间的转换，不重建一套“语音伴侣大脑”**。最终转写仍调用唯一的 `CompanionRuntime.chat()`，这样现有角色、记忆、关系状态、安全策略、事件账本和主动行为不会发生文本/语音双轨分裂。

最值得参考的项目组合：

- **产品语义：Callhome**，参考来电、拒接、软挂断、留言和免打扰。
- **实时音频工程：AIRI**，参考 VAD、录音会话、过期任务丢弃、TTS 分句、播放排队、取消和回声尾音抑制。
- **移动通话交互：AI Virtual Phone**，参考通话状态机、局部/最终转写回退、音频解锁、音量和移动浏览器兼容。
- **中文 ASR：FunASR + SenseVoice**，前者负责实时协议与可替换 ASR，后者可作为转写/情绪标签候选。
- **角色 TTS：GPT-SoVITS 与 CosyVoice 做实测二选一**。不能只按演示音色决定。
- **语气上下文：ears/Callhome 的“个人基线 + 绑定具体消息”原则**，只放在非关键路径。

## 2. Luminous 当前基础与约束

### 2.1 可以复用的基础

- 文本对话已有唯一主链：`CompanionService.chat()` -> `CompanionRuntime.chat()`。运行时在一个事务中写入原始消息、记忆、状态和事件。
- `CompanionRuntimeStore` 已以 SQLite 为权威存储，并提供事务边界，适合为语音消息补充 `source_modality` 和会话元数据。
- HTTP 服务已有 Cookie 鉴权、Origin 校验、幂等处理、JSON 请求大小上限和结构化错误。
- `/api/realtime/outbox` 已证明当前服务可以完成 WebSocket 握手、帧校验和实时事件推送。
- 前端已有统一 composer、`api-client`、adapter、store 和忙碌状态控制。
- Android 已由 Capacitor 8 包装 Web 前端，已有本地通知与原生入口。

### 2.2 必须正视的缺口

- 源码中没有录音、STT、TTS、音频播放或语音会话实现。
- Android Manifest 当前没有 `RECORD_AUDIO` 或 `MODIFY_AUDIO_SETTINGS` 权限。
- 当前 HTTP body 只支持 JSON；音频不能塞进现有 `/api/chat` 的 JSON body。Base64 会放大体积约 33%，也会增加复制和内存峰值，不应采用。
- 当前 WebSocket 是面向 outbox 的手写同步协议，不等于已经具备持续双向音频、背压、取消和多路事件能力。
- 当前模型调用返回完整结构化结果，不是 token 流。即使 TTS 支持流式，首段声音仍必须等待 LLM 完整回复。第一阶段不要为追求“看似实时”同时重写模型输出协议。
- 当前 Android 主要依赖 WebView；必须在真机验证麦克风授权、后台/前台切换、蓝牙耳机、系统音频焦点和 Web Audio 解锁。

## 3. 应实现的产品功能

### 3.1 P0：语音消息闭环

#### 用户输入

- composer 左侧增加麦克风图标按钮；点击开始、再次点击结束。长按可作为快捷方式，但不能成为唯一方式。
- 明确状态：`请求权限 -> 录音中 -> 可试听/取消 -> 转写中 -> 可编辑转写 -> 发送中`。
- 显示稳定尺寸的波形、时长、取消和确认；录音状态不能挤动现有输入区。
- 浏览器不支持、权限拒绝、没有输入设备、录音过短、超时、文件过大、转写失败分别给出可恢复提示。
- 转写结果先进入文本输入框。默认允许用户修改后发送，避免错误转写直接污染记忆和关系状态。

#### 伴侣输出

- 文本回复始终先可见，TTS 失败不影响文本对话成功。
- 回复旁提供播放/暂停、重播和静音；自动播放由用户设置决定。
- 页面刷新后不默认保留合成音频，只保留文本。若未来要保留语音消息，必须单独征得同意。
- 一次只允许一个伴侣音频播放；新播放会停止旧播放并释放 Blob URL/AudioContext 资源。

#### 设置

- `voice_enabled`、`auto_play`、`voice_id`、`speaking_rate`、`output_volume`。
- `stt_provider`、`tts_provider` 只作为服务端配置展示摘要；API key 不回显、不进入公共 DTO。
- 提供“测试声音”按钮，但不能把测试文本写入聊天历史或记忆。

### 3.2 P1：半双工免按键会话

半双工的定义是：用户说完一段后，系统转写并让伴侣回答；伴侣说话时默认暂停输入。它比“电话”简单，但已经能验证大部分真实风险。

- 客户端 VAD 自动检测开始/结束，失败时退回音量阈值或手动结束。
- 每段录音有独立 `segment_id`，旧会话的迟到转写必须丢弃，不能误发到新会话。
- 通话状态固定为：`CONNECTING -> LISTENING -> USER_SPEAKING -> THINKING -> AI_SPEAKING -> LISTENING -> ENDED`。
- UI 同时显示用户最终转写和伴侣字幕，不能只给声音。
- 用户可随时静音麦克风、切到文字输入、停止伴侣播放或结束会话。
- 伴侣播放结束后保留短暂输入抑制窗口，避免扬声器尾音被识别成用户讲话。AIRI 当前实现使用 800ms，可作为初始值，不应当作通用常数。

### 3.3 P2：可打断实时通话

- 采用一个经过鉴权和 Origin 校验的二进制 WebSocket。音频帧与 JSON 控制事件分离。
- 客户端优先发 16kHz、单声道、PCM16；网络较差时再评估 Opus。不要让每个客户端自行发任意媒体格式。
- 支持局部转写和最终转写；只有最终转写可以进入 `CompanionRuntime.chat()`。
- TTS 以句子/短语分块，严格保持回复顺序。后完成的块不能越过先提交的块播放。
- 用户开始说话时立即执行 barge-in：停止本地播放、向服务端发送取消、丢弃当前回复尚未播放的音频块。
- 断线重连使用 `session_id + last_event_sequence`；同一个 `turn_id` 只能提交一次聊天，避免重复记忆和重复状态迁移。
- 每个会话只有一个活动输入段和一个活动输出 intent；所有异步操作都接受 `AbortSignal` 或等价取消令牌。

### 3.4 P3：伴侣特有语音能力

只有 P0-P2 稳定后再加入：

- **主动来电**：完全 opt-in；设安静时段、每日上限、触发原因、拨号前可取消窗口。
- **快速拒接**：忙、在外面、改为文字、自由文本原因。原因作为本次互动上下文，不作为长期人格结论。
- **软挂断**：伴侣提出结束后保留短窗口；用户再次说话可取消挂断。
- **未接留言**：未接来电生成一条短文本/语音留言，不能连续重拨轰炸。
- **睡前朗读**：独立于聊天 turn，保留阅读位置，支持暂停/继续，避免每段朗读触发记忆抽取。
- **相对语气线索**：音量、音高、停顿、语速等只与该用户自己的历史中位数/MAD 比较，并绑定到具体消息。
- **角色声线**：录入参考音频前记录授权、来源和用途；允许删除声纹/参考音频并立即失效。

## 4. 端到端技术设计

### 4.1 组件边界

```text
Android WebView / Browser
  Mic + MediaRecorder/AudioWorklet + VAD + Player
                 |
       HTTP (P0) / WebSocket (P1-P2)
                 |
VoiceSessionService
  |-- SpeechToTextProvider  -> FunASR/SenseVoice/OpenAI-compatible adapter
  |-- CompanionService.chat(transcript)  -> existing runtime/memory/state/safety
  |-- TextToSpeechProvider  -> GPT-SoVITS/CosyVoice/provider adapter
  |-- VoiceSessionStore     -> text + timing + provider metadata, no raw audio by default
```

新增应用层 `VoiceSessionService`，不要让 HTTP handler 直接拼接 STT、LLM 和 TTS。建议接口：

```python
class SpeechToTextProvider(Protocol):
    def transcribe(self, audio: AudioInput, *, language: str) -> Transcript: ...

class TextToSpeechProvider(Protocol):
    def synthesize(self, request: SpeechRequest) -> AudioResult: ...

class VoiceSessionService:
    def transcribe(...): ...
    def synthesize(...): ...
    def submit_voice_turn(...): ...
    def cancel_output(...): ...
```

`VoiceSessionService` 只向 `CompanionService.chat()` 提交最终文本。不要调用或复制 `MemoryExtractor`、`StateEngine`、`PromptBuilder`。

### 4.2 P0 HTTP 合约

#### `POST /api/voice/transcriptions`

- body：原始音频二进制，不用 Base64。
- `Content-Type`：只允许显式白名单，例如 `audio/webm;codecs=opus`、`audio/mp4`、`audio/wav`。
- headers：`X-Voice-Duration-Ms`、`Idempotency-Key`。
- 限制：建议初始为 60 秒、15 MiB；服务端还要在解码后检查真实时长。
- response：

```json
{
  "transcript": "今天有点累",
  "language": "zh",
  "confidence": 0.91,
  "provider": "funasr",
  "model": "configured-model",
  "duration_ms": 1830,
  "timing": {"decode_ms": 420},
  "acoustic": null
}
```

转写确认后仍调用现有 `POST /api/chat`，保持接口与运行时单一来源。

#### `POST /api/voice/speech`

- JSON body：`text`、`turn_id`、可选 `voice_id/style/speed`。
- 返回音频流，不在 JSON 中放 Base64。
- 服务端限制文本长度、并发、超时和允许的 voice；不能成为任意公开 TTS 代理。
- 客户端把响应转成 Blob URL，播放结束或取消后立即 revoke。

这个两步合约刻意让 STT、聊天和 TTS 可以独立失败和重试。不要在 P0 做一个长时间阻塞、任何一步失败就全部失败的 `/api/voice/turns` 巨型接口。

### 4.3 P1-P2 WebSocket 合约

路径建议为 `/api/voice/realtime`。JSON 控制事件示例：

```json
{"event":"session.start","session_id":"vs_...","sample_rate":16000,"encoding":"pcm_s16le"}
{"event":"input.commit","segment_id":"seg_..."}
{"event":"response.cancel","turn_id":"turn_..."}
{"event":"session.end","reason":"user_hangup"}
```

服务端事件：

```json
{"event":"session.started","sequence":1}
{"event":"input.speech_started","segment_id":"seg_...","sequence":2}
{"event":"transcript.partial","segment_id":"seg_...","text":"今天有","sequence":3}
{"event":"transcript.final","segment_id":"seg_...","text":"今天有点累","sequence":4}
{"event":"response.text.done","turn_id":"turn_...","text":"那先歇一会儿。","sequence":5}
{"event":"response.audio.started","turn_id":"turn_...","sequence":6}
{"event":"response.audio.done","turn_id":"turn_...","sequence":7}
{"event":"response.cancelled","turn_id":"turn_...","sequence":8}
{"event":"error","code":"stt_timeout","retryable":true,"sequence":9}
```

二进制帧必须依赖当前 session/segment 上下文，不在每帧复制 JSON。所有事件带单调递增 `sequence`，便于重连和测试。

### 4.4 数据模型

优先扩展现有消息模型，而不是建立第二套语音聊天历史：

- `raw_messages.source_modality`: `text | voice`。
- `raw_messages.modality_metadata_json`: STT provider/model、confidence、language、duration、acoustic cue、voice session/segment id。
- 新表 `voice_sessions`: `session_id`、started/ended、initiator、end_reason、turn_count、timing summary。
- 音频默认不进 SQLite、不进备份、不进 prompt trace。
- 如果用户主动选择保留语音，使用独立媒体目录、内容哈希、加密/访问控制、保留期和删除 API；数据库只存引用。

## 5. 开源项目参考矩阵

| 项目 | 应参考什么 | 不应照搬什么 | 许可证/风险 |
|---|---|---|---|
| [Callhome](https://github.com/Cheiineeey/callhome) | 来电原因、软挂断、拒接、DND、留言、通话摘要；SenseVoice + 个人声学基线 | 当前可运行核心主要是一次性 STT 和参考代码，不是完整通话产品；示例会保留上传音频，且 HTTP 示例缺少生产级鉴权/限流 | MIT；模型权重需另查许可证 |
| [AIRI](https://github.com/moeru-ai/airi) | AudioWorklet/VAD、录音分段、过期转写丢弃、TTS 分句、顺序播放、Abort/cancel、播放后输入抑制 | 不移植整个 Vue/monorepo/角色舞台；Luminous 不需要先做 Live2D | MIT；代码量大，按机制重写 |
| [AI Virtual Phone](https://github.com/xiaolongbao0709/ai-virtual-phone) | `CONNECTING/IDLE/USER_SPEAKING/PROCESSING/AI_SPEAKING` 状态机、局部转写回退、移动端音频解锁和音量 | 不复制其完整虚拟手机和业务存储；Luminous 已有自己的关系/记忆主链 | AGPL-3.0；只研究行为，未经兼容性评估不要复制代码 |
| [My Raze](https://github.com/Do-fei/my-raze) | MediaRecorder MIME fallback、权限错误分类、stream/timer 清理、最长时长 | 仓库自身标记不适合直接部署，且依赖外部服务；不作为安全或生产架构样板 | MIT；适合小范围前端参考 |
| [FunASR](https://github.com/modelscope/FunASR) | 中文 ASR、VAD、标点、OpenAI-compatible HTTP、实时 WS、client `COMMIT` 与 partial/final | 不让浏览器直连模型服务；由 Luminous 网关统一鉴权、限流和协议 | MIT；具体模型权重另核验 |
| [SenseVoice](https://github.com/QwenAudio/SenseVoice) | 中/粤/英/日/韩转写、语言/情绪/音频事件标签；适合 P0 候选与 P3 次级分析 | 情绪标签不是事实、诊断或安全判定；不要直接改变关系状态 | 代码 MIT；模型权重单独核验 |
| [GPT-SoVITS](https://github.com/RVC-Boss/GPT-SoVITS) | 角色声线、参考音频、多级 streaming mode、速度和切分参数 | 不在 P0 开放任意上传克隆；不把参考音频路径暴露给客户端 | 代码 MIT；训练素材、角色声音权利与权重另行审查 |
| [CosyVoice](https://github.com/QwenAudio/CosyVoice) | 多语、zero-shot/cross-lingual/instruct、生成器式流式推理、部署工具 | 不把模型直接嵌进 Luminous API 进程；作为独立推理服务 | 代码 Apache-2.0；模型权重另核验 |
| [Fish Speech](https://github.com/fishaudio/fish-speech) | 仅作为延迟/自然语言控制能力的实验候选 | 当前许可证要求商业使用取得单独书面许可，不能作为产品默认依赖 | Fish Audio Research License，商业使用受限 |
| [voice-mcp](https://github.com/Yinglianchun/voice-mcp) | provider 选择、style 归一化、字幕 timing、内联播放器 | 不需要为 Luminous 引入 MCP；它的“latest event cache”不是聊天持久化设计 | MIT；适合接口形状参考 |
| [ears](https://github.com/eveacla11/ears) | 个人中位数/MAD 基线、语气线索绑定具体消息、音频分析后删除 | 不把 LLM 命名的情绪当作客观真值；不放在回复关键路径 | MIT；默认转写可能使用外部云服务 |
| [voice-familiarity](https://github.com/akinia0315/voice-familiarity) | 未来可选的熟人上下文 | 声纹不能用作登录或权限认证 | Apache-2.0；生物特征需明确同意 |

### 5.1 推荐的默认候选

#### STT

- **P0 默认候选：FunASR 的 OpenAI-compatible transcription service**。原因是接入边界清楚，未来可换模型。
- **P1 默认候选：FunASR realtime WebSocket，客户端 VAD + `COMMIT`**。Luminous 自己定义外层事件，不直接暴露 FunASR 协议。
- **SenseVoice** 作为 P0 对照和 P3 的情绪/事件标签来源。是否成为主转写模型由 CER、延迟和真机噪声实验决定。

#### TTS

- **角色一致性主候选：GPT-SoVITS**。已有直接流式 API，适合固定角色声线。
- **多语/可控性主候选：CosyVoice**。适合作为第二候选和降级路径。
- **Fish Speech 不作为默认**，除非产品许可证已取得。
- **IndexTTS 不作为默认**，直到仓库和模型的可用许可证被明确核验。

provider 选择必须由本机/目标服务器实验决定，不能因为 stars、demo 或“SOTA”描述直接定案。

## 6. Luminous 具体改造位置

### 6.1 后端

建议新增：

- `luminous/runtime/domain/voice.py`：`Transcript`、`AudioInput`、`SpeechRequest`、`VoiceSession`、状态枚举。
- `luminous/runtime/application/voice_service.py`：编排 STT -> chat -> TTS，不包含 HTTP 细节。
- `luminous/runtime/infrastructure/speech/`：provider protocol、FunASR、SenseVoice、GPT-SoVITS、CosyVoice adapters。
- `luminous/runtime/infrastructure/voice_realtime.py`：实时会话、帧/事件协议、背压、取消和重连。

建议修改：

- `luminous/runtime/config.py`：provider URL、model、timeout、并发、大小/时长上限、音频保留策略。密钥只从环境变量/服务端设置读取。
- `luminous/runtime/application/runtime.py`：只增加 voice settings、消息 modality 元数据和 voice session 审计；不要复制 `chat()`。
- `luminous/runtime/application/service.py`：公开经过清洗的语音能力与设置 DTO。
- `luminous/runtime/infrastructure/http.py`：增加原始二进制 body reader、`/api/voice/*` 路由、内容类型/长度校验；实时路由复用现有鉴权和 Origin 逻辑。
- `luminous/runtime/infrastructure/public_api.py`：严格过滤 provider secret、内部路径、参考音频路径和模型错误原文。
- `luminous/runtime/infrastructure/runtime_store.py`：SQLite migration、message modality 和 voice session 表。

不要在现有 `ThreadingHTTPServer` handler 内加载 ASR/TTS 模型。推理模型独立进程运行，Luminous 通过有超时的本机 HTTP/WS adapter 调用。P0 可以保留当前 HTTP 服务；只有当 P2 的双向连接、背压或并发实测不稳定时，才迁移到 ASGI，而不是提前重写整个 API 层。

### 6.2 前端与 Android

建议新增：

- `apps/companion-web/companion-ui/js/features/voice/voice-controller.js`
- `apps/companion-web/companion-ui/js/features/voice/voice-recorder.js`
- `apps/companion-web/companion-ui/js/features/voice/voice-player.js`
- `apps/companion-web/companion-ui/js/features/voice/voice-call-session.js`
- `apps/companion-web/companion-ui/js/services/voice-api.js`

接入点：

- `index.html` 当前 `chat-input` 与 `send-button` 之间加入麦克风按钮和不改变布局尺寸的录音状态区。
- `dom-registry.js` 注册 mic、waveform、timer、cancel、confirm、playback 和 call overlay。
- `main.js` 只负责装配 controller；不要继续堆录音细节。
- `app-store.js/core-state.js` 增加 voice 状态，明确与 `chatStatus === submitting` 的互斥关系。
- `api-client.js` 需要支持 binary request/response、AbortController 和 WebSocket auth。
- Android Manifest 增加 `android.permission.RECORD_AUDIO`；真机验证后再决定是否需要 `MODIFY_AUDIO_SETTINGS`。
- 原生壳只处理权限、音频焦点和生命周期差异。普通录音优先使用标准 Web API，除非真机证据表明 WebView 不可靠，才引入原生录音插件。

## 7. 安全、隐私和可靠性要求

### 7.1 音频处理

- 音频写入随机服务端临时文件；忽略客户端 filename；在 `finally` 中删除。
- 解码器运行要有时长、CPU、内存和 wall-clock timeout，防止畸形媒体耗尽资源。
- 同一用户最多一个活动录音转写、一个活动通话 session、一个活动 TTS 输出。
- 原始音频默认不进日志、trace、备份、错误响应或通知 payload。
- provider 错误映射为稳定错误码，不把密钥、上游 URL、文件路径或 traceback 返回给客户端。

### 7.2 伴侣与安全边界

- 声学情绪只能是 `observed_cue`，不能直接写成“用户很悲伤/在撒谎”等长期记忆。
- 声学线索不能单独触发危机升级、主动联系或关系状态跃迁。
- 声纹识别不是认证；unknown speaker 时应降低个性化，而不是拒绝安全功能。
- 主动来电必须可关闭、可设安静时段、每日限次，并提供一键停止所有主动语音联系。
- 角色声音克隆要记录数据来源、授权主体、允许用途、删除能力和模型/权重许可证。

## 8. 可执行实验与验收

### 8.1 ASR 选型实验

候选：FunASR 配置 A、SenseVoice 配置 B、一个现有云 STT 作为工程基线。

数据：

- 公共集：AISHELL-1 test 或 Common Voice Mandarin 的固定公开子集。
- 产品集：经同意录制的 100 条 Luminous 场景语句，覆盖安静、风扇、街道、耳机、轻声、专有名词和中英混说。
- 所有 provider 使用相同音频，不得人工修正后再送入某个候选。

指标：CER/WER、空结果率、幻觉插入率、语言/标点正确率、实时率 RTF、p50/p95 首个 partial、最终文本延迟、CPU/GPU/显存峰值。

主决策规则：先满足准确率门槛，再在满足者中选 p95 延迟与部署成本更优者。不能把情绪标签能力混进主 ASR 分数。

### 8.2 TTS 选型实验

候选：GPT-SoVITS 固定版本/权重、CosyVoice 固定版本/权重；Fish Speech 只做研究对照。

固定 40 条脚本：短答、长句、数字、日期、人名、英文缩写、低声、安慰、轻松、疑问。记录：

- TTFA、RTF、p95 完成时间、显存峰值、失败率。
- 回转 ASR CER，检查漏字/吞字/重复。
- 盲评自然度、角色匹配、情绪适度和长时间聆听疲劳；至少做成对比较，不只打一个总分。
- 对同一 seed/参考音频重复生成，检查稳定性。

### 8.3 端到端验收

- 语音 turn 的最终 transcript 与普通文字消息走同一 chat trace，并只写入一次记忆/状态迁移。
- 权限拒绝、录音中切后台、STT 超时、TTS 500、网络断开、页面刷新、重复 idempotency key 均可恢复。
- P0：10 秒录音的 `speech_end -> transcript` 和 `reply_ready -> first_audio` 都记录 p50/p95，不只报告平均值。
- P2：用户开口后 250ms 内停止本地伴侣音频作为目标；若硬件不满足，报告实测而不是隐藏。
- 30 分钟连续通话无不断增长的 MediaStream、AudioContext、Blob URL、timer、WebSocket listener 或临时文件。
- 扬声器、听筒、蓝牙耳机三种输出分别测试；伴侣声音不得被再次转写为用户输入。
- Android 真机冷启动、权限首次授权、拒绝后重试、锁屏/解锁、前后台、来电打断、蓝牙切换全部有测试记录。

建议新增测试：

- `tests/backend/test_voice_http.py`
- `tests/backend/test_voice_provider_contracts.py`
- `tests/backend/test_voice_session.py`
- `tests/backend/test_voice_privacy.py`
- `tests/backend/test_voice_realtime_websocket.py`
- `tests/frontend/voice-recorder.test.mjs`
- `tests/frontend/voice-controller.test.mjs`
- `tests/frontend/voice-player.test.mjs`
- `tests/frontend/voice-call-session.test.mjs`
- Android instrumentation：权限、生命周期、音频焦点。

## 9. 分阶段交付门槛

### Gate A：协议与 provider 基线

- provider contract、配置、错误码、临时文件清理和 ASR/TTS benchmark runner 完成。
- 至少一个真实 STT 和一个真实 TTS 通过 smoke test；mock 成功不算完成。

### Gate B：P0 语音消息

- Android 真机完成 `录音 -> 转写 -> 编辑 -> chat -> TTS -> 播放`。
- 文本 fallback、取消、权限、超时、幂等和隐私测试通过。

### Gate C：P1 半双工

- VAD/音量回退、状态机、旧任务丢弃、字幕和播放抑制通过 30 分钟 soak。
- 没有重复 turn、回声自激或无法结束的会话。

### Gate D：P2 实时通话

- WebSocket partial/final/cancel/reconnect 合约稳定。
- p95 延迟、barge-in、资源泄漏和真机兼容达到预先定义门槛。

### Gate E：P3 伴侣语音

- DND、频率上限、拒接、留言和声音授权全部有用户控制与审计。
- 声学线索完成独立消融：开启后是否真的提升用户对“被听见”的评分，同时不增加错误揣测。

## 10. 明确不建议现在做的事

- 不先做 Live2D、口型和 3D 形象。它们不会解决语音闭环、延迟、打断和隐私问题。
- 不让语音走一套单独记忆和关系引擎。
- 不把 Base64 音频塞进 `/api/chat`。
- 不在 Luminous API 进程内加载大型 ASR/TTS 模型。
- 不一开始就做全双工；先用 P0/P1 暴露真机和模型问题。
- 不把固定声学阈值或单次“情绪识别”写入长期用户画像。
- 不以声纹作为认证。
- 不在许可证不清楚时把 Fish Speech 或 IndexTTS 设为产品默认。
- 不把开源项目的完整 UI/架构搬进 Luminous；只复用经过测试的机制与协议思想。

## 11. 一手来源

- 清单：[DasterProkio/awesome-ai-companion](https://github.com/DasterProkio/awesome-ai-companion)
- Callhome：[仓库](https://github.com/Cheiineeey/callhome)、[STT server](https://github.com/Cheiineeey/callhome/blob/main/stt-service/server.py)、[tone baseline](https://github.com/Cheiineeey/callhome/blob/main/stt-service/tone.py)
- AIRI：[仓库](https://github.com/moeru-ai/airi)、[speech pipeline](https://github.com/moeru-ai/airi/blob/main/packages/pipelines-audio/src/speech-pipeline.ts)、[TTS chunker](https://github.com/moeru-ai/airi/blob/main/packages/pipelines-audio/src/processors/tts-chunker.ts)、[voice input session](https://github.com/moeru-ai/airi/blob/main/packages/stage-ui/src/composables/audio/voice-input-session.ts)
- AI Virtual Phone：[仓库](https://github.com/xiaolongbao0709/ai-virtual-phone)、[voice call screen](https://github.com/xiaolongbao0709/ai-virtual-phone/blob/main/components/chat/voice-call-screen.tsx)、[TTS service](https://github.com/xiaolongbao0709/ai-virtual-phone/blob/main/lib/tts-service.ts)
- My Raze：[仓库](https://github.com/Do-fei/my-raze)、[recorder hook](https://github.com/Do-fei/my-raze/blob/main/client/src/hooks/useVoiceRecorder.ts)
- FunASR：[仓库](https://github.com/modelscope/FunASR)、[realtime WebSocket implementation](https://github.com/modelscope/FunASR/blob/main/funasr/bin/realtime_ws.py)
- SenseVoice：[仓库](https://github.com/QwenAudio/SenseVoice)
- GPT-SoVITS：[仓库](https://github.com/RVC-Boss/GPT-SoVITS)、[streaming API](https://github.com/RVC-Boss/GPT-SoVITS/blob/main/api_v2.py)
- CosyVoice：[仓库](https://github.com/QwenAudio/CosyVoice)、[CLI inference](https://github.com/QwenAudio/CosyVoice/blob/main/cosyvoice/cli/cosyvoice.py)
- Fish Speech：[仓库](https://github.com/fishaudio/fish-speech)、[research license](https://github.com/fishaudio/fish-speech/blob/main/LICENSE)
- voice-mcp：[仓库](https://github.com/Yinglianchun/voice-mcp)
- ears：[仓库](https://github.com/eveacla11/ears)
- voice-familiarity：[仓库](https://github.com/akinia0315/voice-familiarity)
