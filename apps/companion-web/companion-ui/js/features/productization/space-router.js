const VALID_SPACES = new Set(['today', 'outbox', 'memory', 'privacy']);

export function readSpaceFromURL(value) {
  const url = value instanceof URL ? value : new URL(String(value), 'http://localhost/');
  const requested = url.searchParams.get('space');
  return VALID_SPACES.has(requested) ? requested : null;
}

export function buildSpaceURL(value, space) {
  const url = value instanceof URL ? new URL(value.href) : new URL(String(value), 'http://localhost/');
  if (VALID_SPACES.has(space)) url.searchParams.set('space', space);
  else url.searchParams.delete('space');
  return url;
}

export function initSpaceRouter(windowRef, { setSpace, onStateChange = () => {} }) {
  let destroyed = false;

  const applyLocation = ({ normalize = true, render = true } = {}) => {
    if (destroyed) return null;
    const url = new URL(windowRef.location.href);
    const requested = url.searchParams.get('space');
    const space = readSpaceFromURL(url);
    if (normalize && requested !== null && !space) {
      url.searchParams.delete('space');
      windowRef.history.replaceState({}, '', `${url.pathname}${url.search}${url.hash}`);
    }
    setSpace(space);
    if (render) onStateChange();
    return space;
  };

  const navigate = (space, { replace = false } = {}) => {
    if (destroyed) return null;
    const normalized = VALID_SPACES.has(space) ? space : null;
    const url = buildSpaceURL(windowRef.location.href, normalized);
    const next = `${url.pathname}${url.search}${url.hash}`;
    const current = `${windowRef.location.pathname}${windowRef.location.search}${windowRef.location.hash}`;
    setSpace(normalized);
    if (next !== current) {
      windowRef.history[replace ? 'replaceState' : 'pushState']({}, '', next);
    }
    return normalized;
  };

  const handlePopState = () => applyLocation();
  windowRef.addEventListener('popstate', handlePopState);

  return Object.freeze({
    applyInitial() { return applyLocation({ render: false }); },
    navigate,
    destroy() {
      destroyed = true;
      windowRef.removeEventListener('popstate', handlePopState);
    },
  });
}
