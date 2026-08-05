package me.havilume.luminous;

import android.Manifest;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.content.pm.ServiceInfo;
import android.graphics.Color;
import android.net.Uri;
import android.os.Build;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.webkit.CookieManager;

import androidx.annotation.Nullable;
import androidx.core.app.NotificationCompat;
import androidx.core.app.NotificationManagerCompat;
import androidx.core.app.ServiceCompat;
import androidx.core.content.ContextCompat;

import org.json.JSONObject;

import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Date;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.TimeZone;
import java.util.concurrent.ThreadLocalRandom;
import java.util.concurrent.TimeUnit;

import okhttp3.MediaType;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.RequestBody;
import okhttp3.Response;
import okhttp3.WebSocket;
import okhttp3.WebSocketListener;

public final class LuminousRealtimeService extends Service {
    public static final String ACTION_START = "me.havilume.luminous.action.START_REALTIME";
    public static final String ACTION_STOP = "me.havilume.luminous.action.STOP_REALTIME";

    private static final String API_BASE = "https://app.havilume.me";
    private static final String WS_BASE = "wss://app.havilume.me";
    private static final String PROTOCOL = "luminous.realtime.v1";
    private static final String SERVICE_CHANNEL_ID = "luminous_realtime_service";
    private static final String MESSAGE_CHANNEL_ID = "luminous_messages";
    private static final String PREFS = "luminous_notification_sync";
    private static final String ENABLED = "realtime_enabled";
    private static final String STATE = "realtime_state";
    private static final String SEEN_IDS = "seen_message_ids";
    private static final String SYNC_STARTED_AT = "sync_started_at";
    private static final int SERVICE_NOTIFICATION_ID = 0x4c554d20;
    private static final MediaType JSON = MediaType.get("application/json; charset=utf-8");
    private static final OkHttpClient CLIENT = new OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(0, TimeUnit.MILLISECONDS)
        .pingInterval(20, TimeUnit.SECONDS)
        .retryOnConnectionFailure(true)
        .build();

    private static volatile LuminousRealtimeService activeInstance;

    private final Handler handler = new Handler(Looper.getMainLooper());
    private WebSocket socket;
    private int reconnectAttempt;
    private boolean stopping;

    public static void start(Context context) {
        SharedPreferences preferences = preferences(context);
        if (!preferences.contains(SYNC_STARTED_AT)) {
            preferences.edit().putLong(SYNC_STARTED_AT, System.currentTimeMillis()).apply();
        }
        preferences.edit().putBoolean(ENABLED, true).putString(STATE, "starting").apply();
        Intent intent = new Intent(context, LuminousRealtimeService.class).setAction(ACTION_START);
        ContextCompat.startForegroundService(context, intent);
    }

    public static void stop(Context context) {
        preferences(context).edit().putBoolean(ENABLED, false).putString(STATE, "stopped").apply();
        context.stopService(new Intent(context, LuminousRealtimeService.class));
    }

    public static boolean isEnabled(Context context) {
        return preferences(context).getBoolean(ENABLED, false);
    }

    public static boolean isRunning() {
        return activeInstance != null;
    }

    public static String connectionState(Context context) {
        return preferences(context).getString(STATE, isEnabled(context) ? "starting" : "stopped");
    }

    public static void sendReceiptNow(Context context, String messageId, String receiptType) {
        if (messageId == null || messageId.trim().isEmpty()) return;
        LuminousRealtimeService active = activeInstance;
        if (active != null && active.sendReceipt(messageId.trim(), receiptType)) return;
        postReceiptHttp(context.getApplicationContext(), messageId.trim(), receiptType);
    }

    @Override
    public void onCreate() {
        super.onCreate();
        activeInstance = this;
        createChannels();
    }

    @Override
    public int onStartCommand(@Nullable Intent intent, int flags, int startId) {
        String action = intent == null ? ACTION_START : intent.getAction();
        if (ACTION_STOP.equals(action) || !isEnabled(this)) {
            stopping = true;
            disconnect();
            ServiceCompat.stopForeground(this, ServiceCompat.STOP_FOREGROUND_REMOVE);
            stopSelf();
            return START_NOT_STICKY;
        }
        stopping = false;
        preferences(this).edit().putBoolean(ENABLED, true).apply();
        promoteToForeground();
        connect();
        return START_STICKY;
    }

    @Nullable
    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    @Override
    public void onDestroy() {
        handler.removeCallbacksAndMessages(null);
        disconnect();
        activeInstance = null;
        if (isEnabled(this) && !stopping) setState("restarting");
        super.onDestroy();
    }

