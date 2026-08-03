const GENERATED_PREFIX = 'gen-'

const DIRECTION_BY_EVENT = {
  TRADE_CREATED: { direction: 'IN', label: 'TRADE_IN', tone: 'healthy' },
  TRADE_CLOSED: { direction: 'OUT', label: 'TRADE_OUT', tone: 'stale' },
  ACTION_REJECTED: { direction: 'REJECTED', label: 'REJECTED', tone: 'down' },
}

export function generatorStatusOf(raw) {
  const config = raw?.config ?? {}
  const intervalMs = Number(config.interval_ms)
  const targetOpenTrades = Number(config.target_open_trades)
  const closeProbability = Number(raw?.close_probability)

  return {
    available: raw != null,
    running: raw?.running === true,
    opened: Number(raw?.opened) || 0,
    closed: Number(raw?.closed) || 0,
    failed: Number(raw?.failed) || 0,
    openTrades: Number(raw?.open_trades) || 0,
    intervalMs: Number.isFinite(intervalMs) ? intervalMs : null,
    targetOpenTrades: Number.isFinite(targetOpenTrades) ? targetOpenTrades : null,
    closeProbability: Number.isFinite(closeProbability) ? closeProbability : null,
  }
}

function isGeneratedIntent(event) {
  return typeof event?.correlationId === 'string'
    && event.correlationId.startsWith(GENERATED_PREFIX)
}

export function intentRowsOf(events, { generatedOnly = false } = {}) {
  if (!Array.isArray(events)) return []
  const rows = []
  for (const event of events) {
    const mapped = DIRECTION_BY_EVENT[event.eventType]
    if (!mapped) continue
    const generated = isGeneratedIntent(event)
    if (generatedOnly && !generated) continue
    rows.push({
      id: event.id,
      atMs: event.createdAtMs,
      direction: mapped.direction,
      label: mapped.label,
      tone: mapped.tone,
      tradeId: event.entityId,
      correlationId: event.correlationId,
      message: event.message,
      generated,
      source: generated ? 'GENERATED' : 'MANUAL',
    })
  }
  return rows
}

export function summarizeIntents(rows) {
  const summary = { total: rows.length, opened: 0, closed: 0, rejected: 0 }
  for (const row of rows) {
    if (row.direction === 'IN') summary.opened += 1
    else if (row.direction === 'OUT') summary.closed += 1
    else summary.rejected += 1
  }
  return summary
}
