package me.havilume.luminous;

import android.Manifest;
import android.media.AudioFormat;
import android.media.AudioRecord;
import android.media.MediaRecorder;
import android.media.audiofx.AcousticEchoCanceler;
import android.media.audiofx.NoiseSuppressor;
import android.util.Base64;
import android.webkit.CookieManager;

import com.getcapacitor.JSObject;
import com.getcapacitor.PermissionState;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import com.getcapacitor.annotation.Permission;
import com.getcapacitor.annotation.PermissionCallback;

import java.io.ByteArrayOutputStream;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import okhttp3.MediaType;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.RequestBody;
import okhttp3.Response;
import okhttp3.WebSocket;
import okhttp3.WebSocketListener;
import okio.ByteString;
import org.json.JSONObject;

@CapacitorPlugin(
    name = "VoiceRecorder",
    permissions = @Permission(alias = "microphone", strings = Manifest.permission.RECORD_AUDIO)
)
public final class VoiceRecorderPlugin extends Plugin {
    private static final int SAMPLE_RATE = 16_000;
    private static final int FRAME_BYTES = 3_200;
    private static final int MAX_MESSAGE_BYTES = SAMPLE_RATE * 2 * 60;
    private static final int MAX_PREROLL_BYTES = SAMPLE_RATE * 2 * 5;
    private static final int MAX_CALL_FRAME_BYTES = 48 * 1024;
    private static final int VAD_THRESHOLD = 450;
    private static final int VAD_START_FRAMES = 2;
    private static final long VAD_END_SILENCE_MS = 900;
    private static final String API_BASE = "https://app.havilume.me";
    private static final MediaType WAV = MediaType.get("audio/wav");
    private static final OkHttpClient HTTP = new OkHttpClient();

    private final ExecutorService audioExecutor = Executors.newSingleThreadExecutor();
    private final ExecutorService networkExecutor = Executors.newSingleThreadExecutor();
    private final Object lock = new Object();
    private AudioRecord recorder;
    private AcousticEchoCanceler echoCanceler;
    private NoiseSuppressor noiseSuppressor;
    private boolean recording;
    private boolean streaming;
    private ByteArrayOutputStream messageAudio;
    private byte[] completedAudio = new byte[0];
    private long startedAt;
    private long completedDurationMs;
    private WebSocket callSocket;
    private boolean callAudioEnabled;
    private final ByteArrayOutputStream callPreRoll = new ByteArrayOutputStream();
    private boolean speechActive;
    private int voicedFrames;
    private long silenceStartedAt;

    @PluginMethod
    public void start(PluginCall call) {
        if (getPermissionState("microphone") != PermissionState.GRANTED) {
            requestPermissionForAlias("microphone", call, "microphonePermissionResult");
            return;
        }
        startCapture(call);
    }

    @PermissionCallback
    private void microphonePermissionResult(PluginCall call) {
        if (getPermissionState("microphone") != PermissionState.GRANTED) {
            call.reject("麦克风权限被拒绝");
            return;
        }
        startCapture(call);
    }

    @PluginMethod
    public void stop(PluginCall call) {
        String mode = call.getString("mode", "message");
        boolean requestedStream = "stream".equals(mode);
        synchronized (lock) {
            if (!recording || streaming != requestedStream) {
                call.reject("当前没有对应的录音会话");
                return;
            }
            stopRecorderLocked();
        }
        audioExecutor.execute(() -> {
            JSObject result = new JSObject();
            if (!requestedStream) {
                long duration;
                synchronized (lock) {
                    duration = completedDurationMs;
                }
                result.put("durationMs", duration);
            }
            call.resolve(result);
        });
    }

