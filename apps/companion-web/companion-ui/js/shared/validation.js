/** @param {unknown} value @returns {boolean} */
export function isPlainObject(value) {
  if (typeof value !== 'object' || value === null) return false;
  const prototype = Object.getPrototypeOf(value);
  return prototype === null || prototype === Object.prototype;
}

const CONTROL_CHARS_RE = /[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]/g;

/**
 * Normalizes bounded user-visible text without splitting surrogate pairs.
 * @param {unknown} value
 * @param {number} maxLength
 * @param {{required?: boolean, preserveOuterWhitespace?: boolean}} [options]
 * @returns {string|null}
 */
export function normalizeBoundedText(value, maxLength, options = {}) {
  if (!Number.isInteger(maxLength) || maxLength <= 0) {
    throw new TypeError('maxLength must be a positive integer');
  }
  const required = options.required === true;
  const preserveOuterWhitespace = options.preserveOuterWhitespace === true;
  if (typeof value !== 'string') return required ? null : '';

  let normalized = value.replace(CONTROL_CHARS_RE, '');
  if (!preserveOuterWhitespace) normalized = normalized.trim();
  if (!normalized && required) return null;
  const codePoints = Array.from(normalized);
  return codePoints.length > maxLength
    ? codePoints.slice(0, maxLength).join('')
    : normalized;
}

/**
 * Normalizes optional text to a bounded string or null.
 * @param {unknown} value
 * @param {number} maxLength
 * @param {{preserveOuterWhitespace?: boolean}} [options]
 * @returns {string|null}
 */
export function normalizeOptionalText(value, maxLength, options = {}) {
  return normalizeBoundedText(value, maxLength, { ...options, required: true });
}

/** @param {unknown} value @param {ReadonlyArray<string>|Set<string>} allowed */
export function normalizeEnum(value, allowed) {
  if (typeof value !== 'string') return 'unknown';
  if (Array.isArray(allowed) && allowed.includes(value)) return value;
  if (allowed instanceof Set && allowed.has(value)) return value;
  return 'unknown';
}

/** @param {unknown} value @returns {string|null} */
export function normalizeOpaqueKey(value) {
  if (typeof value !== 'string') return null;
  const normalized = value.trim();
  if (!normalized || Array.from(normalized).length > 256) return null;
  return normalized;
}

const UNSAFE_OBJECT_KEYS = new Set(['__proto__', 'prototype', 'constructor']);

/**
 * Clones and recursively freezes a JSON-safe value.
 * @param {unknown} value
 * @param {Set<unknown>} [seen]
 * @returns {unknown}
 */
export function deepCloneAndFreeze(value, seen = new Set()) {
  if (value === null || typeof value === 'string' || typeof value === 'boolean') return value;
  if (typeof value === 'number') {
    if (Number.isFinite(value)) return value;
    throw new TypeError('value must be JSON-safe');
  }
  if (Array.isArray(value)) {
    if (seen.has(value)) throw new TypeError('value must be JSON-safe');
    seen.add(value);
    const clone = value.map((item) => deepCloneAndFreeze(item, seen));
    seen.delete(value);
    return Object.freeze(clone);
  }
  if (isPlainObject(value)) {
    if (seen.has(value)) throw new TypeError('value must be JSON-safe');
    seen.add(value);
    const clone = {};
    for (const key of Object.keys(value)) {
      if (UNSAFE_OBJECT_KEYS.has(key)) throw new TypeError('value must be JSON-safe');
      clone[key] = deepCloneAndFreeze(value[key], seen);
    }
    seen.delete(value);
    return Object.freeze(clone);
  }
  throw new TypeError('value must be JSON-safe');
}
