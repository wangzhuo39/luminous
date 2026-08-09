# 栖光 Android 测试版

当前 Android 客户端基于 Capacitor 8，应用 ID 为 `me.havilume.luminous`，使用本地打包的 Web 资源连接 `https://app.havilume.me`。

Android App 是当前唯一产品客户端。`https://app.havilume.me/` 的浏览器界面只显示 App 下载提示；App 自身从安装包加载界面，仅通过 HTTPS 调用该域名的 `/api/*`。

## 构建与安装

```bash
npm run android:build:debug
adb install -r android/app/build/outputs/apk/debug/app-debug.apk
```

本机隔离工具链位于 `/home/wz/.local/share/luminous-android/`。如在其他机器构建，可通过 `JAVA_HOME` 和 `ANDROID_SDK_ROOT` 覆盖。

测试包默认版本为 `0.1.0`（versionCode `1`）。后续可升级安装的构建必须提高 versionCode：

```bash
LUMINOUS_ANDROID_VERSION_CODE=2 LUMINOUS_ANDROID_VERSION_NAME=0.1.1 npm run android:build:debug
```

应用禁止 Android 自动备份会话与 WebView 数据，仅允许 HTTPS/WSS 外部通信，并支持 `havilume://app?space=outbox&message_id=...` 形式的受限深链。

## 自定义 LLM 与伴侣设定

在 App 中进入“隐私与边界”→“连接与伴侣设定”，可填写 OpenAI-compatible API 地址、API key、模型、生成参数和伴侣 prompt。配置保存在服务端运行时数据库中，API key 不会回显到 Android WebView；保存后从下一轮对话开始生效。

Android WebView 的 Origin 是 `https://localhost`。公开部署必须把它加入 `LUMINOUS_CORS_ORIGINS`（仓库的 `.env.example` 已包含），否则 App 无法读取或保存这些设置。`npm run build:android:web` 会校验设置表单和 `/api/settings/companion` 客户端代码已进入 Android 资源包。

正式签名包使用环境变量读取密钥，不会把口令写入 Gradle 或仓库：

```bash
LUMINOUS_ANDROID_VERSION_CODE=2 \
LUMINOUS_ANDROID_VERSION_NAME=0.1.1 \
LUMINOUS_ANDROID_KEYSTORE=/absolute/secure/release.jks \
LUMINOUS_ANDROID_KEY_ALIAS=luminous \
LUMINOUS_ANDROID_STORE_PASSWORD='...' \
LUMINOUS_ANDROID_KEY_PASSWORD='...' \
npm run android:build:release
```

## LiveKit 实时语音通话

实时通话只在 Android App 中开放。Capacitor 页面负责通话按钮、状态和转写展示；麦克风采集、远端音频播放、Audio Focus、蓝牙/有线耳机/扬声器路由、网络切换与重连由 LiveKit Android SDK 处理。`LiveKitCallService` 是独立的 `microphone` foreground service，并持有 `Room`；WebView 重建不会结束正在进行的通话，系统常驻通知可直接结束通话。主动来信使用的 `LuminousRealtimeService` 不参与语音媒体。

服务端需要同时运行 Luminous API 与 Voice Agent。LiveKit 密钥只放在服务端：

```dotenv
LUMINOUS_LIVEKIT_URL=wss://your-project.livekit.cloud
LUMINOUS_LIVEKIT_API_KEY=...
LUMINOUS_LIVEKIT_API_SECRET=...
LUMINOUS_LIVEKIT_AGENT_NAME=luminous-voice-agent

LUMINOUS_STT_STREAM_URL=wss://stt-stream.example.com/v1/asr/stream
LUMINOUS_STT_API_KEY=...
LUMINOUS_STT_MODEL=qwen3-asr
LUMINOUS_TTS_STREAM_URL=wss://tts.example.com/v1/tts/stream
LUMINOUS_TTS_API_KEY=...
LUMINOUS_TTS_MODEL=cosyvoice3
LUMINOUS_TTS_VOICE=default
```

```bash
uv run luminous-api --host 127.0.0.1 --port 8000 --deployment-mode public
uv run luminous-livekit-agent start
```

App 先通过已认证的 `/api/voice/livekit/session` 获取 10 分钟、仅限指定房间和 microphone source 的 participant token，再由原生 SDK 直连 LiveKit；客户端不会获得 LiveKit API secret、STT/TTS 或 LLM 凭据。真机验收还需覆盖来电音量通道、蓝牙插拔、锁屏、切换 Wi-Fi/蜂窝网络、WebView/Activity 重建、静音和通知栏结束通话。

## 通知

- 本地提醒：进入“隐私与边界”，点击“开启 Android 通知”。创建、延期、完成或取消提醒时会同步系统通知。
- 实时陪伴：授权通知后，App 会显式启动 `remoteMessaging` 前台服务，通过 `wss://app.havilume.me/api/realtime/outbox` 接收主动来信。系统会保留“栖光实时陪伴”常驻通知；可在 App 或该通知中暂停。
- 漏信恢复：Android 仍会每约 15 分钟从 `/api/outbox` 同步一次。WebSocket 与周期任务共享 `message_id` 去重集合，因此重连、进程恢复或系统延迟不会重复展示同一封来信。
- 回执：本地展示记录为 `notification_displayed`；点击具体来信后记录为 `notification_opened`。退出当前设备时会停止实时前台服务。
- 重启恢复：用户保持实时陪伴开启时，设备重启或 App 升级后会尝试恢复连接；若系统拒绝后台启动，打开 App 后会再次恢复，周期同步始终保留。
- 服务端保持 API 和 `luminous-worker` 运行，`.env` 使用内部 outbox 通道：

```dotenv
ROLE_PLAY_NOTIFY_ENABLED=true
ROLE_PLAY_NOTIFY_CHANNEL=internal
```

内测版不需要 Firebase、FCM、`google-services.json` 或任何 Google 服务账号。构建后在真机登录并开启通知即可。

真机验收至少覆盖：锁屏收信、断网后重连、强制结束后的周期补偿、设备重启、点击深链、暂停实时陪伴以及退出设备后不再连接。
