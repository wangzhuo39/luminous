# 语音服务调用协议

本文档是调用端接入 ASR/TTS 服务的唯一接口说明。服务通过 Cloudflare Tunnel 发布，调用端不需要访问服务器内网地址或 Tailscale 地址。

## 1. 服务地址和鉴权

```text
STT_BASE          = https://stt.havilume.me
STT_STREAM_URL    = wss://stt-stream.havilume.me/v1/asr/stream
TTS_BASE          = https://tts.havilume.me
TTS_STREAM_URL    = wss://tts.havilume.me/v1/tts/stream
API_KEY           = ${API_KEY}
```

| 功能 | 请求地址 | 传输方式 |
| --- | --- | --- |
| 语音消息 ASR | `https://stt.havilume.me/v1/audio/transcriptions` | HTTP multipart 上传完整音频 |
| 实时通话 ASR | `wss://stt-stream.havilume.me/v1/asr/stream` | WebSocket，JSON 控制帧 + PCM 二进制帧 |
| 语音消息 TTS | `https://tts.havilume.me/v1/tts` | HTTP JSON，返回完整 PCM |
| 实时通话 TTS | `wss://tts.havilume.me/v1/tts/stream` | WebSocket，JSON 文本帧 + PCM 二进制帧 |
| 音色注册 | `https://tts.havilume.me/v1/voices` | HTTP multipart 上传一次参考 WAV |

`https` 和 `wss` 是 Cloudflare 对外协议；不要把 `http://127.0.0.1:端口` 或 `ws://127.0.0.1:端口` 写在调用端代码中，那些地址只在服务端本机有效。

### API Key 规则

- 语音消息 ASR：HTTP Header `Authorization: Bearer API_KEY`。
- 实时 ASR/TTS v2：优先使用 WebSocket 握手 Header `Authorization: Bearer API_KEY`。
- 旧调用端仍可在首个 `start` JSON 中发送 `api_key`；这是兼容路径。
- 当前服务端源码对 HTTP `/v1/tts` 和 `/v1/voices` 未强制检查 API Key；调用端仍建议通过 Cloudflare Access、网关策略或后续服务端改造保护这两个接口。

## 2. 语音消息 ASR

适用于微信式的“录完后发送一条语音”。调用端上传完整音频，服务端返回一个最终识别结果。

支持 WAV、MP3 等服务端音频栈可解码的格式。建议控制单条语音时长和文件大小，避免不必要的上传延迟。

```bash
curl -X POST https://stt.havilume.me/v1/audio/transcriptions \
  -H 'Authorization: Bearer ${API_KEY}' \
  -F 'model=qwen3-asr' \
  -F 'file=@input.wav'
```

响应示例：

```json
{
  "text": "language Chinese<asr_text>你好，今天过得怎么样？",
  "usage": {"type": "duration", "seconds": 2.4}
}
```

调用端应将 `text` 作为最终文本传给对话业务。当前 Qwen 返回文本可能包含 `language ...<asr_text>` 前缀，解析层应兼容该格式，不要假设 `text` 永远只有纯正文。

## 3. 实时通话 ASR

适用于持续通话、边说边识别。协议 v2 中一个 WebSocket 连接代表一次通话，可以顺序处理多个由 VAD 切分的 utterance。

### 音频格式

```text
采样率：16,000 Hz
声道：单声道
编码：signed 16-bit little-endian PCM（s16le）
```

建议每个 WebSocket 二进制帧携带 20-100 ms 音频。客户端可以发送任意偶数字节长度的 PCM 帧，服务端按 `chunk_size_sec` 执行增量解码。

### 客户端发送顺序

连接：

```text
wss://stt-stream.havilume.me/v1/asr/stream
```

首帧发送 JSON：

```json
{
  "type": "start",
  "protocol_version": "2",
  "language": "Chinese",
  "context": "",
  "chunk_size_sec": 0.5,
  "sample_rate": 16000,
  "channels": 1,
  "format": "s16le"
}
```

收到 `ready` 后，每句话先发送 `utterance_start`，再持续发送 PCM 二进制帧：

```json
{"type":"utterance_start","utterance_id":"utt_001"}
```

客户端 VAD 判断用户说完后发送：

```json
{"type":"utterance_end","utterance_id":"utt_001"}
```

### 服务端消息

```json
{"type":"ready","protocol_version":"2","multi_utterance":true,"sample_rate":16000,"channels":1,"format":"s16le"}
{"type":"utterance_ready","utterance_id":"utt_001"}
{"type":"partial","utterance_id":"utt_001","revision":1,"language":"Chinese","text":"你好"}
{"type":"final","utterance_id":"utt_001","revision":2,"language":"Chinese","text":"你好，今天过得怎么样？","audio_duration_ms":1800,"inference_duration_ms":230}
```

`partial.text` 可能被后续结果修正，只用于实时字幕或临时 UI；业务提交、触发 LLM 时使用 `final.text`。

取消当前句发送 `{"type":"utterance_cancel","utterance_id":"utt_001"}`。整次通话结束发送 `{"type":"session_end"}`，服务端回复 `{"type":"session_ended"}` 后关闭连接。未声明 v2 的旧客户端仍按“一句话一个连接 + `end`”工作。

## 4. 语音消息 TTS

适用于生成一条完整语音消息。默认音色是 `default`，响应为不带 WAV 文件头的原始 PCM：24 kHz、单声道、s16le。

```bash
curl -X POST https://tts.havilume.me/v1/tts \
  -H 'Content-Type: application/json' \
  -d '{
    "text": "收到你的消息了。",
    "voice_id": "default",
    "instruct_text": "请用自然、温和的语气说话。"
  }' \
  -o output.pcm

ffmpeg -f s16le -ar 24000 -ac 1 -i output.pcm output.wav
```

