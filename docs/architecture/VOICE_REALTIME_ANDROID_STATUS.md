# Android 实时语音通话：当前实现与问题记录

> 更新时间：2026-08-10
> 本文用于向后续开发者或 AI 说明：我们实现了什么、验证到了哪里、为什么实机曾出现 `Broken pipe`，以及下一步还缺什么。

## 1. 当前结论

Luminous 已经完成 Android 原生 LiveKit 通话链路的主要代码，并在 WSL 内部跑通了完整闭环：

```text
Android 原生麦克风/扬声器
        |
        | WebRTC
        v
LiveKit Room
        |
        v
Luminous Voice Agent
  STT -> VAD/Turn -> CompanionService.chat -> TTS
                         |
                         +-> 与文字聊天共用记忆、人格、安全、持久化
```

当前真实状态：

- Android 原生通话、前台服务、音频路由、控制接口已经实现。
- LiveKit Server、Voice Agent、STT/TTS 协议适配已经实现。
- WSL 内部端到端测试已经成功：真实音频输入能转写，回复会进入正常聊天与记忆流程，并收到合成语音。
- Android APK 已成功构建并安装到实机。
- **任意公网网络下的实机 WebRTC 媒体链路尚未打通。** 实机出现的 `Broken pipe` 主要是 LiveKit 公网 ICE/媒体端口不可达，不是 STT、TTS 或 LLM 本身失败。

因此，当前不能宣称“安卓公网实时通话已完成”，只能说应用代码和服务端智能链路基本完成，公网 WebRTC 部署仍待完成。

## 2. 为什么采用这条路径

旧方案通过自定义 WebSocket 在客户端和服务端之间传 PCM，存在网络切换、抖动、拥塞控制、回声处理、重连和 Android 音频路由等问题。

新方案的职责划分为：

- LiveKit/WebRTC 负责媒体面：音频编码、抖动缓冲、拥塞控制、重连以及网络切换。
- Luminous 负责智能面：身份、会话授权、记忆、人格、安全、转写与回复持久化、STT/TTS/LLM 适配。
- HTTP/WebSocket 只做控制和状态，不再传 PCM。
- 客户端不直连模型供应商，避免暴露凭据和绕过 Luminous 的记忆、安全及审计流程。

Android 音频全部留在原生层，不在 Capacitor WebView 和 Native 之间传输音频数据。WebView 只负责按钮、状态和转写展示。

## 3. Android 端实现

核心文件：

- `android/app/src/main/java/me/havilume/luminous/LiveKitCallService.kt`
- `android/app/src/main/java/me/havilume/luminous/LiveKitCallPlugin.kt`
- `apps/companion-android/native-entry.js`
- `apps/companion-web/companion-ui/js/features/voice/voice-call.js`

### `LiveKitCallService`

这是独立的麦克风前台服务，没有复用原来的 `LuminousRealtimeService`。后者负责通知/outbox，不适合承担实时通话。

它负责：

- 创建并连接 LiveKit Room。
- 开启、关闭和静音麦克风。
- 处理 `connecting`、`connected`、`reconnecting`、`failed` 等状态。
- 接收 LiveKit 转写事件。
- 管理听筒、扬声器、有线耳机和蓝牙设备。
- 使用 microphone 类型 foreground service，维持锁屏/后台通话。
- 使用有限时长 WakeLock 保持通话运行。
- 在通知栏显示通话状态和“结束通话”操作。
- 向服务端回传状态、时长、重连次数和错误，并在结束时关闭会话。

### `LiveKitCallPlugin`

Capacitor 插件把以下能力暴露给页面：

- `connect`
- `disconnect`
- `getState`
- `setMicrophoneEnabled`
- `getAudioDevices`
- `selectAudioDevice`

同时发送状态、转写和音频设备变化事件。插件只传控制信息，不传音频帧。

### 页面层

页面先调用 `POST /api/voice/livekit/session` 创建会话，得到短期 participant token 和房间信息，再调用原生插件连接 LiveKit。

当前页面已经能开始/结束通话并显示状态和转写，但还有两个体验缺口：

- 原生的具体连接错误在页面上会被折叠成通用错误，导致 `Broken pipe` 等信息不够清楚。
- 原生已提供音频设备列表和切换能力，但页面还没有完整的设备选择 UI。

## 4. 服务端实现

