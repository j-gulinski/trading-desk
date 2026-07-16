import { DEGRADED_LATENCY_MS, STALE_AFTER_MS } from '../config/monitoring.js'

const MONITORING_SERVICE = 'monitoring-service'

const DISPLAY_ORDER = [
  'monitoring-service',
  'market-data-service',
  'pricing-service',
  'books-service',
  'blotter-service',
  'trade-generation-service',
  'trade-action-service',
]

function levelFor(info) {
  if (!info || !info.status) return 'unknown'
  if (info.status === 'DOWN') return 'down'
  if (info.status !== 'UP') return 'unknown'
  if (info.response_time_ms != null && info.response_time_ms > DEGRADED_LATENCY_MS) return 'degraded'
  return 'healthy'
}

function labelFor(name) {
  return name.replace(/-service$/, '').replace(/-/g, ' ').toUpperCase()
}

function checkedAtFor(id, info, monitoringCheckedAtMs) {
  const checkedAtMs = Date.parse(info?.last_checked ?? info?.checked_at ?? '')
  if (!Number.isNaN(checkedAtMs)) return checkedAtMs
  return id === MONITORING_SERVICE ? monitoringCheckedAtMs : null
}

function normalizedLevel(
  id,
  info,
  { freshnessKnown, stale, monitoringUnavailable },
) {
  if (monitoringUnavailable && id === MONITORING_SERVICE) return 'down'
  if (!freshnessKnown) return 'unknown'
  if (stale) return 'stale'
  return levelFor(info)
}

export function normalizeServiceStatus(
  raw,
  {
    now = Date.now(),
    monitoringCheckedAtMs = null,
    monitoringUnavailable = false,
  } = {},
) {
  const extraIds = Object.keys(raw ?? {}).filter((id) => !DISPLAY_ORDER.includes(id))

  return [...DISPLAY_ORDER, ...extraIds].map((id) => {
    const info = raw?.[id]
    const checkedAtMs = checkedAtFor(id, info, monitoringCheckedAtMs)
    const ageMs = checkedAtMs == null ? null : Math.max(0, now - checkedAtMs)
    const freshnessKnown = ageMs != null
    const stale = freshnessKnown && ageMs > STALE_AFTER_MS
    const monitoringDown = monitoringUnavailable && id === MONITORING_SERVICE

    return {
      id,
      label: labelFor(id),
      level: normalizedLevel(id, info, {
        freshnessKnown,
        stale,
        monitoringUnavailable,
      }),
      status: info?.status ?? 'UNKNOWN',
      latencyMs: stale || monitoringDown ? null : (info?.response_time_ms ?? null),
      ageMs,
      stale,
      error: info?.error ?? null,
    }
  })
}

export function summarize(list) {
  return {
    total: list.length,
    healthy: list.filter((s) => s.level === 'healthy').length,
    degraded: list.filter((s) => s.level === 'degraded').length,
    stale: list.filter((s) => s.level === 'stale').length,
    down: list.filter((s) => s.level === 'down').length,
    unknown: list.filter((s) => s.level === 'unknown').length,
  }
}
