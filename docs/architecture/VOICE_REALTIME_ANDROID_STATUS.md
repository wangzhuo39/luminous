# Android 实时语音通话实现与问题记录

更新时间：2026-08-09

本文描述 Luminous 当前 Android 实时语音通话的真实实现，不把它表述为 Android 系统电话，也不把静态测试当作实机端到端证明。

## 1. 结论摘要

当前通话是“Capacitor WebView + 原生 Android 录音插件 + Luminous WebSocket 语音桥接”的应用内会话：

```text
Android WebView
  voice-call.js 状态机 / AudioContext 播放
        |
        | Capacitor Plugin.notifyListeners / PluginMethod
        v
VoiceRecorderPlugin.java
  AudioRecord 16 kHz mono s16le + VAD + OkHttp WebSocket
        |
        | wss://app.havilume.me/api/voice/realtime
        v
luminous-api
  voice_realtime.py
        |-- STT WebSocket -> stt-stream.havilume.me
        |-- CompanionService.chat -> LLM/记忆运行时
        `-- TTS WebSocket -> tts.havilume.me
```

这不是 `Telecom`/`ConnectionService` 系统级通话。应用进入后台、WebView 被销毁、网络链路断开时，当前实现没有通话级自动恢复。

2026-08-09 的实机复现已经得到明确服务端证据：WebSocket 握手成功（HTTP 101）后，服务端在收到 Android 端数据约 4 秒后因 `websocket frame too large` 关闭连接。原因是 Android VAD 预录音缓存最多 5 秒，开启一个新 turn 时把整段缓存一次性作为单帧发送，最大约 160 KB，而服务端入站帧上限为 64 KB。

已在 Android 端增加 48 KB 分片发送，覆盖预录音和普通 PCM 帧；服务端此前的写超时修复仍保留。

## 2. Android 原生层

### 2.1 插件注册与权限

`MainActivity` 注册 `VoiceRecorderPlugin`。插件声明 `RECORD_AUDIO`，Manifest 同时声明 `MODIFY_AUDIO_SETTINGS` 和网络权限。实机检查显示应用的 `RECORD_AUDIO` 已授予。

相关文件：

- `android/app/src/main/java/me/havilume/luminous/MainActivity.java`
- `android/app/src/main/java/me/havilume/luminous/VoiceRecorderPlugin.java`
- `android/app/src/main/AndroidManifest.xml`

插件在普通录音和实时通话之间复用一个 `AudioRecord` 实例。权限未授予时通过 Capacitor 权限回调请求；拒绝后直接 reject，不会建立录音会话。

### 2.2 采集格式和线程

核心常量：

- 采样率：16,000 Hz
- 单声道、PCM signed 16-bit little-endian
- 每次读取 `FRAME_BYTES = 3,200`，约 100 ms 音频
- 普通语音消息最大 60 秒
- 实时 VAD 预录音最多 5 秒
- 实时发送帧上限：当前 Android 分片为 48 KB，低于服务端 64 KB 限制

录音在单线程 `audioExecutor` 中循环调用 `AudioRecord.read()`。每个有效块先进入 VAD，再根据 `callAudioEnabled` 决定是否发送：

1. 未开启当前 turn 时，若检测到语音，音频写入 `callPreRoll`。
2. 开启 turn 后，先发送预录音，再发送当前实时块。
3. 录音停止时退出循环，释放 `AudioRecord`、回声消除器和噪声抑制器。

### 2.3 VAD

VAD 是本地、基于平均绝对振幅的简单阈值检测：

- `VAD_THRESHOLD = 450`
- 连续 2 个 voiced frame 触发 `speech_start`
- 连续静音 900 ms 触发 `speech_end`

VAD 只负责产生事件，不负责识别。它可能产生两类体验问题：

- 阈值过高时，用户开头音节进入预录音但没有立即开始 turn。
- 环境噪声超过阈值时，预录音不断累积，随后一次性发送大块数据。后者已经是本次实机中断的直接原因，现已通过分片修复。

### 2.4 WebSocket 客户端

`connectCall()` 从 `CookieManager` 读取登录 cookie，向 `/api/voice/realtime` 发起 OkHttp WebSocket。连接成功后由服务端发送 `call.ready`。

插件向 WebView 派发三种事件：

- `text`：JSON 控制事件
- `binary`：TTS PCM，转为 Base64 后派发
- `closed` / `error`：连接关闭或失败

连接没有通话级重连。`onClosed` 和 `onFailure` 只清空 `callSocket` 并通知前端；是否重连完全由前端决定，而当前前端直接结束通话。

## 3. WebView 通话状态机

文件：`apps/companion-web/companion-ui/js/features/voice/voice-call.js`

主要状态：

```text
idle -> connecting -> ready -> listening -> thinking -> speaking -> ready
```

用户说话时：

1. `speech_start`：`ready` 状态发送 `turn.start`。
2. 服务端回复 `turn.ready` 后开启 `callAudioEnabled`，进入 `listening`。
3. `speech_end`：关闭音频发送，发送 `turn.end`，进入 `thinking`。
4. 服务端发送最终转写、文本和音频事件，进入 `speaking`。
5. 收到 `response.done` 后回到 `ready`。

插话时，前端停止已有 PCM 播放，发送 `response.cancel`，再开始新 turn。

任何原生 `error` 或 `closed` 事件都会调用 `close()`。`close()` 会停止录音、发送 `call.end`、关闭 WebSocket、移除监听器、关闭 `AudioContext`，并将状态设为 `idle`。因此当前实现的连接异常是“整场通话结束”，而不是“本轮失败后恢复”。

## 4. 服务端实时桥接

文件：`luminous/runtime/infrastructure/voice_realtime.py`

服务端完成 WebSocket 握手后立即发送：

```json
{"type":"call.ready","asr_sample_rate":16000,"tts_sample_rate":24000}
```

控制事件：

- `turn.start`：建立上游 ASR WebSocket
- `turn.end`：后台线程等待 ASR final，调用 `CompanionService.chat()`，再建立 TTS WebSocket
- `response.cancel`：设置取消事件并关闭 ASR/TTS 上游
- `call.end`：关闭当前会话
- `ping`：回复 `pong`

下行事件包括 `transcript.partial`、`transcript.final`、`response.text`、`response.audio.start`、二进制 PCM、`response.audio.end` 和 `response.done`。

服务端使用 `_write_lock` 串行化 JSON、音频和 ping 写入。当前读取循环使用 `select()`；写入保持阻塞，避免读取超时污染 TTS 的 `sendall()`。

## 5. 已复现问题

### 5.1 已确认并修复：预录音单帧过大

实机日志对应的服务端记录：

```text
21:00:41 GET /api/voice/realtime 101
21:00:45 voice realtime websocket closed after ValueError: websocket frame too large
```

服务端帧解析器限制为 64 KB。Android 原实现会在 turn ready 时发送最多 5 秒预录音：

```text
16,000 samples/s * 2 bytes * 5 s = 160,000 bytes
```

这不是权限问题，也不是 STT provider 错误，而是协议帧边界错误。当前修复使用 48 KB 分片，避免任何单帧超过服务端限制。

### 5.2 已修复：下游写超时误杀通话

原服务端把同一个 socket 设置为 10 秒超时。该 socket 同时被主线程读取和 TTS worker 写入；移动端消费音频较慢时，`sendall()` 会抛 `TimeoutError`。当前改为阻塞写，主线程用 `select()` 做读取轮询和心跳。

### 5.3 尚未解决：连接异常直接结束整场通话

前端收到 `error`/`closed` 后无条件调用 `close()`。当前没有：

- 自动重连
- 当前 turn 恢复
- 音频播放队列恢复
- 断线原因和 close code 的用户可见诊断

所以网络抖动、Cloudflare Tunnel 重连、服务进程重启或 WebView 暂停仍会表现为“通话中断”。

### 5.4 尚未解决：Android 生命周期不是通话级前台服务

`VoiceRecorderPlugin` 只在 `handleOnDestroy()` 中停止录音和关闭连接。它没有单独的通话前台服务、Audio Focus 生命周期管理、蓝牙路由管理或锁屏保持策略。当前的 `LuminousRealtimeService` 是远程消息 outbox 服务，不能保证实时语音会话在后台持续。

### 5.5 可观测性不足

原生插件的 WebSocket 失败只向 JS 发送固定文案“实时语音连接失败，请重试”，没有传递 HTTP 状态、WebSocket close code、异常类型、已发送帧大小、录音状态或当前 turn id。实机诊断必须依赖服务端日志，客户端自身无法解释中断原因。

## 6. 测试现状

已覆盖：

- 普通语音 API、STT/TTS provider 错误映射
- outbox WebSocket 基础握手和帧处理
- 前端录音、播放、API 适配器

未覆盖：

- Android 原生实时 WebSocket 分片
- 5 秒预录音边界
- 实机 WebView 到服务端的完整 turn
- 下游慢消费和断线重连
- Activity 后台/恢复、锁屏、蓝牙耳机

因此静态测试通过不能替代实机通话证据。

## 7. 下一步优先级

1. 安装包含分片修复的最新 APK，重复“连接 -> 说话 -> 收到回复 -> 连续两轮”测试。
2. 为 Android 插件增加 `sendCallAudioFrames` 的单元测试或协议级测试，验证 160 KB 预录音被拆成多个小于 64 KB 的 frame。
3. 在服务端和原生端记录 call id、turn id、帧大小、close code 和阶段。
4. 增加一次有限次数的自动重连；不要把每次临时网络错误直接转换成 `idle`。
5. 再处理后台生命周期、Audio Focus、蓝牙和系统级通话集成。

