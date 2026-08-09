package me.havilume.luminous;

import android.Manifest;
import android.annotation.SuppressLint;
import android.media.AudioFormat;
import android.media.AudioRecord;
import android.media.MediaRecorder;
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
import org.json.JSONObject;

@CapacitorPlugin(
    name = "VoiceRecorder",
    permissions = @Permission(alias = "microphone", strings = Manifest.permission.RECORD_AUDIO)
)
public final class VoiceRecorderPlugin extends Plugin {
    private static final int SAMPLE_RATE = 16_000;
    private static final int FRAME_BYTES = 3_200;
    private static final int MAX_MESSAGE_BYTES = SAMPLE_RATE * 2 * 60;
    private static final String API_BASE = "https://app.havilume.me";
    private static final MediaType WAV = MediaType.get("audio/wav");
    private static final OkHttpClient HTTP = new OkHttpClient();

    private final ExecutorService audioExecutor = Executors.newSingleThreadExecutor();
    private final ExecutorService networkExecutor = Executors.newSingleThreadExecutor();
    private final Object lock = new Object();
    private AudioRecord recorder;
    private boolean recording;
    private ByteArrayOutputStream messageAudio;
    private byte[] completedAudio = new byte[0];
    private long startedAt;
    private long completedDurationMs;

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
        synchronized (lock) {
            if (!recording) {
                call.reject("当前没有录音会话");
                return;
            }
            stopRecorderLocked();
        }
        audioExecutor.execute(() -> {
            JSObject result = new JSObject();
            long duration;
            synchronized (lock) {
                duration = completedDurationMs;
            }
            result.put("durationMs", duration);
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

    @Override
    protected void handleOnDestroy() {
        synchronized (lock) {
            stopRecorderLocked();
        }
        audioExecutor.shutdownNow();
        networkExecutor.shutdownNow();
        super.handleOnDestroy();
    }

    private void startCapture(PluginCall call) {
        AudioRecord next;
        try {
            next = newRecorder();
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
            messageAudio = new ByteArrayOutputStream();
            completedAudio = new byte[0];
            completedDurationMs = 0;
            startedAt = System.currentTimeMillis();
        }
        audioExecutor.execute(() -> capture(next));
        call.resolve();
    }

    @SuppressLint("MissingPermission") // start() and its permission callback both gate this call.
    private AudioRecord newRecorder() {
        int minimum = AudioRecord.getMinBufferSize(
            SAMPLE_RATE, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT
        );
        if (minimum <= 0) throw new IllegalStateException("设备不支持 16 kHz 单声道录音");
        AudioRecord created = new AudioRecord(
            MediaRecorder.AudioSource.VOICE_RECOGNITION,
            SAMPLE_RATE,
            AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT,
            Math.max(minimum * 2, FRAME_BYTES * 4)
        );
        return created;
    }

    private void capture(AudioRecord active) {
        byte[] buffer = new byte[FRAME_BYTES];
        try {
            while (isCurrent(active)) {
                int count = active.read(buffer, 0, buffer.length);
                if (count <= 0) continue;
                synchronized (lock) {
                    if (messageAudio != null && messageAudio.size() < MAX_MESSAGE_BYTES) {
                        messageAudio.write(buffer, 0, Math.min(count, MAX_MESSAGE_BYTES - messageAudio.size()));
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
                    messageAudio = null;
                }
            }
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
