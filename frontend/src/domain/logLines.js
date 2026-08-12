import { labelForService } from './auditEvents.js'
import { LOG_FEED_CAP, LOG_LEVELS, PULSE_SPAN_MINUTES, PULSE_WINDOW_MINUTES } from '../config/logs.js'

const LEVEL_TONE = {
  debug: 'unknown',
  info: 'info',
  warning: 'warning',
  error: 'error',
  critical: 'critical',
}

// Already shown in the row header — repeating them in the detail block is noise.
const HEADER_KEYS = new Set(['event', 'level', 'service', 'id', 'timestamp'])

export function payloadEntriesOf(payload) {
  if (payload == null || typeof payload !== 'object') return []
  return Object.entries(payload).filter(([key]) => !HEADER_KEYS.has(key))
}

export function normalizeLogLine(raw) {
  if (raw == null || typeof raw !== 'object') return null
  const level = LOG_LEVELS.includes(raw.level) ? raw.level : 'info'
  const atMs = Date.parse(raw.timestamp ?? '')
  return {
    id: raw.id,
    service: raw.service ?? null,
    serviceLabel: labelForService(raw.service),
    level,
    tone: LEVEL_TONE[level],
    atMs: Number.isNaN(atMs) ? null : atMs,
    event: String(raw.event ?? ''),
    correlationId: typeof raw.correlation_id === 'string' ? raw.correlation_id : null,
    payload: raw,
  }
}

export function normalizeLogLines(raw) {
  if (!Array.isArray(raw)) return []
  return raw.map(normalizeLogLine).filter(Boolean)
}

export function mergeLogLines(existing, incoming, cap = LOG_FEED_CAP) {
  if (!incoming || incoming.length === 0) return existing
  const byId = new Map()
  for (const line of existing) byId.set(line.id, line)
  for (const line of incoming) byId.set(line.id, line)
  return [...byId.values()].sort((a, b) => b.id - a.id).slice(0, cap)
}

export function levelAtLeast(level, minLevel) {
  return LOG_LEVELS.indexOf(level) >= LOG_LEVELS.indexOf(minLevel)
}

export function filterLogLines(lines, { service = null, minLevel = null, query = '' } = {}) {
  const needle = query.trim().toLowerCase()
  return lines.filter((line) => {
    if (service && line.service !== service) return false
    if (minLevel && !levelAtLeast(line.level, minLevel)) return false
    if (needle) {
      const haystack =
        `${line.event} ${line.correlationId ?? ''} ${JSON.stringify(line.payload)}`.toLowerCase()
      if (!haystack.includes(needle)) return false
    }
    return true
  })
}

function warnCountOf(bucket) {
  return (
    (Number(bucket?.warning) || 0) +
    (Number(bucket?.error) || 0) +
    (Number(bucket?.critical) || 0)
  )
}

export function minuteSeriesOf(minutes, nowMs, span = PULSE_SPAN_MINUTES) {
  const byMinute = new Map()
  for (const bucket of minutes ?? []) {
    const ms = Date.parse(bucket?.t ?? '')
    if (!Number.isNaN(ms)) byMinute.set(ms, warnCountOf(bucket))
  }
  const currentMinute = Math.floor(nowMs / 60000) * 60000
  const series = []
  for (let i = span - 1; i >= 0; i -= 1) {
    series.push(byMinute.get(currentMinute - i * 60000) ?? 0)
  }
  return series
}

export function logServicesOf(meta, nowMs) {
  const services = meta?.services
  if (services == null || typeof services !== 'object') return []
  return Object.entries(services)
    .map(([service, info]) => {
      const counts = info?.counts ?? {}
      const lastAtMs = Date.parse(info?.last_at ?? '')
      return {
        service,
        label: labelForService(service),
        buffered: Number(info?.buffered) || 0,
        lastAtMs: Number.isNaN(lastAtMs) ? null : lastAtMs,
        counts,
        warnPlus: warnCountOf(counts),
        warnSeries: minuteSeriesOf(info?.minutes, nowMs),
      }
    })
    .sort((a, b) => a.service.localeCompare(b.service))
}

export function warnPulseOf(meta, nowMs, windowMinutes = PULSE_WINDOW_MINUTES) {
  const services = meta?.services
  if (services == null || typeof services !== 'object') return 0
  const cutoff = nowMs - windowMinutes * 60000
  let total = 0
  for (const info of Object.values(services)) {
    for (const bucket of info?.minutes ?? []) {
      const ms = Date.parse(bucket?.t ?? '')
      if (!Number.isNaN(ms) && ms >= cutoff) total += warnCountOf(bucket)
    }
  }
  return total
}
