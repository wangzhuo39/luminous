/**
 * Creates a client-side single-flight and stale-response gate.
 * @param {string} [prefix='operation']
 */
export function createOperationGate(prefix = 'operation') {
  const safePrefix = typeof prefix === 'string' && prefix.trim()
    ? Array.from(prefix.trim()).slice(0, 48).join('')
    : 'operation';
  let counter = 0;
  let currentToken = null;

  const begin = () => {
    if (currentToken !== null) return null;
    counter += 1;
    currentToken = `${safePrefix}-${counter}`;
    return currentToken;
  };
  const isCurrent = (token) => (
    typeof token === 'string' && token !== '' && token === currentToken
  );
  const finish = (token) => {
    if (!isCurrent(token)) return false;
    currentToken = null;
    return true;
  };
  const cancel = (token) => finish(token);
  const isPending = () => currentToken !== null;

  return Object.freeze({ begin, isCurrent, finish, cancel, isPending });
}
