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
    curves: (raw = false) => withQuery('/api/market-data/curves', { raw: raw ? 1 : null }),
    curveRevision: (provider, curve, asOf) => (
      `/api/market-data/curves/${encodeURIComponent(provider)}/${encodeURIComponent(curve)}/${encodeURIComponent(asOf)}`
    ),
    refresh: (symbol, provider) =>
      withQuery('/api/market-data/refresh', { symbol, provider }),
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
    curveAt: (curveName, params) =>
      withQuery(`/api/pricing/curves/${encodeURIComponent(curveName)}/at`, params),
  },
  books: {
    list: '/api/books/books',
    book: (bookId) => `/api/books/books/${encodeURIComponent(bookId)}`,
  },
  blotter: {
    booksSummary: (currency) => withQuery('/api/blotter/books/summary', { currency }),
    trades: (params) => withQuery('/api/blotter/trades', params),
    trade: (tradeId) => `/api/blotter/trades/${encodeURIComponent(tradeId)}`,
    tradesOverview: (params) => withQuery('/api/blotter/trades/overview', params),
  },
  tradeAction: {
    submit: '/api/trade-action/trade-actions',
    termSchemas: '/api/trade-action/instruments/term-schemas',
  },
}
