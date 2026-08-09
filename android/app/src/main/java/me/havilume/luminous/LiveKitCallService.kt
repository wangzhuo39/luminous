package me.havilume.luminous

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import android.webkit.CookieManager
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import androidx.core.content.ContextCompat
import com.twilio.audioswitch.AudioDevice
import com.twilio.audioswitch.AudioDeviceChangeListener
import io.livekit.android.LiveKit
import io.livekit.android.annotations.Beta
import io.livekit.android.audio.AudioSwitchHandler
import io.livekit.android.events.RoomEvent
import io.livekit.android.events.collect
import io.livekit.android.room.Room
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.util.concurrent.CopyOnWriteArraySet
import java.util.concurrent.Executors

class LiveKitCallService : Service() {
    interface Observer {
        fun onStateChanged(state: CallState) = Unit
        fun onTranscription(transcription: Transcription) = Unit
        fun onAudioDevicesChanged(devices: AudioDevices) = Unit
    }

    data class CallState(
        val status: String = "idle",
        val message: String = "",
        val muted: Boolean = false,
        val roomName: String = "",
        val callSessionId: String = "",
        val startedAtMs: Long = 0,
        val reconnectCount: Int = 0,
    )

    data class Transcription(
        val text: String,
        val final: Boolean,
        val participantIdentity: String,
        val assistant: Boolean,
    )

    data class AudioDeviceInfo(val id: String, val name: String)

    data class AudioDevices(
        val selectedDeviceId: String = "",
        val availableDevices: List<AudioDeviceInfo> = emptyList(),
    )

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private var room: Room? = null
    private var roomEvents: Job? = null
    private var audioSwitchHandler: AudioSwitchHandler? = null
    private var audioDeviceListener: AudioDeviceChangeListener? = null
    private var wakeLock: PowerManager.WakeLock? = null
    private var roomName = ""
    private var callSessionId = ""
    private var callStartedAtMs = 0L
    private var reconnectCount = 0
    private var terminalStateReported = false
    private var stopping = false

