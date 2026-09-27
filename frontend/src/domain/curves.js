import { CURVE_BASIS_TEXT, CURVE_TEXT } from '../config/marketData.js'
import { providerFullName } from '../config/providers.js'
import { toNum, toTime } from './values.js'

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
    family: tick.curve_family ?? null,
    displayName: tick.display_name ?? null,
    displayQualifier: tick.display_qualifier ?? null,
    provider: typeof tick.provider === 'string' ? tick.provider : null,
    curveBasis: tick.curve_basis ?? null,
    roles: Array.isArray(tick.roles) ? tick.roles : [],
    uses: Array.isArray(tick.uses) ? tick.uses : [],
    currency: tick.currency ?? null,
    indexTenor: tick.index_tenor ?? null,
    asOfDate: tick.as_of_date ?? null,
    receivedAt: typeof tick.received_at === 'string' ? tick.received_at : null,
    receivedAtMs: toTime(tick.received_at),
    eventTimeMs: toTime(tick.event_time),
    points,
  }
}

export function mergeCurves(previous, updates) {
  let curves = previous
  for (const update of updates) {
    const current = curves[update.name]
    if (current) {
      const currentRevision = `${current.asOfDate ?? ''}|${String(
        current.receivedAtMs ?? current.eventTimeMs ?? '',
      ).padStart(16, '0')}`
      const updateRevision = `${update.asOfDate ?? ''}|${String(
        update.receivedAtMs ?? update.eventTimeMs ?? '',
      ).padStart(16, '0')}`
      if (updateRevision <= currentRevision) continue
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

function curveNameOf(curve) {
  if (typeof curve === 'string') return curve
  return curve?.name ?? curve?.curve_name ?? null
}

export function curveTitle(curve) {
  const curveName = curveNameOf(curve)
  if (typeof curve === 'object' && curve != null) {
    const displayName = curve.displayName ?? curve.display_name
    const qualifier = curve.displayQualifier ?? curve.display_qualifier
    if (displayName) return qualifier ? `${displayName} · ${qualifier}` : displayName
  }
  return CURVE_TEXT[curveName]?.title ?? curveName ?? 'Unknown curve'
}

export function curveSourceName(provider) {
  return providerFullName(provider)
}

export function curveTradeUse(curve) {
  const curveName = curveNameOf(curve)
  return CURVE_TEXT[curveName]?.tradeUse ?? 'Research only'
}

export function curveBasisText(curveBasis) {
  return CURVE_BASIS_TEXT[curveBasis] ?? 'derivation not stated'
}

export function indexTenorText(indexTenor) {
  if (indexTenor == null) return null
  const months = Number(String(indexTenor).replace(/\D/g, ''))
  return Number.isFinite(months) && months > 0 ? `${months}-month` : String(indexTenor)
}

export function curveOptionLabel(curve) {
  const title = curveTitle(curve)
  return curve.currency ? `${curve.currency} · ${title}` : title
}
