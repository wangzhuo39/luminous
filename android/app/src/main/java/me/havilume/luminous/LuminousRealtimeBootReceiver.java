package me.havilume.luminous;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

public final class LuminousRealtimeBootReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context context, Intent intent) {
        String action = intent == null ? "" : intent.getAction();
        if (!Intent.ACTION_BOOT_COMPLETED.equals(action) && !Intent.ACTION_MY_PACKAGE_REPLACED.equals(action)) return;
        if (!LuminousRealtimeService.isEnabled(context)) return;
        try {
            LuminousRealtimeService.start(context);
        } catch (RuntimeException ignored) {
            // Opening the app will retry; the periodic outbox job remains available meanwhile.
        }
    }
}