    override fun onCreate() {
        super.onCreate()
        activeService = this
        createNotificationChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_CONNECT -> {
                promoteToForeground("正在连接实时通话")
                val serverUrl = intent.getStringExtra(EXTRA_SERVER_URL).orEmpty().trim()
                val participantToken = intent.getStringExtra(EXTRA_PARTICIPANT_TOKEN).orEmpty().trim()
                roomName = intent.getStringExtra(EXTRA_ROOM_NAME).orEmpty().trim()
                callSessionId = intent.getStringExtra(EXTRA_CALL_SESSION_ID).orEmpty().trim()
                callStartedAtMs = System.currentTimeMillis()
                reconnectCount = 0
                terminalStateReported = false
                if (serverUrl.isEmpty() || participantToken.isEmpty()) {
                    failAndStop("LiveKit connection details are required")
                } else {
                    scope.launch { connect(serverUrl, participantToken) }
                }
            }
            ACTION_DISCONNECT -> disconnectAndStop("通话已结束")
            else -> {
                stopSelf(startId)
                return START_NOT_STICKY
            }
        }
        return START_NOT_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        teardownRoom()
        if (activeService === this) activeService = null
        if (!stopping && currentState.status !in TERMINAL_STATES) {
            publishState(callState("failed", "实时通话服务已停止"))
        }
        scope.cancel()
        super.onDestroy()
    }

    private suspend fun connect(serverUrl: String, participantToken: String) {
        teardownRoom()
        acquireWakeLock()
        stopping = false
        publishState(callState("connecting"))
        val nextRoom = LiveKit.create(applicationContext)
        room = nextRoom
        observe(nextRoom)
        observeAudioDevices(nextRoom)
        try {
            nextRoom.connect(serverUrl, participantToken)
            if (!nextRoom.localParticipant.setMicrophoneEnabled(true)) {
                throw IllegalStateException("microphone publication failed")
            }
            publishState(callState("connected"))
        } catch (error: Throwable) {
            failAndStop(error.message ?: "LiveKit call connection failed")
        }
    }

    @OptIn(Beta::class)
    private fun observe(active: Room) {
        roomEvents?.cancel()
        roomEvents = scope.launch(Dispatchers.Default) {
            active.events.collect { event ->
                if (room !== active) return@collect
                when (event) {
                    is RoomEvent.Reconnecting -> {
                        reconnectCount += 1
                        publishState(currentState.copy(status = "reconnecting", reconnectCount = reconnectCount))
                    }
                    is RoomEvent.Reconnected -> publishState(currentState.copy(status = "connected", message = ""))
                    is RoomEvent.FailedToConnect -> failAndStop(event.error.message ?: "failed to connect")
                    is RoomEvent.Disconnected -> {
                        if (!stopping) failAndStop(event.error?.message ?: event.reason.name)
                    }
                    is RoomEvent.TranscriptionReceived -> event.transcriptionSegments.lastOrNull()?.let { segment ->
                        publishTranscription(
                            Transcription(
                                text = segment.text,
                                final = segment.final,
                                participantIdentity = event.participant?.identity?.value.orEmpty(),
                                assistant = event.participant?.identity != active.localParticipant.identity,
                            ),
                        )
                    }
                    else -> Unit
                }
            }
        }
    }

    private fun observeAudioDevices(active: Room) {
        val handler = active.audioHandler as? AudioSwitchHandler ?: return
        val listener: AudioDeviceChangeListener = { devices, selected ->
            publishAudioDevices(
                AudioDevices(
                    selectedDeviceId = selected?.deviceId().orEmpty(),
                    availableDevices = devices.map { AudioDeviceInfo(it.deviceId(), it.name) },
                ),
            )
        }
        audioSwitchHandler = handler
        audioDeviceListener = listener
        handler.registerAudioDeviceChangeListener(listener)
    }

    private fun setMicrophoneEnabled(enabled: Boolean, callback: (Result<CallState>) -> Unit) {
        val active = room
        if (active == null || currentState.status !in ACTIVE_STATES) {
            callback(Result.failure(IllegalStateException("LiveKit call is not connected")))
            return
        }
        scope.launch {
            try {
                if (!active.localParticipant.setMicrophoneEnabled(enabled)) {
                    throw IllegalStateException("microphone update failed")
                }
                val next = currentState.copy(muted = !enabled)
                publishState(next)
                callback(Result.success(next))
            } catch (error: Throwable) {
                callback(Result.failure(error))
            }
        }
    }

    private fun selectAudioDevice(deviceId: String): Boolean {
        val handler = audioSwitchHandler ?: return false
        val selected = handler.availableAudioDevices.firstOrNull { it.deviceId() == deviceId } ?: return false
        handler.selectDevice(selected)
        return true
    }

    private fun disconnectAndStop(message: String) {
        if (stopping) return
        stopping = true
        publishState(callState("disconnected", message))
        teardownRoom()
        ServiceCompat.stopForeground(this, ServiceCompat.STOP_FOREGROUND_REMOVE)
        stopSelf()
    }

    private fun failAndStop(message: String) {
        publishState(callState("failed", message))
        stopping = true
        teardownRoom()
        ServiceCompat.stopForeground(this, ServiceCompat.STOP_FOREGROUND_REMOVE)
        stopSelf()
    }

    private fun teardownRoom() {
        roomEvents?.cancel()
        roomEvents = null
        audioDeviceListener?.let { listener ->
            audioSwitchHandler?.unregisterAudioDeviceChangeListener(listener)
        }
        audioDeviceListener = null
        audioSwitchHandler = null
        room?.disconnect()
        room?.release()
        room = null
        wakeLock?.let { if (it.isHeld) it.release() }
        wakeLock = null
        publishAudioDevices(AudioDevices())
    }

    private fun acquireWakeLock() {
        if (wakeLock?.isHeld == true) return
        val manager = getSystemService(PowerManager::class.java) ?: return
        wakeLock = manager.newWakeLock(
            PowerManager.PARTIAL_WAKE_LOCK,
            "$packageName:livekit-call",
        ).apply {
            setReferenceCounted(false)
            acquire(WAKE_LOCK_TIMEOUT_MS)
        }
    }

    private fun callState(status: String, message: String = "") = CallState(
        status = status,
        message = message,
        roomName = roomName,
        callSessionId = callSessionId,
        startedAtMs = callStartedAtMs,
        reconnectCount = reconnectCount,
    )

    private fun reportState(state: CallState) {
        if (state.callSessionId.isEmpty()) return
        val terminal = state.status in setOf("disconnected", "failed")
        if (terminal && terminalStateReported) return
        if (terminal) terminalStateReported = true
        CONTROL_EXECUTOR.execute {
            val cookie = CookieManager.getInstance().getCookie(API_BASE).orEmpty()
            if (cookie.isEmpty()) return@execute
            val serverStatus = if (state.status == "disconnected") "ended" else state.status
            val durationMs = if (state.startedAtMs > 0) {
                (System.currentTimeMillis() - state.startedAtMs).coerceAtLeast(0)
            } else {
                0
            }
            val body = JSONObject()
                .put("status", serverStatus)
                .put("last_error", if (state.status == "failed") state.message else "")
                .put("metrics", JSONObject()
                    .put("duration_ms", durationMs)
                    .put("reconnect_count", state.reconnectCount)
                    .put("muted", state.muted)
                    .put("platform", "android"))
            val sessionUrl = "$API_BASE/api/voice/livekit/session/${state.callSessionId}"
            try {
                HTTP.newCall(
                    Request.Builder()
                        .url("$sessionUrl/metrics")
                        .header("Cookie", cookie)
                        .post(body.toString().toRequestBody(JSON_MEDIA_TYPE))
                        .build(),
                ).execute().close()
                if (terminal) {
                    HTTP.newCall(
                        Request.Builder()
                            .url(sessionUrl)
                            .header("Cookie", cookie)
                            .delete()
                            .build(),
                    ).execute().close()
                }
            } catch (_: Exception) {
                // Call teardown must never be blocked by best-effort control-plane reporting.
            }
        }
    }

    private fun promoteToForeground(text: String) {
        val type = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE
        } else {
            0
        }
        ServiceCompat.startForeground(this, NOTIFICATION_ID, notification(text), type)
    }

    private fun updateNotification(state: CallState) {
        if (state.status !in ACTIVE_STATES) return
        val text = when (state.status) {
            "connecting" -> "正在连接实时通话"
            "reconnecting" -> "网络切换，正在恢复通话"
            else -> if (state.muted) "麦克风已静音" else "实时通话进行中"
        }
        getSystemService(NotificationManager::class.java)?.notify(NOTIFICATION_ID, notification(text))
    }

    private fun notification(text: String): Notification {
        val openIntent = PendingIntent.getActivity(
            this,
            NOTIFICATION_ID,
            Intent(this, MainActivity::class.java).addFlags(
                Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP,
            ),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        val endIntent = PendingIntent.getService(
            this,
            NOTIFICATION_ID + 1,
            Intent(this, LiveKitCallService::class.java).setAction(ACTION_DISCONNECT),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        return NotificationCompat.Builder(this, CHANNEL)
            .setSmallIcon(R.drawable.ic_stat_luminous)
            .setContentTitle("栖光实时通话")
            .setContentText(text)
            .setContentIntent(openIntent)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .setCategory(NotificationCompat.CATEGORY_CALL)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .addAction(0, "结束通话", endIntent)
            .build()
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val manager = getSystemService(NotificationManager::class.java) ?: return
        manager.createNotificationChannel(
            NotificationChannel(CHANNEL, "实时通话", NotificationManager.IMPORTANCE_LOW).apply {
                description = "保持 Luminous 实时语音通话和麦克风访问"
                lockscreenVisibility = Notification.VISIBILITY_PUBLIC
            },
        )
    }

    private fun AudioDevice.deviceId(): String = when (this) {
        is AudioDevice.BluetoothHeadset -> "bluetooth:${name.lowercase()}"
        is AudioDevice.WiredHeadset -> "wired"
        is AudioDevice.Speakerphone -> "speaker"
        is AudioDevice.Earpiece -> "earpiece"
    }

    companion object {
        private const val ACTION_CONNECT = "me.havilume.luminous.action.CONNECT_LIVEKIT_CALL"
        private const val ACTION_DISCONNECT = "me.havilume.luminous.action.DISCONNECT_LIVEKIT_CALL"
        private const val EXTRA_SERVER_URL = "server_url"
        private const val EXTRA_PARTICIPANT_TOKEN = "participant_token"
        private const val EXTRA_ROOM_NAME = "room_name"
        private const val EXTRA_CALL_SESSION_ID = "call_session_id"
        private const val API_BASE = "https://app.havilume.me"
        private const val CHANNEL = "luminous_voice_call"
        private const val NOTIFICATION_ID = 4101
        private const val WAKE_LOCK_TIMEOUT_MS = 4 * 60 * 60 * 1000L
        private val JSON_MEDIA_TYPE = "application/json; charset=utf-8".toMediaType()
        private val HTTP = OkHttpClient.Builder().retryOnConnectionFailure(true).build()
        private val CONTROL_EXECUTOR = Executors.newSingleThreadExecutor { runnable ->
            Thread(runnable, "luminous-voice-control").apply { isDaemon = true }
        }
        private val ACTIVE_STATES = setOf("connecting", "connected", "reconnecting")
        private val TERMINAL_STATES = setOf("idle", "disconnected", "failed")
        private val observers = CopyOnWriteArraySet<Observer>()

        @Volatile
        private var activeService: LiveKitCallService? = null

        @Volatile
        private var currentState = CallState()

        @Volatile
        private var currentAudioDevices = AudioDevices()

        fun connect(
            context: Context,
            serverUrl: String,
            participantToken: String,
            roomName: String,
            callSessionId: String,
        ) {
            val intent = Intent(context, LiveKitCallService::class.java)
                .setAction(ACTION_CONNECT)
                .putExtra(EXTRA_SERVER_URL, serverUrl)
                .putExtra(EXTRA_PARTICIPANT_TOKEN, participantToken)
                .putExtra(EXTRA_ROOM_NAME, roomName)
                .putExtra(EXTRA_CALL_SESSION_ID, callSessionId)
            ContextCompat.startForegroundService(context, intent)
        }

        fun disconnect(context: Context) {
            val active = activeService
            if (active != null) {
                active.disconnectAndStop("通话已结束")
            } else {
                publishState(currentState.copy(status = "disconnected", message = "通话已结束"))
                context.stopService(Intent(context, LiveKitCallService::class.java))
            }
        }

        fun setMicrophoneEnabled(enabled: Boolean, callback: (Result<CallState>) -> Unit) {
            val active = activeService
            if (active == null) {
                callback(Result.failure(IllegalStateException("LiveKit call is not connected")))
            } else {
                active.setMicrophoneEnabled(enabled, callback)
            }
        }

        fun selectAudioDevice(deviceId: String): Boolean = activeService?.selectAudioDevice(deviceId) == true

        fun state(): CallState = currentState

        fun audioDevices(): AudioDevices = currentAudioDevices

        fun addObserver(observer: Observer) {
            observers.add(observer)
            observer.onStateChanged(currentState)
            observer.onAudioDevicesChanged(currentAudioDevices)
        }

        fun removeObserver(observer: Observer) {
            observers.remove(observer)
        }

        private fun publishState(state: CallState) {
            currentState = state
            activeService?.updateNotification(state)
            activeService?.reportState(state)
            observers.forEach { it.onStateChanged(state) }
        }

        private fun publishTranscription(transcription: Transcription) {
            observers.forEach { it.onTranscription(transcription) }
        }

        private fun publishAudioDevices(devices: AudioDevices) {
            currentAudioDevices = devices
            observers.forEach { it.onAudioDevicesChanged(devices) }
        }
    }
}