    private void promoteToForeground() {
        Notification notification = serviceNotification(connectionState(this));
        int type = Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE
            ? ServiceInfo.FOREGROUND_SERVICE_TYPE_REMOTE_MESSAGING
            : 0;
        ServiceCompat.startForeground(this, SERVICE_NOTIFICATION_ID, notification, type);
    }

    private void connect() {
        handler.removeCallbacksAndMessages(null);
        if (stopping || !isEnabled(this) || socket != null) return;
        String cookie = CookieManager.getInstance().getCookie(API_BASE);
        if (cookie == null || cookie.trim().isEmpty()) {
            setState("login_required");
            scheduleReconnect(15_000L);
            return;
        }
        setState(reconnectAttempt == 0 ? "connecting" : "reconnecting");
        long since = preferences(this).getLong(SYNC_STARTED_AT, System.currentTimeMillis());
        Request request = new Request.Builder()
            .url(WS_BASE + "/api/realtime/outbox?since=" + since)
            .header("Cookie", cookie)
            .header("Sec-WebSocket-Protocol", PROTOCOL)
            .build();
        socket = CLIENT.newWebSocket(request, new RealtimeListener());
    }

    private void disconnect() {
        WebSocket current = socket;
        socket = null;
        if (current != null) current.close(1000, "client stopping");
    }

    private void scheduleReconnect(long minimumDelayMs) {
        if (stopping || !isEnabled(this)) return;
        long exponential = Math.min(60_000L, 1_000L << Math.min(reconnectAttempt, 6));
        long delay = Math.max(minimumDelayMs, exponential) + ThreadLocalRandom.current().nextLong(0, 1_001);
        reconnectAttempt += 1;
        handler.postDelayed(this::connect, delay);
    }

    private void setState(String state) {
        preferences(this).edit().putString(STATE, state).apply();
        try {
            NotificationManagerCompat.from(this).notify(SERVICE_NOTIFICATION_ID, serviceNotification(state));
        } catch (SecurityException ignored) {
            // startForeground still keeps the service visible in system task management.
        }
    }

    private Notification serviceNotification(String state) {
        Intent open = new Intent(this, MainActivity.class)
            .setFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        PendingIntent openIntent = PendingIntent.getActivity(
            this, SERVICE_NOTIFICATION_ID, open, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
        );
        Intent stop = new Intent(this, LuminousRealtimeService.class).setAction(ACTION_STOP);
        PendingIntent stopIntent = PendingIntent.getService(
            this, SERVICE_NOTIFICATION_ID + 1, stop, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
        );
        return new NotificationCompat.Builder(this, SERVICE_CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_stat_luminous)
            .setColor(Color.rgb(159, 199, 216))
            .setContentTitle("栖光实时陪伴")
            .setContentText(serviceStatusText(state))
            .setContentIntent(openIntent)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setCategory(NotificationCompat.CATEGORY_SERVICE)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .addAction(0, "暂停", stopIntent)
            .build();
    }

    private String serviceStatusText(String state) {
        if ("connected".equals(state)) return "已连接，叶筝可以实时给你写信";
        if ("login_required".equals(state)) return "等待 App 登录后重新连接";
        if ("reconnecting".equals(state) || "restarting".equals(state)) return "连接暂时中断，正在重试";
        return "正在连接 Luminous";
    }

