package me.havilume.luminous;

import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

@CapacitorPlugin(name = "RealtimeCompanion")
public final class RealtimeCompanionPlugin extends Plugin {
    @PluginMethod
    public void getState(PluginCall call) {
        call.resolve(state());
    }

    @PluginMethod
    public void start(PluginCall call) {
        try {
            LuminousRealtimeService.start(getContext());
            call.resolve(state());
        } catch (RuntimeException exception) {
            call.reject("无法启动实时陪伴", exception);
        }
    }

    @PluginMethod
    public void stop(PluginCall call) {
        LuminousRealtimeService.stop(getContext());
        call.resolve(state());
    }

    @PluginMethod
    public void acknowledge(PluginCall call) {
        String messageId = call.getString("messageId", "").trim();
        String receiptType = call.getString("receiptType", "notification_opened").trim();
        if (messageId.isEmpty()) {
            call.reject("messageId is required");
            return;
        }
        LuminousRealtimeService.sendReceiptNow(getContext(), messageId, receiptType);
        call.resolve();
    }

    private JSObject state() {
        JSObject result = new JSObject();
        result.put("enabled", LuminousRealtimeService.isEnabled(getContext()));
        result.put("running", LuminousRealtimeService.isRunning());
        result.put("status", LuminousRealtimeService.connectionState(getContext()));
        return result;
    }
}