    @PluginMethod
    public void transcribeMessage(PluginCall call) {
        byte[] audio;
        long duration;
        synchronized (lock) {
            audio = completedAudio;
            duration = completedDurationMs;
        }
        if (audio.length == 0 || duration <= 0) {
            call.reject("没有可发送的录音");
            return;
        }
        String cookie = CookieManager.getInstance().getCookie(API_BASE);
        if (cookie == null || cookie.trim().isEmpty()) {
            call.reject("登录已失效，请重新登录后发送语音");
            return;
        }
        byte[] wav = wav(audio);
        networkExecutor.execute(() -> {
            Request request = new Request.Builder()
                .url(API_BASE + "/api/voice/transcriptions")
                .header("Cookie", cookie)
                .header("X-Audio-Duration-Ms", Long.toString(duration))
                .header("X-Audio-Filename", "recording.wav")
                .post(RequestBody.create(wav, WAV))
                .build();
            try (Response response = HTTP.newCall(request).execute()) {
                String body = response.body() == null ? "" : response.body().string();
                JSONObject payload = new JSONObject(body);
                if (!response.isSuccessful()) {
                    JSONObject error = payload.optJSONObject("error");
                    call.reject(error == null ? "语音处理失败，请重试。" : error.optString("message", "语音处理失败，请重试。"));
                    return;
                }
                String text = payload.optString("text", "").trim();
                if (text.isEmpty()) {
                    call.reject("没有识别到清晰语音，请重试。");
                    return;
                }
                JSObject result = new JSObject();
                result.put("text", text);
                call.resolve(result);
            } catch (Exception exception) {
                call.reject("暂时无法连接语音服务。", exception);
            }
        });
    }

    @PluginMethod
    public void discardMessage(PluginCall call) {
        synchronized (lock) {
            completedAudio = new byte[0];
            completedDurationMs = 0;
        }
        call.resolve();
    }

    @PluginMethod
    public void connectCall(PluginCall call) {
        String cookie = CookieManager.getInstance().getCookie(API_BASE);
        if (cookie == null || cookie.trim().isEmpty()) {
            call.reject("登录已失效，请重新登录后开始通话");
            return;
        }
        Request request = new Request.Builder()
            .url(API_BASE + "/api/voice/realtime")
            .header("Cookie", cookie)
            .build();
        synchronized (lock) {
            closeCallLocked();
            callSocket = HTTP.newWebSocket(request, new CallListener());
        }
        call.resolve();
    }

    @PluginMethod
    public void sendCallEvent(PluginCall call) {
        String event = call.getString("event", "").trim();
        WebSocket socket;
        synchronized (lock) {
            socket = callSocket;
        }
        if (event.isEmpty() || socket == null || !socket.send(event)) {
            call.reject("实时通话连接不可用");
            return;
        }
        call.resolve();
    }

    @PluginMethod
    public void closeCall(PluginCall call) {
        synchronized (lock) {
            closeCallLocked();
        }
        call.resolve();
    }

    @PluginMethod
    public void setCallAudioEnabled(PluginCall call) {
        boolean enabled = call.getBoolean("enabled", false);
        WebSocket socket = null;
        byte[] preRoll = new byte[0];
        synchronized (lock) {
            callAudioEnabled = enabled;
            if (enabled && callPreRoll.size() > 0) {
                socket = callSocket;
                preRoll = callPreRoll.toByteArray();
                callPreRoll.reset();
            } else if (!enabled && !speechActive) {
                callPreRoll.reset();
            }
        }
        if (socket != null && preRoll.length > 0) {
            sendCallAudioFrames(socket, preRoll, preRoll.length);
        }
        call.resolve();
    }

    @Override
    protected void handleOnDestroy() {
        synchronized (lock) {
            stopRecorderLocked();
            closeCallLocked();
        }
        audioExecutor.shutdownNow();
        networkExecutor.shutdownNow();
        super.handleOnDestroy();
    }

    private void startCapture(PluginCall call) {
        boolean requestedStream = "stream".equals(call.getString("mode", "message"));
        AudioRecord next;
        try {
            next = newRecorder(requestedStream);
            next.startRecording();
        } catch (RuntimeException exception) {
            call.reject("无法启动麦克风录音", exception);
            return;
        }
        synchronized (lock) {
            if (recording) {
                next.release();
                call.reject("已有录音会话正在进行");
                return;
            }
            recorder = next;
            recording = true;
            streaming = requestedStream;
            if (requestedStream) {
                callAudioEnabled = false;
                callPreRoll.reset();
                speechActive = false;
                voicedFrames = 0;
                silenceStartedAt = 0;
            }
            messageAudio = requestedStream ? null : new ByteArrayOutputStream();
            completedAudio = new byte[0];
            completedDurationMs = 0;
            startedAt = System.currentTimeMillis();
            if (requestedStream) enableCallProcessing(next);
        }
        audioExecutor.execute(() -> capture(next, requestedStream));
        call.resolve();
    }

