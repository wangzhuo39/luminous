package me.havilume.luminous

import android.Manifest
import android.os.Build
import com.getcapacitor.JSArray
import com.getcapacitor.JSObject
import com.getcapacitor.PermissionState
import com.getcapacitor.Plugin
import com.getcapacitor.PluginCall
import com.getcapacitor.PluginMethod
import com.getcapacitor.annotation.CapacitorPlugin
import com.getcapacitor.annotation.Permission
import com.getcapacitor.annotation.PermissionCallback

@CapacitorPlugin(
    name = "LiveKitCall",
    permissions = [
        Permission(alias = "microphone", strings = [Manifest.permission.RECORD_AUDIO]),
        Permission(alias = "bluetooth", strings = [Manifest.permission.BLUETOOTH_CONNECT]),
    ],
)
class LiveKitCallPlugin : Plugin() {
    private var pendingConnectCall: PluginCall? = null

    private val observer = object : LiveKitCallService.Observer {
        override fun onStateChanged(state: LiveKitCallService.CallState) {
            activity?.runOnUiThread {
                val payload = state.toJsObject()
                when (state.status) {
                    "connected" -> pendingConnectCall?.resolve(payload).also { pendingConnectCall = null }
                    "failed", "disconnected" -> pendingConnectCall?.reject(
                        state.message.ifEmpty { "LiveKit call connection failed" },
                    ).also { pendingConnectCall = null }
                }
                notifyListeners("state", payload)
            }
        }

        override fun onTranscription(transcription: LiveKitCallService.Transcription) {
            activity?.runOnUiThread {
                notifyListeners("transcription", JSObject().apply {
                    put("text", transcription.text)
                    put("final", transcription.final)
                    put("participantIdentity", transcription.participantIdentity)
                    put("assistant", transcription.assistant)
                })
            }
        }

        override fun onAudioDevicesChanged(devices: LiveKitCallService.AudioDevices) {
            activity?.runOnUiThread { notifyListeners("audioDevices", devices.toJsObject()) }
        }
    }

    override fun load() {
        LiveKitCallService.addObserver(observer)
    }

    @PluginMethod
    fun connect(call: PluginCall) {
        if (getPermissionState("microphone") != PermissionState.GRANTED) {
            requestPermissionForAlias("microphone", call, "microphonePermissionResult")
            return
        }
        connectWithMicrophonePermission(call)
    }

    @PermissionCallback
    private fun microphonePermissionResult(call: PluginCall) {
        if (getPermissionState("microphone") != PermissionState.GRANTED) {
            call.reject("麦克风权限被拒绝")
            return
        }
        connectWithMicrophonePermission(call)
    }

    private fun connectWithMicrophonePermission(call: PluginCall) {
        if (
            Build.VERSION.SDK_INT >= Build.VERSION_CODES.S &&
            getPermissionState("bluetooth") != PermissionState.GRANTED
        ) {
            requestPermissionForAlias("bluetooth", call, "bluetoothPermissionResult")
            return
        }
        connectWithAvailablePermissions(call)
    }

    @PermissionCallback
    private fun bluetoothPermissionResult(call: PluginCall) {
        // Bluetooth routing is optional; continue with earpiece/speaker if it was denied.
        connectWithAvailablePermissions(call)
    }

    private fun connectWithAvailablePermissions(call: PluginCall) {
        val url = call.getString("serverUrl", "").orEmpty().trim()
        val token = call.getString("participantToken", "").orEmpty().trim()
        val roomName = call.getString("roomName", "").orEmpty().trim()
        val callSessionId = call.getString("callSessionId", "").orEmpty().trim()
        if (url.isEmpty() || token.isEmpty()) {
            call.reject("LiveKit connection details are required")
            return
        }
        pendingConnectCall?.reject("A newer LiveKit connection replaced this request")
        pendingConnectCall = call
        LiveKitCallService.connect(context, url, token, roomName, callSessionId)
    }

    @PluginMethod
    fun disconnect(call: PluginCall) {
        pendingConnectCall?.reject("LiveKit call was cancelled")
        pendingConnectCall = null
        LiveKitCallService.disconnect(context)
        call.resolve(LiveKitCallService.state().toJsObject())
    }

    @PluginMethod
    fun getState(call: PluginCall) {
        call.resolve(LiveKitCallService.state().toJsObject())
    }

    @PluginMethod
    fun setMicrophoneEnabled(call: PluginCall) {
        val enabled = call.getBoolean("enabled", true) ?: true
        LiveKitCallService.setMicrophoneEnabled(enabled) { result ->
            activity?.runOnUiThread {
                result.fold(
                    onSuccess = { call.resolve(it.toJsObject()) },
                    onFailure = { call.reject(it.message ?: "microphone update failed") },
                )
            }
        }
    }

    @PluginMethod
    fun getAudioDevices(call: PluginCall) {
        call.resolve(LiveKitCallService.audioDevices().toJsObject())
    }

    @PluginMethod
    fun selectAudioDevice(call: PluginCall) {
        val deviceId = call.getString("deviceId", "").orEmpty().trim()
        if (deviceId.isEmpty()) {
            call.reject("deviceId is required")
        } else if (!LiveKitCallService.selectAudioDevice(deviceId)) {
            call.reject("audio device is not available")
        } else {
            call.resolve(LiveKitCallService.audioDevices().toJsObject())
        }
    }

    override fun handleOnDestroy() {
        LiveKitCallService.removeObserver(observer)
        pendingConnectCall?.reject("LiveKit UI bridge was destroyed")
        pendingConnectCall = null
        super.handleOnDestroy()
    }

    private fun LiveKitCallService.CallState.toJsObject(): JSObject = JSObject().apply {
        put("status", status)
        put("message", message)
        put("muted", muted)
        put("roomName", roomName)
        put("callSessionId", callSessionId)
        put("startedAtMs", startedAtMs)
        put("reconnectCount", reconnectCount)
    }

    private fun LiveKitCallService.AudioDevices.toJsObject(): JSObject = JSObject().apply {
        put("selectedDeviceId", selectedDeviceId)
        put("availableDevices", JSArray(availableDevices.map { device ->
            JSObject().apply {
                put("id", device.id)
                put("name", device.name)
            }
        }))
    }
}
