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
}
