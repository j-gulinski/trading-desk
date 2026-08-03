export function buildCloseTradeIntent(tradeId, closePrice) {
  return {
    action_type: 'CLOSE_TRADE',
    trade_id: tradeId,
    close_price: Number.isFinite(closePrice) ? closePrice : null,
    close_reason: 'MANUAL_CLOSE',
    client_request_id: crypto.randomUUID(),
  }
}

function count(value) {
  const n = Number(value)
  return Number.isFinite(n) ? n : 0
}

export function queueStatusOf(raw) {
  if (raw == null) {
    return {
      available: false,
      accepted: 0,
      processed: 0,
      created: 0,
      closed: 0,
      rejected: 0,
    }
  }

  return {
    available: true,
    accepted: count(raw.accepted),
    processed: count(raw.processed),
    created: count(raw.created),
    closed: count(raw.closed),
    rejected: count(raw.rejected),
  }
}

export function lastActionAtOf(rows) {
  if (!Array.isArray(rows)) return null
  let newest = null
  for (const row of rows) {
    if (Number.isFinite(row.atMs) && (newest == null || row.atMs > newest)) newest = row.atMs
  }
  return newest
}
