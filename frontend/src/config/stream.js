export const FLUSH_INTERVAL_MS = 500
export const FRESHNESS_INTERVAL_MS = 1000

export const STREAM_STATUS = {
  connecting: 'CONNECTING',
  connected: 'CONNECTED',
  reconnecting: 'RECONNECTING',
  suspended: 'SUSPENDED',
}

const STREAM_STATUS_LEVEL = {
  [STREAM_STATUS.connected]: 'healthy',
  [STREAM_STATUS.reconnecting]: 'degraded',
  [STREAM_STATUS.connecting]: 'unknown',
  [STREAM_STATUS.suspended]: 'unknown',
}

const STREAM_STATUS_LABEL = {
  [STREAM_STATUS.suspended]: 'PAUSED',
}

export function streamStatusLabel(status) {
  return STREAM_STATUS_LABEL[status] ?? status
}

export function streamStatusLevel(status) {
  return STREAM_STATUS_LEVEL[status] ?? 'unknown'
}
