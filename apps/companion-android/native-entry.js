import { App } from '@capacitor/app';
import { Capacitor, registerPlugin } from '@capacitor/core';
import { LocalNotifications } from '@capacitor/local-notifications';

const API_BASE = 'https://app.havilume.me';
const ACTIVE_REMINDER_STATUSES = new Set(['scheduled', 'due', 'snoozed']);
const listeners = [];
const RealtimeCompanion = registerPlugin('RealtimeCompanion');

window.__LUMINOUS_NATIVE__ = Capacitor.isNativePlatform();
window.__LUMINOUS_API_BASE__ = window.__LUMINOUS_NATIVE__ ? API_BASE : '';

function stableNotificationId(key) {
  let hash = 2166136261;
  for (const character of String(key)) {
    hash ^= character.codePointAt(0);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0) % 2_000_000_000 || 1;
}

function openSpace(space = 'outbox', messageId = '') {
  const safeSpace = ['today', 'outbox', 'memory', 'privacy'].includes(space) ? space : 'outbox';
  const url = new URL(window.location.href);
  url.searchParams.set('space', safeSpace);
  if (messageId) url.searchParams.set('message_id', messageId);
  else url.searchParams.delete('message_id');
  window.history.pushState({}, '', `${url.pathname}${url.search}${url.hash}`);
  window.dispatchEvent(new PopStateEvent('popstate'));
}

async function permissionState() {
  if (!window.__LUMINOUS_NATIVE__) {
    return { native: false, local: 'denied', delivery: 'unavailable' };
  }
  const local = await LocalNotifications.checkPermissions();
  const realtime = await RealtimeCompanion.getState().catch(() => ({
    enabled: false,
    running: false,
    status: 'unavailable',
  }));
  return {
    native: true,
    local: local.display,
    delivery: realtime.enabled ? 'realtime-websocket' : 'periodic-local',
    realtime,
  };
}

function dispatchNotificationState() {
  window.dispatchEvent(new CustomEvent('luminous:native-notification-state'));
}

async function enableNotifications() {
  if (!window.__LUMINOUS_NATIVE__) return permissionState();
  const permission = await LocalNotifications.requestPermissions();
  if (permission.display === 'granted') await RealtimeCompanion.start();
  dispatchNotificationState();
  return permissionState();
}

async function disableRealtime() {
  if (!window.__LUMINOUS_NATIVE__) return permissionState();
  await RealtimeCompanion.stop();
  dispatchNotificationState();
  return permissionState();
}

async function acknowledgeNotification(messageId, receiptType = 'notification_opened') {
  if (!window.__LUMINOUS_NATIVE__ || !messageId) return;
  await RealtimeCompanion.acknowledge({ messageId, receiptType }).catch(() => {});
}

function reminderSchedule(reminder, at) {
  const allowWhileIdle = true;
  if (reminder.recurrence === 'daily') {
    return { on: { hour: at.getHours(), minute: at.getMinutes() }, allowWhileIdle };
  }
  if (reminder.recurrence === 'weekly') {
    return {
      on: { weekday: at.getDay() + 1, hour: at.getHours(), minute: at.getMinutes() },
      allowWhileIdle,
    };
  }
  return { at: new Date(Math.max(at.getTime(), Date.now() + 1_000)), allowWhileIdle };
}

async function syncReminder(reminder) {
  if (!window.__LUMINOUS_NATIVE__ || !reminder?.key) return false;
  const id = stableNotificationId(reminder.key);
  await LocalNotifications.cancel({ notifications: [{ id }] });
  if (!ACTIVE_REMINDER_STATUSES.has(reminder.status)) return true;
  const at = new Date(reminder.dueAt);
  if (!Number.isFinite(at.getTime())) return false;
  const permissions = await LocalNotifications.checkPermissions();
  if (permissions.display !== 'granted') return false;
  await LocalNotifications.schedule({
    notifications: [{
      id,
      title: reminder.title,
      body: reminder.description || '叶筝提醒你看看今天的约定。',
      schedule: reminderSchedule(reminder, at),
      channelId: 'luminous_messages',
      smallIcon: 'ic_stat_luminous',
      iconColor: '#9fc7d8',
      extra: { space: 'today', reminderId: reminder.key },
    }],
  });
  return true;
}

function listen(plugin, eventName, handler) {
  const pending = plugin.addListener(eventName, handler);
  listeners.push(() => pending.then((handle) => handle.remove()).catch(() => {}));
}

function handleAppUrl(url) {
  try {
    const parsed = new URL(url);
    const messageId = parsed.searchParams.get('message_id') || '';
    openSpace(parsed.searchParams.get('space') || 'outbox', messageId);
    void acknowledgeNotification(messageId);
  } catch { openSpace('outbox'); }
}

async function initialize() {
  if (!window.__LUMINOUS_NATIVE__) return permissionState();
  await LocalNotifications.createChannel({
    id: 'luminous_messages',
    name: '栖光来信',
    description: '提醒与叶筝主动发来的消息',
    importance: 5,
    visibility: 1,
    vibration: true,
  }).catch(() => {});
  listen(LocalNotifications, 'localNotificationActionPerformed', ({ notification }) => {
    const messageId = notification?.extra?.messageId || '';
    openSpace(notification?.extra?.space || 'today', messageId);
    void acknowledgeNotification(messageId);
  });
  listen(App, 'appUrlOpen', ({ url }) => handleAppUrl(url));
  const launch = await App.getLaunchUrl().catch(() => null);
  if (launch?.url) handleAppUrl(launch.url);
  listen(App, 'appStateChange', async ({ isActive }) => {
    if (!isActive) return;
    dispatchNotificationState();
  });
  return permissionState();
}

window.LuminousNative = Object.freeze({
  apiBase: API_BASE,
  acknowledgeNotification,
  disableRealtime,
  enableNotifications,
  permissionState,
  reminderSchedule,
  stableNotificationId,
  syncReminder,
});
window.LuminousNativeReady = initialize();

window.addEventListener('pagehide', () => {
  listeners.splice(0).forEach((dispose) => dispose());
}, { once: true });