    private AudioRecord newRecorder(boolean stream) {
        int minimum = AudioRecord.getMinBufferSize(
            SAMPLE_RATE, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT
        );
        if (minimum <= 0) throw new IllegalStateException("设备不支持 16 kHz 单声道录音");
        AudioRecord created = new AudioRecord(
            stream ? MediaRecorder.AudioSource.VOICE_COMMUNICATION : MediaRecorder.AudioSource.VOICE_RECOGNITION,
            SAMPLE_RATE,
            AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT,
            Math.max(minimum * 2, FRAME_BYTES * 4)
        );
        return created;
    }

    private void enableCallProcessing(AudioRecord active) {
        int sessionId = active.getAudioSessionId();
        if (AcousticEchoCanceler.isAvailable()) {
            echoCanceler = AcousticEchoCanceler.create(sessionId);
            if (echoCanceler != null) echoCanceler.setEnabled(true);
        }
        if (NoiseSuppressor.isAvailable()) {
            noiseSuppressor = NoiseSuppressor.create(sessionId);
            if (noiseSuppressor != null) noiseSuppressor.setEnabled(true);
        }
    }

    private void capture(AudioRecord active, boolean activeStream) {
        byte[] buffer = new byte[FRAME_BYTES];
        try {
            while (isCurrent(active)) {
                int count = active.read(buffer, 0, buffer.length);
                if (count <= 0) continue;
                if (activeStream) {
                    updateVad(buffer, count);
                    sendCallAudio(buffer, count);
                } else {
                    synchronized (lock) {
                        if (messageAudio != null && messageAudio.size() < MAX_MESSAGE_BYTES) {
                            messageAudio.write(buffer, 0, Math.min(count, MAX_MESSAGE_BYTES - messageAudio.size()));
                        }
                    }
                }
            }
        } finally {
            synchronized (lock) {
                if (recorder == active) {
                    completedAudio = messageAudio == null ? new byte[0] : messageAudio.toByteArray();
                    completedDurationMs = Math.max(0, System.currentTimeMillis() - startedAt);
                    recorder = null;
                    recording = false;
                    streaming = false;
                    messageAudio = null;
                }
            }
            releaseCallProcessing();
            release(active);
        }
    }

    private boolean isCurrent(AudioRecord active) {
        synchronized (lock) {
            return recording && recorder == active;
        }
    }

    private void stopRecorderLocked() {
        recording = false;
        AudioRecord active = recorder;
        if (active != null) {
            try {
                active.stop();
            } catch (IllegalStateException ignored) {
                // The capture loop will release it.
            }
        }
    }

    private void releaseCallProcessing() {
        if (echoCanceler != null) {
            echoCanceler.release();
            echoCanceler = null;
        }
        if (noiseSuppressor != null) {
            noiseSuppressor.release();
            noiseSuppressor = null;
        }
    }

    private void closeCallLocked() {
        WebSocket socket = callSocket;
        callSocket = null;
        callAudioEnabled = false;
        callPreRoll.reset();
        if (socket != null) socket.close(1000, "client stopping");
    }

    private void sendCallAudio(byte[] buffer, int count) {
        WebSocket socket;
        byte[] preRoll = new byte[0];
        synchronized (lock) {
            socket = callSocket;
            if (socket == null) return;
            if (!callAudioEnabled) {
                if (speechActive) {
                    int allowed = Math.min(count, MAX_PREROLL_BYTES - callPreRoll.size());
                    if (allowed > 0) callPreRoll.write(buffer, Math.max(0, count - allowed), allowed);
                }
                return;
            }
            if (callPreRoll.size() > 0) {
                preRoll = callPreRoll.toByteArray();
                callPreRoll.reset();
            }
        }
        if (preRoll.length > 0) sendCallAudioFrames(socket, preRoll, preRoll.length);
        sendCallAudioFrames(socket, buffer, count);
    }