请求体：

```json
{
  "text": "要合成的文本",
  "voice_id": "default",
  "instruct_text": "请用自然、温和的语气说话。"
}
```

`instruct_text` 不带 `<|endofprompt|>` 时，服务端会自动补齐 CosyVoice3 所需的提示词标记。`voice_id` 必须是已注册音色，否则返回错误。

## 5. 实时通话 TTS

适用于通话中边生成边播放。连接：

```text
wss://tts.havilume.me/v1/tts/stream
```

首帧发送：

```json
{
  "type": "start",
  "protocol_version": "2",
  "voice_id": "default",
  "instruct_text": "请用自然、温和的语气说话。"
}
```

收到：

```json
{"type":"ready","protocol_version":"2","cancellation":true,"sample_rate":24000,"channels":1,"format":"s16le"}
```

之后按短句发送文本，建议每条 1-2 个句子：

```json
{"type":"synthesize","request_id":"tts_001","text":"今天过得怎么样？"}
```

每条文本对应以下服务端消息序列：

```text
JSON:    {"type":"audio_start","request_id":"tts_001","sample_rate":24000,"channels":1,"format":"s16le"}
binary:  24 kHz mono s16le PCM（可有多个帧）
JSON:    {"type":"audio_end","request_id":"tts_001","audio_duration_ms":1600,"inference_duration_ms":420}
```

客户端应在收到二进制帧时立即播放，不要等整段音频结束。一个连接同时只允许一个活跃请求，默认应等待 `audio_end` 后再发送下一条文本。

用户插话时发送取消。服务端必须停止继续发送音频，但保持连接：

```json
{"type":"cancel","request_id":"tts_001"}
{"type":"cancelled","request_id":"tts_001"}
```

结束通话发送：

```json
{"type":"session_end"}
```

服务端回复 `{"type":"session_ended"}`。旧客户端的 `text` 和 `end` 消息仍兼容。

## 6. 音色注册

固定角色音色只注册一次，运行时通过 `voice_id` 使用，不要每次 TTS 请求重复上传参考音频。

```bash
curl -X POST https://tts.havilume.me/v1/voices \
  -F 'voice_id=alice' \
  -F 'prompt_text=You are a helpful assistant.<|endofprompt|>希望你以后能够做的比我还好呦。' \
  -F 'prompt_wav=@alice.wav'
```

参考 WAV 应清晰、无明显背景噪声，建议不超过 30 秒。注册成功后响应类似：

```json
{"voice_id":"alice","voices":["default","alice"]}
```

服务端会持久化音色缓存。音色注册不是实时通话流程的一部分，建议在角色创建或后台管理流程中完成。

## 7. Python 最小示例

### 完整 ASR

```python
import requests

API_KEY = os.environ["API_KEY"]
with open("input.wav", "rb") as audio:
    response = requests.post(
        "https://stt.havilume.me/v1/audio/transcriptions",
        headers={"Authorization": f"Bearer {API_KEY}"},
        files={"file": ("input.wav", audio, "audio/wav")},
        data={"model": "qwen3-asr"},
        timeout=120,
    )
response.raise_for_status()
print(response.json()["text"])
```

### 流式 TTS

```python
import asyncio
import json
import websockets

API_KEY = os.environ["API_KEY"]

async def synthesize():
    async with websockets.connect(
        "wss://tts.havilume.me/v1/tts/stream",
        additional_headers={"Authorization": f"Bearer {API_KEY}"},
    ) as ws:
        await ws.send(json.dumps({
            "type": "start",
            "protocol_version": "2",
            "voice_id": "default",
        }))
        ready = json.loads(await ws.recv())
        assert ready["type"] == "ready"
        await ws.send(json.dumps({
            "type": "synthesize",
            "request_id": "example-1",
            "text": "你好，欢迎使用语音服务。",
        }))
        with open("reply.pcm", "wb") as output:
            while True:
                message = await ws.recv()
                if isinstance(message, bytes):
                    output.write(message)
                elif json.loads(message)["type"] == "audio_end":
                    break
        await ws.send(json.dumps({"type": "session_end"}))

asyncio.run(synthesize())
```

## 8. 健康检查和错误处理

```bash
curl -fsS https://stt.havilume.me/healthz
curl -fsS https://stt-stream.havilume.me/healthz
curl -fsS https://tts.havilume.me/healthz
```

常见问题：

| 现象 | 检查方向 |
| --- | --- |
| 域名无法连接 | Cloudflare Tunnel connector、DNS、Published Application 主机名 |
| HTTP 404 | 路径或域名写错；音色注册是 `/v1/voices`（复数） |
| HTTP 405 | 方法错误；`/v1/voices` 只接受 POST |
| WebSocket 失败 | 使用 `wss://`，确认 Cloudflare Tunnel 已启用 WebSockets |
| ASR 401/鉴权失败 | Bearer Header 或 WebSocket `start.api_key` 错误 |
| ASR 没有 partial | PCM 不是 16 kHz mono s16le，或发送帧不足约 2 秒 |
| TTS 无声音 | 按 24 kHz mono s16le 播放；响应不是 WAV 文件 |
| voice_id 错误 | 先注册音色，或改用 `default` |

WebSocket 业务错误统一使用 JSON，调用端按 `retryable` 决定是否重试：

```json
{"type":"error","request_id":"tts_001","code":"MODEL_BUSY","message":"another request is active","retryable":true}
```

调用端不得依赖 `127.0.0.1`、`10.112.222.142` 或 `100.104.83.111`；这些是服务端内部/网络地址，不是对外协议地址。
