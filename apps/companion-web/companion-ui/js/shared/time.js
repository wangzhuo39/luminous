/**
 * Gets the browser's time zone or falls back to 'UTC'.
 * @param {Function} [resolver] Optional function returning a timezone string.
 * @returns {string} A non-empty trimmed timezone string.
 */
export function getBrowserTimeZone(resolver) {
  if (typeof resolver === 'function') {
    try {
      const timeZone = resolver();
      if (typeof timeZone === 'string' && timeZone.trim()) {
        return timeZone.trim();
      }
    } catch {
      // Fall through to the deterministic default.
    }
    return 'UTC';
  }

  try {
    if (typeof Intl !== 'undefined' && Intl.DateTimeFormat) {
      const timeZone = Intl.DateTimeFormat().resolvedOptions().timeZone;
      if (typeof timeZone === 'string' && timeZone.trim()) {
        return timeZone.trim();
      }
    }
  } catch {
    // Fall through to the deterministic default.
  }
  return 'UTC';
}

const ISO_INSTANT_RE = /^([1-9]\d{3})-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])T([01]\d|2[0-3]):([0-5]\d):([0-5]\d)(?:\.(\d+))?(Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)$/;

/**
 * Checks an ISO datetime has an explicit offset and a real calendar date.
 * @param {unknown} value Value to validate.
 * @returns {boolean}
 */
export function isISOInstant(value) {
  if (typeof value !== 'string') return false;
  const match = value.match(ISO_INSTANT_RE);
  if (!match) return false;

  const year = Number.parseInt(match[1], 10);
  const month = Number.parseInt(match[2], 10);
  const day = Number.parseInt(match[3], 10);
  const hour = Number.parseInt(match[4], 10);
  const minute = Number.parseInt(match[5], 10);
  const second = Number.parseInt(match[6], 10);
  const fraction = match[7] || '000';
  const milliseconds = Number.parseInt(`${fraction}000`.slice(0, 3), 10);
  const wallTime = new Date(Date.UTC(
    year, month - 1, day, hour, minute, second, milliseconds,
  ));

  if (
    wallTime.getUTCFullYear() !== year
    || wallTime.getUTCMonth() !== month - 1
    || wallTime.getUTCDate() !== day
    || wallTime.getUTCHours() !== hour
    || wallTime.getUTCMinutes() !== minute
    || wallTime.getUTCSeconds() !== second
  ) return false;

  return !Number.isNaN(new Date(value).getTime());
}

const LOCAL_TIMED_RE = /^([1-9]\d{3})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/;

/**
 * Converts a strict local datetime value to a UTC ISO instant.
 * @param {unknown} value Local YYYY-MM-DDTHH:mm value.
 * @returns {string|null}
 */
export function parseLocalTimedToISO(value) {
  if (typeof value !== 'string') return null;
  const match = value.match(LOCAL_TIMED_RE);
  if (!match) return null;

  const year = Number.parseInt(match[1], 10);
  const month = Number.parseInt(match[2], 10);
  const day = Number.parseInt(match[3], 10);
  const hour = Number.parseInt(match[4], 10);
  const minute = Number.parseInt(match[5], 10);
  if (year < 1000) return null;

  const date = new Date(year, month - 1, day, hour, minute, 0, 0);
  if (
    date.getFullYear() === year
    && date.getMonth() === month - 1
    && date.getDate() === day
    && date.getHours() === hour
    && date.getMinutes() === minute
    && date.getSeconds() === 0
    && date.getMilliseconds() === 0
  ) return date.toISOString();
  return null;
}

const LOCAL_ALL_DAY_RE = /^([1-9]\d{3})-(\d{2})-(\d{2})$/;

/**
 * Converts a strict local date at midnight to a UTC ISO instant.
 * @param {unknown} value Local YYYY-MM-DD value.
 * @returns {string|null}
 */
export function parseLocalAllDayToISO(value) {
  if (typeof value !== 'string') return null;
  const match = value.match(LOCAL_ALL_DAY_RE);
  if (!match) return null;

  const year = Number.parseInt(match[1], 10);
  const month = Number.parseInt(match[2], 10);
  const day = Number.parseInt(match[3], 10);
  if (year < 1000) return null;

  const date = new Date(year, month - 1, day, 0, 0, 0, 0);
  if (
    date.getFullYear() === year
    && date.getMonth() === month - 1
    && date.getDate() === day
    && date.getHours() === 0
    && date.getMinutes() === 0
    && date.getSeconds() === 0
    && date.getMilliseconds() === 0
  ) return date.toISOString();
  return null;
}

function pad(number) {
  return String(number).padStart(2, '0');
}

/** @param {string} instant @returns {string|null} */
export function formatISOToLocalTimed(instant) {
  if (!isISOInstant(instant)) return null;
  const date = new Date(instant);
  const year = String(date.getFullYear()).padStart(4, '0');
  return `${year}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

/** @param {string} instant @returns {string|null} */
export function formatISOToLocalAllDay(instant) {
  if (!isISOInstant(instant)) return null;
  const date = new Date(instant);
  const year = String(date.getFullYear()).padStart(4, '0');
  return `${year}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

/**
 * Validates an optional-ended range of strict ISO instants.
 * @param {string} startInstant
 * @param {string|null|undefined} endInstant
 * @returns {boolean}
 */
export function isValidTimeRange(startInstant, endInstant) {
  if (!isISOInstant(startInstant)) return false;
  if (endInstant === null || endInstant === undefined || endInstant === '') return true;
  if (!isISOInstant(endInstant)) return false;
  return new Date(startInstant).getTime() <= new Date(endInstant).getTime();
}
