import test from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { pathToFileURL } from 'node:url';
import {
  formatISOToLocalAllDay,
  formatISOToLocalTimed,
  getBrowserTimeZone,
  isISOInstant,
  isValidTimeRange,
  parseLocalAllDayToISO,
  parseLocalTimedToISO,
} from '../../apps/companion-web/companion-ui/js/shared/time.js';

const SOURCE_FILE = '/home/wz/luminous/apps/companion-web/companion-ui/js/shared/time.js';

test('timezone resolver normalizes and trims', () => {
  assert.equal(getBrowserTimeZone(() => '  Asia/Shanghai  '), 'Asia/Shanghai');
  assert.equal(getBrowserTimeZone(() => 'UTC'), 'UTC');
});

test('provided invalid timezone resolvers use UTC without reading Intl', () => {
  assert.equal(getBrowserTimeZone(() => ''), 'UTC');
  assert.equal(getBrowserTimeZone(() => null), 'UTC');
  assert.equal(getBrowserTimeZone(() => 42), 'UTC');
  assert.equal(getBrowserTimeZone(() => { throw new Error('test'); }), 'UTC');
});

test('strict ISO instants accept Z and numeric offsets', () => {
  assert.equal(isISOInstant('2024-01-01T12:00:00Z'), true);
  assert.equal(isISOInstant('2024-01-01T12:00:00+08:00'), true);
  assert.equal(isISOInstant('2024-01-01T12:00:00-05:00'), true);
  assert.equal(isISOInstant('2024-01-01T12:00:00.123Z'), true);
});

test('strict ISO instants reject missing offsets and impossible values', () => {
  const invalid = [
    '2024-01-01', '2024-01-01T12:00:00', '2023-02-30T10:00:00Z',
    '2023-02-29T10:00:00Z', '2024-01-01T24:00:00Z',
    '2024-01-01T12:00:60Z', '2024-01-01T12:00:00+24:00',
    '2024-01-01T12:00:00+00:60',
  ];
  invalid.forEach((value) => assert.equal(isISOInstant(value), false, value));
});

test('local timed parsing rejects format and calendar overflow', () => {
  assert.equal(parseLocalTimedToISO('2024-02-30T12:00'), null);
  assert.equal(parseLocalTimedToISO('2024-01-01T24:00'), null);
  assert.equal(parseLocalTimedToISO('2024-01-01T12:60'), null);
  assert.equal(parseLocalTimedToISO('0999-01-01T12:00'), null);
  assert.equal(parseLocalTimedToISO('invalid'), null);
});

test('leap days are accepted only in leap years', () => {
  assert.ok(parseLocalTimedToISO('2024-02-29T00:00')?.endsWith('Z'));
  assert.ok(parseLocalAllDayToISO('2024-02-29')?.endsWith('Z'));
  assert.equal(parseLocalAllDayToISO('2023-02-29'), null);
});

test('all-day values round-trip in the current local timezone', () => {
  const value = '2025-12-25';
  const instant = parseLocalAllDayToISO(value);
  assert.ok(instant);
  assert.equal(formatISOToLocalAllDay(instant), value);
  assert.equal(parseLocalAllDayToISO('2025-13-01'), null);
  assert.equal(parseLocalAllDayToISO('2025-12-32'), null);
});

test('timed values round-trip without truncating a UTC instant', () => {
  const value = '2026-05-20T15:45';
  const instant = parseLocalTimedToISO(value);
  assert.ok(instant);
  assert.equal(formatISOToLocalTimed(instant), value);
});

test('time ranges allow open/equal ends and reject earlier or invalid ends', () => {
  const first = '2024-01-01T10:00:00Z';
  const later = '2024-01-01T11:00:00Z';
  assert.equal(isValidTimeRange(first, null), true);
  assert.equal(isValidTimeRange(first, first), true);
  assert.equal(isValidTimeRange(first, later), true);
  assert.equal(isValidTimeRange(later, first), false);
  assert.equal(isValidTimeRange('invalid', later), false);
  assert.equal(isValidTimeRange(first, '2024-01-01T11:00:00'), false);
});

test('DST gaps fail local round-trip validation', () => {
  const script = `
    import { parseLocalTimedToISO } from '${pathToFileURL(SOURCE_FILE).href}';
    process.stdout.write(String(parseLocalTimedToISO('2026-03-08T02:30') === null));
  `;
  const result = spawnSync(process.execPath, ['--input-type=module', '-e', script], {
    env: { ...process.env, TZ: 'America/New_York' },
    encoding: 'utf8',
  });
  assert.equal(result.status, 0, result.stderr);
  assert.equal(result.stdout, 'true');
});
