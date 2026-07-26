const VALID_KINDS = new Set([
  'offline',
  'timeout',
  'validation',
  'not-found',
  'model-unavailable',
  'server',
  'cancelled',
  'unknown',
]);

const RETRYABLE_KINDS = new Set([
  'offline',
  'timeout',
  'model-unavailable',
  'server',
  'unknown',
]);

const SAFE_MESSAGES = {
  offline: '暂时无法连接。',
  timeout: '这次等待有些久。',
  validation: '这条内容暂时无法发送。',
  'not-found': '暂时找不到需要的内容。',
  'model-unavailable': '栖光暂时无法回应。',
  server: '连接暂时不稳定。',
  cancelled: '请求已取消。',
  unknown: '出现了暂时无法确认的问题。',
};

export class AppError extends Error {
  constructor(kind, options = {}) {
    const safeKind = VALID_KINDS.has(kind) ? kind : 'unknown';
    super(SAFE_MESSAGES[safeKind], options.cause ? { cause: options.cause } : undefined);
    this.name = 'AppError';
    this.kind = safeKind;
    this.status = Number.isInteger(options.status) ? options.status : null;
    this.retryable = RETRYABLE_KINDS.has(safeKind);
  }
}

export function appErrorFromStatus(status) {
  if (status === 400) {
    return new AppError('validation', { status });
  }
  if (status === 404) {
    return new AppError('not-found', { status });
  }
  if (status === 503) {
    return new AppError('model-unavailable', { status });
  }
  if (status >= 500 && status <= 599) {
    return new AppError('server', { status });
  }
  return new AppError('unknown', { status });
}

export function toAppError(error) {
  return error instanceof AppError
    ? error
    : new AppError('unknown', { cause: error instanceof Error ? error : undefined });
}