    private static void sendCallAudioFrames(WebSocket socket, byte[] audio, int length) {
        for (int offset = 0; offset < length; offset += MAX_CALL_FRAME_BYTES) {
            int chunk = Math.min(MAX_CALL_FRAME_BYTES, length - offset);
            if (!socket.send(ByteString.of(audio, offset, chunk))) return;
        }
    }

    private void updateVad(byte[] buffer, int count) {
        long total = 0;
        int samples = count / 2;
        for (int offset = 0; offset + 1 < count; offset += 2) {
            int sample = (buffer[offset] & 0xff) | (buffer[offset + 1] << 8);
            total += Math.abs((short) sample);
        }
        int amplitude = samples == 0 ? 0 : (int) (total / samples);
        long now = System.currentTimeMillis();
        if (amplitude >= VAD_THRESHOLD) {
            voicedFrames += 1;
            silenceStartedAt = 0;
            if (!speechActive && voicedFrames >= VAD_START_FRAMES) {
                speechActive = true;
                emitVad("speech_start");
            }
            return;
        }
        voicedFrames = 0;
        if (!speechActive) return;
        if (silenceStartedAt == 0) silenceStartedAt = now;
        if (now - silenceStartedAt >= VAD_END_SILENCE_MS) {
            speechActive = false;
            silenceStartedAt = 0;
            emitVad("speech_end");
        }
    }

    private void emitVad(String type) {
        JSObject event = new JSObject();
        event.put("type", type);
        notifyListeners("vad", event);
    }

    private void emitCallEvent(String kind, String data) {
        JSObject event = new JSObject();
        event.put("kind", kind);
        event.put("data", data);
        notifyListeners("call", event);
    }

    private final class CallListener extends WebSocketListener {
        @Override
        public void onMessage(WebSocket socket, String text) {
            emitCallEvent("text", text);
        }

        @Override
        public void onMessage(WebSocket socket, ByteString bytes) {
            emitCallEvent("binary", Base64.encodeToString(bytes.toByteArray(), Base64.NO_WRAP));
        }

        @Override
        public void onClosed(WebSocket socket, int code, String reason) {
            synchronized (lock) {
                if (callSocket == socket) callSocket = null;
            }
            emitCallEvent("closed", "");
        }

        @Override
        public void onFailure(WebSocket socket, Throwable throwable, Response response) {
            synchronized (lock) {
                if (callSocket == socket) callSocket = null;
            }
            emitCallEvent("error", "实时语音连接失败，请重试。");
        }
    }

    private static void release(AudioRecord active) {
        try {
            active.release();
        } catch (RuntimeException ignored) {
            // Nothing else can use this short-lived recorder.
        }
    }

    private static byte[] wav(byte[] pcm) {
        byte[] result = new byte[44 + pcm.length];
        putInt(result, 0, 0x46464952);
        putInt(result, 4, 36 + pcm.length);
        putInt(result, 8, 0x45564157);
        putInt(result, 12, 0x20746d66);
        putInt(result, 16, 16);
        putShort(result, 20, 1);
        putShort(result, 22, 1);
        putInt(result, 24, SAMPLE_RATE);
        putInt(result, 28, SAMPLE_RATE * 2);
        putShort(result, 32, 2);
        putShort(result, 34, 16);
        putInt(result, 36, 0x61746164);
        putInt(result, 40, pcm.length);
        System.arraycopy(pcm, 0, result, 44, pcm.length);
        return result;
    }

    private static void putInt(byte[] target, int offset, int value) {
        target[offset] = (byte) value;
        target[offset + 1] = (byte) (value >>> 8);
        target[offset + 2] = (byte) (value >>> 16);
        target[offset + 3] = (byte) (value >>> 24);
    }

    private static void putShort(byte[] target, int offset, int value) {
        target[offset] = (byte) value;
        target[offset + 1] = (byte) (value >>> 8);
    }
}
