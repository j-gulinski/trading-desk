export const FLUSH_INTERVAL_MS = 500
export const FRESHNESS_INTERVAL_MS = 1000

export const STREAM_STATUS = {
  connecting: 'CONNECTING',
  connected: 'CONNECTED',
  reconnecting: 'RECONNECTING',
}

const STREAM_STATUS_LEVEL = {
  [STREAM_STATUS.connected]: 'healthy',
  [STREAM_STATUS.reconnecting]: 'degraded',
  [STREAM_STATUS.connecting]: 'unknown',
}

export function streamStatusLevel(status) {
  return STREAM_STATUS_LEVEL[status] ?? 'unknown'
}
