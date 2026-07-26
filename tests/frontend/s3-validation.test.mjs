import test from 'node:test';
import assert from 'node:assert/strict';
import {
  deepCloneAndFreeze,
  isPlainObject,
  normalizeBoundedText,
  normalizeEnum,
  normalizeOpaqueKey,
  normalizeOptionalText,
} from '../../apps/companion-web/companion-ui/js/shared/validation.js';

test('plain-object checks accept only ordinary and null-prototype records', () => {
  assert.equal(isPlainObject({}), true);
  assert.equal(isPlainObject(Object.create(null)), true);
  assert.equal(isPlainObject([]), false);
  assert.equal(isPlainObject(new Date()), false);
  assert.equal(isPlainObject(null), false);
});

test('bounded text handles required, optional and outer whitespace', () => {
  assert.equal(normalizeBoundedText(123, 10), '');
  assert.equal(normalizeBoundedText(123, 10, { required: true }), null);
  assert.equal(normalizeOptionalText(123, 10), null);
  assert.equal(normalizeBoundedText('  hello  ', 10), 'hello');
  assert.equal(normalizeBoundedText('  hello  ', 10, { preserveOuterWhitespace: true }), '  hello  ');
  assert.equal(normalizeBoundedText('   ', 10, { required: true }), null);
});

test('bounded text retains CR LF tab and Chinese while removing unsafe controls', () => {
  const input = 'a\x00b\x09c\x0Ad\x0De\x1Ff\x7F中文';
  assert.equal(normalizeBoundedText(input, 50), 'ab\x09c\x0Ad\x0Def中文');
});

test('bounded text counts code points and rejects invalid lengths', () => {
  assert.equal(normalizeBoundedText('😀😃😄😁', 2), '😀😃');
  assert.equal(normalizeBoundedText('a😀b', 2), 'a😀');
  [0, -1, 1.5, '5', Number.NaN].forEach((length) => {
    assert.throws(() => normalizeBoundedText('test', length), TypeError);
  });
});

test('enum and opaque-key normalization are finite and deterministic', () => {
  assert.equal(normalizeEnum('a', ['a', 'b']), 'a');
  assert.equal(normalizeEnum('c', new Set(['a', 'b'])), 'unknown');
  assert.equal(normalizeEnum(123, ['123']), 'unknown');
  assert.equal(normalizeOpaqueKey('  validKey  '), 'validKey');
  assert.equal(normalizeOpaqueKey('   '), null);
  assert.equal(normalizeOpaqueKey(123), null);
  const key256 = '😀'.repeat(256);
  assert.equal(normalizeOpaqueKey(key256), key256);
  assert.equal(normalizeOpaqueKey('😀'.repeat(257)), null);
});

test('JSON-safe cloning is independent and recursively frozen', () => {
  const original = { str: 'text', num: 42, bool: true, nul: null, arr: [{ nested: 'value' }] };
  const before = JSON.stringify(original);
  const cloned = deepCloneAndFreeze(original);
  assert.notEqual(cloned, original);
  assert.notEqual(cloned.arr, original.arr);
  assert.notEqual(cloned.arr[0], original.arr[0]);
  assert.deepEqual(cloned, original);
  assert.equal(JSON.stringify(original), before);
  assert.equal(Object.isFrozen(cloned), true);
  assert.equal(Object.isFrozen(cloned.arr), true);
  assert.equal(Object.isFrozen(cloned.arr[0]), true);
});

test('JSON-safe cloning rejects unsafe values, cycles and keys', () => {
  [
    Number.NaN, Infinity, -Infinity, undefined, () => {}, 1n,
    new Date(), new Map(), new Set(),
  ].forEach((value) => assert.throws(() => deepCloneAndFreeze(value), TypeError));
  const circularObject = {};
  circularObject.self = circularObject;
  const circularArray = [];
  circularArray.push(circularArray);
  assert.throws(() => deepCloneAndFreeze(circularObject), TypeError);
  assert.throws(() => deepCloneAndFreeze(circularArray), TypeError);
  assert.throws(() => deepCloneAndFreeze({ __proto__: { a: 1 } }), TypeError);
  assert.throws(() => deepCloneAndFreeze({ prototype: {} }), TypeError);
  assert.throws(() => deepCloneAndFreeze({ constructor: {} }), TypeError);
});
