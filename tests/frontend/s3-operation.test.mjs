import test from 'node:test';
import assert from 'node:assert/strict';
import { createOperationGate } from '../../apps/companion-web/companion-ui/js/shared/operation.js';

test('begin starts one pending operation and blocks a double begin', () => {
  const gate = createOperationGate();
  assert.equal(gate.isPending(), false);
  const token = gate.begin();
  assert.equal(typeof token, 'string');
  assert.equal(gate.isPending(), true);
  assert.equal(gate.begin(), null);
});

test('finish and cancel accept only the current token', () => {
  const gate = createOperationGate();
  const first = gate.begin();
  assert.equal(gate.finish('stale-token'), false);
  assert.equal(gate.isPending(), true);
  assert.equal(gate.finish(first), true);
  const second = gate.begin();
  assert.equal(gate.cancel('stale-token'), false);
  assert.equal(gate.cancel(second), true);
  assert.equal(gate.isPending(), false);
});

test('destructured gate methods do not depend on this', () => {
  const { begin, isCurrent, finish, cancel, isPending } = createOperationGate();
  const first = begin();
  assert.equal(isCurrent(first), true);
  assert.equal(cancel(first), true);
  const second = begin();
  assert.equal(finish(second), true);
  assert.equal(isPending(), false);
});

test('retry tokens are monotonic and separate gates are isolated', () => {
  const firstGate = createOperationGate();
  const secondGate = createOperationGate('other');
  const first = firstGate.begin();
  firstGate.finish(first);
  const retry = firstGate.begin();
  const other = secondGate.begin();
  assert.ok(first.endsWith('-1'));
  assert.ok(retry.endsWith('-2'));
  assert.ok(other.endsWith('-1'));
  assert.notEqual(retry, other);
});

test('prefixes trim, bound Unicode code points and fall back safely', () => {
  const trimmed = createOperationGate('   my-op   ');
  const bounded = createOperationGate('😀'.repeat(50));
  const fallback = createOperationGate(12345);
  assert.ok(trimmed.begin().startsWith('my-op-'));
  assert.ok(bounded.begin().startsWith(`${'😀'.repeat(48)}-`));
  assert.ok(fallback.begin().startsWith('operation-'));
  assert.equal(Object.isFrozen(trimmed), true);
});

test('isCurrent rejects empty and non-string values', () => {
  const gate = createOperationGate();
  const token = gate.begin();
  assert.equal(gate.isCurrent(token), true);
  ['', null, undefined, 123].forEach((value) => assert.equal(gate.isCurrent(value), false));
});