    private void createChannels() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return;
        NotificationManager manager = getSystemService(NotificationManager.class);
        if (manager == null) return;
        NotificationChannel service = new NotificationChannel(
            SERVICE_CHANNEL_ID, "实时陪伴连接", NotificationManager.IMPORTANCE_LOW
        );
        service.setDescription("保持与 Luminous 的实时连接；可随时在 App 内暂停。");
        manager.createNotificationChannel(service);
        NotificationChannel messages = new NotificationChannel(
            MESSAGE_CHANNEL_ID, "栖光来信", NotificationManager.IMPORTANCE_HIGH
        );
        messages.setDescription("提醒与叶筝主动发来的消息");
        messages.enableVibration(true);
        manager.createNotificationChannel(messages);
    }

    private void handleMessage(String raw) {
        try {
            JSONObject payload = new JSONObject(raw);
            if (!"proactive_message".equals(payload.optString("type"))) return;
            String messageId = payload.optString("message_id", "").trim();
            String body = payload.optString("body", "").trim();
            if (messageId.isEmpty() || body.isEmpty() || alreadySeen(messageId)) return;
            if (!notificationsAllowed()) return;
            showMessageNotification(messageId, body);
            rememberSeen(messageId);
            sendReceipt(messageId, "notification_displayed");
        } catch (Exception ignored) {
            // Malformed server frames are ignored; the persisted outbox remains available to fallback sync.
        }
    }

    private boolean notificationsAllowed() {
        return Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU
            || ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS)
                == PackageManager.PERMISSION_GRANTED;
    }

    private void showMessageNotification(String messageId, String body) {
        Uri deepLink = Uri.parse("havilume://app?space=outbox&message_id=" + Uri.encode(messageId));
        Intent open = new Intent(Intent.ACTION_VIEW, deepLink, this, MainActivity.class)
            .setFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        PendingIntent pendingIntent = PendingIntent.getActivity(
            this, stableId(messageId), open, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
        );
        Notification notification = new NotificationCompat.Builder(this, MESSAGE_CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_stat_luminous)
            .setColor(Color.rgb(159, 199, 216))
            .setContentTitle("叶筝的来信")
            .setContentText(body)
            .setStyle(new NotificationCompat.BigTextStyle().bigText(body))
            .setContentIntent(pendingIntent)
            .setAutoCancel(true)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setCategory(NotificationCompat.CATEGORY_MESSAGE)
            .build();
        NotificationManagerCompat.from(this).notify(stableId(messageId), notification);
    }

    private boolean alreadySeen(String messageId) {
        return preferences(this).getStringSet(SEEN_IDS, new HashSet<>()).contains(messageId);
    }

    private synchronized void rememberSeen(String messageId) {
        SharedPreferences preferences = preferences(this);
        Set<String> seen = new HashSet<>(preferences.getStringSet(SEEN_IDS, new HashSet<>()));
        seen.add(messageId);
        if (seen.size() > 200) {
            List<String> values = new ArrayList<>(seen);
            seen = new HashSet<>(values.subList(values.size() - 200, values.size()));
        }
        preferences.edit().putStringSet(SEEN_IDS, seen).apply();
    }

    private boolean sendReceipt(String messageId, String receiptType) {
        WebSocket current = socket;
        if (current == null) return false;
        JSONObject payload = new JSONObject();
        try {
            payload.put("type", "receipt");
            payload.put("message_id", messageId);
            payload.put("receipt_type", receiptType);
            payload.put("occurred_at", nowIso());
            return current.send(payload.toString());
        } catch (Exception ignored) {
            return false;
        }
    }

    private static void postReceiptHttp(Context context, String messageId, String receiptType) {
        CLIENT.dispatcher().executorService().execute(() -> {
            String cookie = CookieManager.getInstance().getCookie(API_BASE);
            if (cookie == null || cookie.trim().isEmpty()) return;
            try {
                JSONObject payload = new JSONObject()
                    .put("message_id", messageId)
                    .put("receipt_type", receiptType)
                    .put("channel", "android-realtime")
                    .put("occurred_at", nowIso());
                Request request = new Request.Builder()
                    .url(API_BASE + "/api/outbox/receipt")
                    .header("Cookie", cookie)
                    .post(RequestBody.create(payload.toString(), JSON))
                    .build();
                try (Response ignored = CLIENT.newCall(request).execute()) {
                    // The server persists the receipt; a later outbox sync remains the recovery path.
                }
            } catch (Exception ignored) {
                // Open receipts are best-effort in the internal-test build.
            }
        });
    }

    private static SharedPreferences preferences(Context context) {
        return context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    private static int stableId(String key) {
        int hash = key.hashCode() & 0x7fffffff;
        return hash == 0 ? 1 : hash;
    }

    private static String nowIso() {
        SimpleDateFormat format = new SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss.SSS'Z'", Locale.US);
        format.setTimeZone(TimeZone.getTimeZone("UTC"));
        return format.format(new Date());
    }

    private final class RealtimeListener extends WebSocketListener {
        @Override
        public void onOpen(WebSocket webSocket, Response response) {
            if (socket != webSocket) return;
            reconnectAttempt = 0;
            setState("connected");
        }

        @Override
        public void onMessage(WebSocket webSocket, String text) {
            if (socket == webSocket) handleMessage(text);
        }

        @Override
        public void onClosed(WebSocket webSocket, int code, String reason) {
            if (socket != webSocket) return;
            socket = null;
            if (!stopping && isEnabled(LuminousRealtimeService.this)) {
                setState("reconnecting");
                scheduleReconnect(0L);
            }
        }

        @Override
        public void onFailure(WebSocket webSocket, Throwable throwable, @Nullable Response response) {
            if (socket != webSocket) return;
            socket = null;
            if (response != null && response.code() == 401) setState("login_required");
            else setState("reconnecting");
            if (!stopping && isEnabled(LuminousRealtimeService.this)) {
                scheduleReconnect(response != null && response.code() == 401 ? 15_000L : 0L);
            }
        }
    }
}
