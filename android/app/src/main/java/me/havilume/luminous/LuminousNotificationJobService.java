package me.havilume.luminous;

import android.Manifest;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.job.JobInfo;
import android.app.job.JobParameters;
import android.app.job.JobScheduler;
import android.app.job.JobService;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.net.Uri;
import android.os.Build;
import android.webkit.CookieManager;

import androidx.core.app.NotificationCompat;
import androidx.core.app.NotificationManagerCompat;
import androidx.core.content.ContextCompat;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.text.ParseException;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Date;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.TimeZone;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public final class LuminousNotificationJobService extends JobService {
    private static final String API_BASE = "https://app.havilume.me";
    private static final String CHANNEL_ID = "luminous_messages";
    private static final String PREFS = "luminous_notification_sync";
    private static final String SEEN_IDS = "seen_message_ids";
    private static final String SYNC_STARTED_AT = "sync_started_at";
    private static final int PERIODIC_JOB_ID = 0x4c554d01;
    private static final int IMMEDIATE_JOB_ID = 0x4c554d02;
    private static final long PERIOD_MS = 15L * 60L * 1000L;
    private static final Set<String> NOTIFIABLE_STATUSES = new HashSet<>(Arrays.asList(
        "drafted", "queued", "retrying", "delivering", "sent", "delivered"
    ));

    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private Future<?> running;

    public static void schedule(Context context) {
        SharedPreferences preferences = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        if (!preferences.contains(SYNC_STARTED_AT)) {
            preferences.edit().putLong(SYNC_STARTED_AT, System.currentTimeMillis()).apply();
        }
        JobScheduler scheduler = context.getSystemService(JobScheduler.class);
        if (scheduler == null) return;
        ComponentName service = new ComponentName(context, LuminousNotificationJobService.class);
        JobInfo periodic = new JobInfo.Builder(PERIODIC_JOB_ID, service)
            .setRequiredNetworkType(JobInfo.NETWORK_TYPE_ANY)
            .setPersisted(true)
            .setPeriodic(PERIOD_MS)
            .build();
        scheduler.schedule(periodic);
        JobInfo immediate = new JobInfo.Builder(IMMEDIATE_JOB_ID, service)
            .setRequiredNetworkType(JobInfo.NETWORK_TYPE_ANY)
            .setMinimumLatency(3_000L)
            .setOverrideDeadline(30_000L)
            .build();
        scheduler.schedule(immediate);
    }

    @Override
    public boolean onStartJob(JobParameters params) {
        running = executor.submit(() -> {
            boolean retry = false;
            try {
                retry = !syncOutbox();
            } catch (Exception ignored) {
                retry = true;
            } finally {
                jobFinished(params, retry);
            }
        });
        return true;
    }

    @Override
    public boolean onStopJob(JobParameters params) {
        if (running != null) running.cancel(true);
        return true;
    }

    @Override
    public void onDestroy() {
        executor.shutdownNow();
        super.onDestroy();
    }

    private boolean syncOutbox() throws Exception {
        if (!notificationsAllowed()) return true;
        String cookie = CookieManager.getInstance().getCookie(API_BASE);
        if (cookie == null || cookie.trim().isEmpty()) return true;
        HttpURLConnection connection = open("GET", "/api/outbox?limit=50", cookie);
        int status = connection.getResponseCode();
        if (status == HttpURLConnection.HTTP_UNAUTHORIZED) {
            connection.disconnect();
            return true;
        }
        if (status < 200 || status >= 300) {
            connection.disconnect();
            return false;
        }
        JSONObject response = new JSONObject(readBody(connection.getInputStream()));
        connection.disconnect();
        JSONArray items = response.optJSONArray("items");
        if (items == null) return true;

        SharedPreferences preferences = getSharedPreferences(PREFS, MODE_PRIVATE);
        long syncStartedAt = preferences.getLong(SYNC_STARTED_AT, System.currentTimeMillis());
        Set<String> seen = new HashSet<>(preferences.getStringSet(SEEN_IDS, new HashSet<>()));
        List<String> orderedSeen = new ArrayList<>(seen);
        for (int index = 0; index < items.length(); index += 1) {
            JSONObject item = items.optJSONObject(index);
            if (item == null) continue;
            String messageId = item.optString("message_id", "").trim();
            String body = item.optString("draft_text", "").trim();
            String itemStatus = item.optString("status", "").trim();
            if (messageId.isEmpty() || body.isEmpty() || seen.contains(messageId)) continue;
            if (!NOTIFIABLE_STATUSES.contains(itemStatus)) continue;
            long createdAt = parseTimestamp(item.optString("created_at", ""));
            if (createdAt > 0L && createdAt < syncStartedAt - 5L * 60L * 1000L) {
                remember(orderedSeen, seen, messageId);
                continue;
            }
            showNotification(messageId, body);
            remember(orderedSeen, seen, messageId);
            postReceipt(cookie, messageId);
        }
        int from = Math.max(orderedSeen.size() - 200, 0);
        preferences.edit().putStringSet(SEEN_IDS, new HashSet<>(orderedSeen.subList(from, orderedSeen.size()))).apply();
        return true;
    }

    private void remember(List<String> ordered, Set<String> seen, String messageId) {
        if (seen.add(messageId)) ordered.add(messageId);
    }

    private boolean notificationsAllowed() {
        return Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU
            || ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS)
                == PackageManager.PERMISSION_GRANTED;
    }

    private void showNotification(String messageId, String body) {
        createChannel();
        Intent intent = new Intent(
            Intent.ACTION_VIEW,
            Uri.parse("havilume://app?space=outbox&message_id=" + Uri.encode(messageId)),
            this,
            MainActivity.class
        );
        intent.setFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        PendingIntent pendingIntent = PendingIntent.getActivity(
            this,
            stableId(messageId),
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
        );
        NotificationCompat.Builder notification = new NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_stat_luminous)
            .setColor(Color.rgb(159, 199, 216))
            .setContentTitle("叶筝的来信")
            .setContentText(body)
            .setStyle(new NotificationCompat.BigTextStyle().bigText(body))
            .setContentIntent(pendingIntent)
            .setAutoCancel(true)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setCategory(NotificationCompat.CATEGORY_MESSAGE);
        try {
            NotificationManagerCompat.from(this).notify(stableId(messageId), notification.build());
        } catch (SecurityException ignored) {
            // Notification permission can be revoked between the explicit check and delivery.
        }
    }

    private void createChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return;
        NotificationManager manager = getSystemService(NotificationManager.class);
        if (manager == null) return;
        NotificationChannel channel = new NotificationChannel(
            CHANNEL_ID,
            "栖光来信",
            NotificationManager.IMPORTANCE_HIGH
        );
        channel.setDescription("提醒与叶筝主动发来的消息");
        channel.enableVibration(true);
        manager.createNotificationChannel(channel);
    }

    private void postReceipt(String cookie, String messageId) {
        HttpURLConnection connection = null;
        try {
            connection = open("POST", "/api/outbox/receipt", cookie);
            connection.setRequestProperty("Content-Type", "application/json; charset=utf-8");
            JSONObject payload = new JSONObject()
                .put("message_id", messageId)
                .put("receipt_type", "notification_displayed")
                .put("channel", "android-local");
            byte[] encoded = payload.toString().getBytes(StandardCharsets.UTF_8);
            connection.setDoOutput(true);
            connection.setFixedLengthStreamingMode(encoded.length);
            try (OutputStream output = connection.getOutputStream()) {
                output.write(encoded);
            }
            connection.getResponseCode();
        } catch (Exception ignored) {
            // A missing receipt must not duplicate a notification already shown locally.
        } finally {
            if (connection != null) connection.disconnect();
        }
    }

    private HttpURLConnection open(String method, String path, String cookie) throws Exception {
        HttpURLConnection connection = (HttpURLConnection) new URL(API_BASE + path).openConnection();
        connection.setRequestMethod(method);
        connection.setConnectTimeout(10_000);
        connection.setReadTimeout(15_000);
        connection.setRequestProperty("Accept", "application/json");
        connection.setRequestProperty("Cookie", cookie);
        return connection;
    }

    private static String readBody(InputStream stream) throws Exception {
        StringBuilder body = new StringBuilder();
        try (BufferedReader reader = new BufferedReader(new InputStreamReader(stream, StandardCharsets.UTF_8))) {
            String line;
            while ((line = reader.readLine()) != null) body.append(line);
        }
        return body.toString();
    }

    private static long parseTimestamp(String value) {
        if (value == null || value.trim().isEmpty()) return 0L;
        String[] patterns = {
            "yyyy-MM-dd'T'HH:mm:ss.SSSXXX",
            "yyyy-MM-dd'T'HH:mm:ssXXX",
            "yyyy-MM-dd'T'HH:mm:ss.SSS'Z'",
            "yyyy-MM-dd'T'HH:mm:ss'Z'"
        };
        for (String pattern : patterns) {
            SimpleDateFormat format = new SimpleDateFormat(pattern, Locale.US);
            format.setTimeZone(TimeZone.getTimeZone("UTC"));
            try {
                Date parsed = format.parse(value);
                if (parsed != null) return parsed.getTime();
            } catch (ParseException ignored) {
                // Try the next supported ISO-8601 form.
            }
        }
        return 0L;
    }

    private static int stableId(String key) {
        int hash = key.hashCode() & 0x7fffffff;
        return hash == 0 ? 1 : hash;
    }
}