### 会话控制面

相关代码：

- `luminous/runtime/application/livekit_service.py`
- `luminous/runtime/infrastructure/http.py`
- `luminous/runtime/infrastructure/runtime_store.py`

接口包括：

- `POST /api/voice/livekit/session`：创建 Android 通话会话并签发短期 token。
- `GET /api/voice/livekit/session/{id}`：读取状态。
- `POST /api/voice/livekit/session/{id}/metrics`：回传指标。
- `DELETE /api/voice/livekit/session/{id}`：结束会话和房间。

token 只允许进入指定房间，并限制为麦克风发布源。会话按登录 cookie 归属，数据库记录房间、参与者、状态、时间、错误和指标。

配置区分：

- `LUMINOUS_LIVEKIT_URL`：API 和 Agent 使用的内部地址。
- `LUMINOUS_LIVEKIT_PUBLIC_URL`：返回给 Android 的公网地址。

这个区分很重要：若直接把 `127.0.0.1` 返回给手机，手机连接的是自己而不是 LiveKit Server。

### Voice Agent

相关代码：

- `luminous/runtime/infrastructure/livekit_agent.py`
- `luminous/runtime/infrastructure/speech/livekit_protocol.py`

Agent 加入房间后执行：

1. 接收用户音频。
2. Silero VAD 判断说话边界。
3. STT 长连接流式转写。
4. 调用 `CompanionService.chat(text, history)`。
5. TTS 流式生成并发布回复音频。

语音和文字聊天使用的是同一个 `CompanionService.chat`，因此语音回复会经过相同的长期记忆、人格状态、安全规则、审计和消息持久化，不存在另建一套“无记忆 Voice Agent 聊天”的情况。

当前 LLM 调用仍是先得到完整文本回复，再交给 TTS；STT 和 TTS 音频是流式的，但还不是 LLM token 到 TTS 的真正逐 token 流水线。

## 5. STT/TTS 协议

协议定义见 `docs/architecture/VOICE_SERVICES_PROTOCOL.md`。

- STT 使用一个长 WebSocket 连接承载多轮 utterance，输入 16 kHz、单声道、s16le PCM，返回 partial/final。
- TTS 使用长 WebSocket 连接，每轮有独立 `request_id`，返回 24 kHz、单声道、s16le PCM。
- 两者都用 Bearer 鉴权。
- TTS 支持 cancel，用于用户打断助手时停止当前合成。

远端 Qwen ASR 和 CosyVoice 服务已经按 v2 协议修改和部署。密钥只由服务端环境变量读取，不进入 APK 或浏览器。

## 6. 已完成的验证

已经验证：

- STT 单连接多轮识别。
- TTS 流式播放和取消确认。
- LiveKit Server 与 Voice Agent 在 WSL 内运行。
- WSL 内部真实 E2E：合成一段用户语音并发布到房间，Agent 成功识别、调用正常聊天、持久化用户和助手消息，并返回可听语音。
- Android 编译、lint、APK 安装和页面启动。
- USB 诊断时，手机能够创建会话，LiveKit Server 和 Agent 能看到参与者进入房间。

尚未验证：

- 手机在任意公网 Wi-Fi/蜂窝网络下完成双向音频。
- 公网环境中的网络切换和长时间重连。
- 锁屏、后台、蓝牙耳机和多种厂商 ROM 的完整行为。
- 实机打断、弱网和回声场景。
- token 过期后的重新入房。当前 token 有效期约 10 分钟，已加入的通话不立即受影响，但过期后重新连接还没有刷新 token 流程。

## 7. 遇到的问题

### 7.1 实机报 `Broken pipe`

最初为了调试使用了 USB `adb reverse`。它只能转发 TCP 端口，无法等价转发 LiveKit 使用的 UDP 媒体通道，也不代表真实用户网络可用。信令可能成功、房间也可能出现参与者，但 ICE 最终选择不到可达的媒体地址，连接随后断开并出现 `Broken pipe`。

这次错误说明的是公网/媒体网络未打通，不能通过“USB 能进房”证明实时通话完成。

### 7.2 WSL 地址不是公网地址

WSL 当前 IPv4 为私网地址。即使 LiveKit 监听 `0.0.0.0`，外部手机也不能自然访问。Cloudflare HTTP Tunnel 可以代理 API 和 WebSocket 信令，但普通 HTTP Tunnel 不能替代 WebRTC UDP 和 TURN。

