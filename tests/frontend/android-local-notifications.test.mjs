import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const root = new URL('../../', import.meta.url);
const source = (path) => readFile(new URL(path, root), 'utf8');

test('Android internal build uses foreground WebSocket with local polling fallback and no Google services', async () => {
  const [nativeEntry, packageJson, appGradle, rootGradle, jobService, realtimeService, plugin, manifest, buildScript] = await Promise.all([
    source('apps/companion-android/native-entry.js'),
    source('package.json'),
    source('android/app/build.gradle'),
    source('android/build.gradle'),
    source('android/app/src/main/java/me/havilume/luminous/LuminousNotificationJobService.java'),
    source('android/app/src/main/java/me/havilume/luminous/LuminousRealtimeService.java'),
    source('android/app/src/main/java/me/havilume/luminous/RealtimeCompanionPlugin.java'),
    source('android/app/src/main/AndroidManifest.xml'),
    source('scripts/build-android-web.mjs'),
  ]);

  assert.doesNotMatch(nativeEntry, /PushNotifications|notification-devices|provider:\s*['"]fcm/);
  assert.match(nativeEntry, /App\.getLaunchUrl\(\)/);
  assert.match(nativeEntry, /handleAppUrl\(launch\.url\)/);
  assert.match(buildScript, /registration\.unregister\(\)/);
  assert.match(buildScript, /key\.startsWith\('luminous-shell-'\)/);
  assert.doesNotMatch(packageJson, /@capacitor\/push-notifications/);
  assert.doesNotMatch(appGradle, /google-services/);
  assert.doesNotMatch(rootGradle, /google-services/);
  assert.match(jobService, /setPeriodic\(PERIOD_MS\)/);
  assert.match(jobService, /\/api\/outbox\?limit=50/);
  assert.match(jobService, /notification_displayed/);
  assert.match(realtimeService, /newWebSocket\(/);
  assert.match(realtimeService, /\/api\/realtime\/outbox\?since=/);
  assert.match(realtimeService, /START_STICKY/);
  assert.match(plugin, /@CapacitorPlugin\(name = "RealtimeCompanion"\)/);
  assert.match(manifest, /LuminousNotificationJobService/);
  assert.match(manifest, /LuminousRealtimeService/);
  assert.match(manifest, /android\.permission\.BIND_JOB_SERVICE/);
  assert.match(manifest, /android\.permission\.ACCESS_NETWORK_STATE/);
  assert.match(manifest, /android\.permission\.FOREGROUND_SERVICE_REMOTE_MESSAGING/);
  assert.match(manifest, /android:foregroundServiceType="remoteMessaging"/);
  assert.match(appGradle, /com\.squareup\.okhttp3:okhttp:4\.12\.0/);
});
