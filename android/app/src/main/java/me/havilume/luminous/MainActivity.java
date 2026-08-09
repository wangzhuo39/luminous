package me.havilume.luminous;

import android.os.Bundle;

import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        registerPlugin(RealtimeCompanionPlugin.class);
        registerPlugin(VoiceRecorderPlugin.class);
        super.onCreate(savedInstanceState);
        LuminousNotificationJobService.schedule(this);
    }
}