LiveKit 至少涉及：

- HTTPS/WSS 信令。
- ICE 使用的 UDP 媒体端口。
- TCP fallback。
- 受限网络所需的 TURN/TLS 443。

Windows Hyper-V 防火墙规则曾因没有管理员权限而添加失败。仓库中已经加入辅助脚本：

- `scripts/deploy/configure-livekit-wsl-firewall.ps1`

但开放本机防火墙仍不等于具备公网 IP、NAT 端口映射或 TURN 服务。

### 7.3 内部地址和客户端地址混用

早期只配置一个 LiveKit URL，导致服务端可用的 `127.0.0.1` 被返回给手机。之后拆分成 internal URL 和 public URL。内部测试继续使用 loopback，Android 必须拿到真实公网 WSS 地址。

### 7.4 Voice Agent 多进程启动失败

最初把 Agent 入口函数定义在 `build_server` 内部。LiveKit worker 使用 forkserver 后无法 pickle 这个局部函数，报错：

```text
AttributeError: Can't get local object 'build_server.<locals>.voice_session'
```

修复方式是把 `voice_session` 移到模块级，并增加 pickle/启动测试。

### 7.5 STT/TTS 密钥被伴侣设置覆盖

`CompanionService` 启动时会应用持久化的伴侣配置，曾把部署环境里的 STT/TTS 密钥覆盖为旧值，导致 Agent 报鉴权失败。

修复方式是增加专用的流式服务配置：

- `LUMINOUS_STT_STREAM_URL`
- `LUMINOUS_STT_STREAM_API_KEY`
- `LUMINOUS_TTS_STREAM_URL`
- `LUMINOUS_TTS_STREAM_API_KEY`

这些配置不再被用户级伴侣设置修改。

### 7.6 TTS 取消时机错误

初版在 WebSocket 上下文已经退出后才发送 cancel，因此用户打断并没有真正通知 TTS 服务。现在改为在连接仍打开时尽力发送 cancel，再清理播放任务。

### 7.7 端到端测试曾产生假阳性

早期测试只检查“收到非零音频帧”。即使 STT 鉴权失败，也可能收到连接噪声或状态音频，从而误判成功。

现在 E2E 同时校验：

- 输入语音的 final transcript。
- 聊天数据库中持久化的用户消息和助手回复。
- 返回音频的有效语音能量和持续时间。

因此“能进房”或“收到音频帧”不再被视为完整闭环。

## 8. 下一步：打通真正的公网通话

Android 代码不需要回退到 PCM WebSocket。下一步是完成 LiveKit 的公网基础设施：

1. 提供稳定的公网域名和有效 TLS，Android 使用 `wss://...`。
2. 为 LiveKit 配置公网可达的 ICE 地址和 UDP/TCP 端口。
3. 部署 TURN，最好支持 TURN/TLS 443，以覆盖运营商网络、企业 Wi-Fi 和对称 NAT。
4. `LUMINOUS_LIVEKIT_URL` 保持为服务端内部地址，`LUMINOUS_LIVEKIT_PUBLIC_URL` 设置为公网 WSS 地址。
5. 用不在服务器局域网内、不开 USB reverse 的手机测试。
6. 验证蜂窝网络、普通 Wi-Fi、切网、锁屏、蓝牙和打断。

可选部署位置包括有公网能力的服务器，或者 WSL 配合公网 IPv6/路由器端口映射/TURN；“LiveKit 能运行在 WSL”与“WSL 上的 LiveKit 能被全球手机可靠访问”是两件不同的事。

## 9. 完成标准

只有以下条件都满足，才能把 Android 实时语音标记为完成：

- 手机不依赖 USB、ADB reverse 或同一局域网。
- API 创建会话成功，Android 通过公网 WSS 进入房间。
- 双向音频在 Wi-Fi 和蜂窝网络都可用。
- 用户语音被转写并进入同一个 `CompanionService.chat` 和记忆链路。
- 助手文本和语音都返回，消息持久化正确。
- 打断、静音、扬声器/听筒/蓝牙、锁屏和结束通话正常。
- 弱网重连可恢复，失败时 UI 能显示具体原因。
- 服务端不向客户端暴露 LiveKit、STT、TTS 或模型供应商长期密钥。
