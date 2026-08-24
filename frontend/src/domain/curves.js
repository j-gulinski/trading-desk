function toNum(value) {
  if (value == null || value === '') return null
  const n = Number(value)
  return Number.isFinite(n) ? n : null
}

function toTime(value) {
  const parsed = Date.parse(value ?? '')
  return Number.isFinite(parsed) ? parsed : null
}

function pointOf(raw) {
  const years = toNum(raw?.tenor_years)
  const rate = toNum(raw?.rate)
  if (years == null || rate == null) return null
  return {
    label: raw.tenor_label ?? `${years}Y`,
    years,
    rate,
    sourceSeries: raw.source_series ?? null,
    sourceAsOf: raw.source_as_of ?? null,
    derived: raw.source_series == null,
  }
}

export function curveOf(tick) {
  if (!tick || typeof tick.curve_name !== 'string' || tick.curve_name.length === 0) {
    return null
  }
  const points = (Array.isArray(tick.points) ? tick.points : [])
    .map(pointOf)
    .filter(Boolean)
    .sort((a, b) => a.years - b.years)
  if (points.length === 0) return null
  return {
    name: tick.curve_name,
    provider: typeof tick.provider === 'string' ? tick.provider : null,
    curveType: tick.curve_type ?? null,
    currency: tick.currency ?? null,
    indexTenor: tick.index_tenor ?? null,
    asOfDate: tick.as_of_date ?? null,
    receivedAtMs: toTime(tick.received_at),
    eventTimeMs: toTime(tick.event_time),
    points,
  }
}

export function mergeCurves(previous, updates) {
  let curves = previous
  for (const update of updates) {
    const current = curves[update.name]
    if (
      current &&
      Number.isFinite(current.eventTimeMs) &&
      Number.isFinite(update.eventTimeMs) &&
      update.eventTimeMs < current.eventTimeMs
    ) {
      continue
    }
    if (curves === previous) curves = { ...curves }
    curves[update.name] = update
  }
  return curves
}

export function curvesFromSnapshot(snapshot) {
  return Object.values(snapshot?.curves ?? {})
    .map(curveOf)
    .filter(Boolean)
}

export function curveOptionLabel(curve) {
  const tenor = curve.index_tenor ? ` · ${curve.index_tenor} index` : ''
  return `${curve.curve_name} · ${curve.currency}${tenor} · as of ${curve.as_of_date}`
}
