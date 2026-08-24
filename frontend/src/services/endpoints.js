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
    logs: (params) => withQuery('/api/monitoring/logs', params),
    logsStream: '/api/monitoring/logs/stream',
  },
  marketData: {
    stream: '/api/market-data/stream',
    snapshot: '/api/market-data/snapshot',
    providers: '/api/market-data/providers',
    quoteHistory: (provider, symbol, limit = 60, raw = false) =>
      withQuery(
        `/api/market-data/quotes/${encodeURIComponent(provider)}/${encodeURIComponent(symbol)}/history`,
        { limit, raw: raw ? 1 : null },
      ),
    fxRates: (to) => withQuery('/api/market-data/fx/rates', { to }),
    curves: (raw = false) => withQuery('/api/market-data/curves', { raw: raw ? 1 : null }),
    curvesRefresh: (curve) => withQuery('/api/market-data/curves/refresh', { curve }),
    watchlist: '/api/market-data/watchlist',
    watchlistItem: (symbol, provider) =>
      withQuery(`/api/market-data/watchlist/${encodeURIComponent(symbol)}`, { provider }),
    symbolSearch: (q) => withQuery('/api/market-data/symbols/search', { q }),
  },
  pricing: {
    stream: '/api/pricing/valuation-stream',
    valuations: '/api/pricing/valuations',
    bookRisk: '/api/pricing/book-risk',
    price: '/api/pricing/price',
  },
  books: {
    list: '/api/books/books',
    book: (bookId) => `/api/books/books/${encodeURIComponent(bookId)}`,
  },
  blotter: {
    // Books without the trade payload; Trades uses the heavier `tradesOverview`
    // aggregate because it needs both.
    booksSummary: '/api/blotter/books/summary',
    trades: (params) => withQuery('/api/blotter/trades', params),
    trade: (tradeId) => `/api/blotter/trades/${encodeURIComponent(tradeId)}`,
    tradesOverview: (params) => withQuery('/api/blotter/trades/overview', params),
  },
  tradeAction: {
    submit: '/api/trade-action/trade-actions',
    queueStatus: '/api/trade-action/queue/status',
    instruments: '/api/trade-action/instruments',
    termSchemas: '/api/trade-action/instruments/term-schemas',
  },
}
