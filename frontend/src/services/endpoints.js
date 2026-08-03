function withQuery(base, params = {}) {
  const qs = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value == null) continue
    qs.set(key, Array.isArray(value) ? value.join(',') : value)
  }
  const query = qs.toString()
  return query ? `${base}?${query}` : base
}

export const endpoints = {
  monitoring: {
    status: '/api/monitoring/status',
    audits: (params) => withQuery('/api/monitoring/audits', params),
  },
  marketData: {
    stream: '/api/market-data/stream',
    snapshot: '/api/market-data/snapshot',
  },
  pricing: {
    stream: '/api/pricing/valuation-stream',
    valuations: '/api/pricing/valuations',
  },
  blotter: {
    // Books without the trade payload. Trades uses the heavier `tradesOverview`
    // aggregate because it needs both; Generator only needs the book list.
    booksSummary: '/api/blotter/books/summary',
    trades: (params) => withQuery('/api/blotter/trades', params),
    trade: (tradeId) => `/api/blotter/trades/${encodeURIComponent(tradeId)}`,
    tradesOverview: (params) => withQuery('/api/blotter/trades/overview', params),
  },
  tradeAction: {
    submit: '/api/trade-action/trade-actions',
    queueStatus: '/api/trade-action/queue/status',
  },
  tradeGeneration: {
    status: '/api/trade-generation/status',
    start: '/api/trade-generation/start',
    stop: '/api/trade-generation/stop',
    generateOnce: '/api/trade-generation/generate-once',
    config: '/api/trade-generation/config',
  },
}
