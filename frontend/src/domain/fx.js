import { REPORTING_CURRENCY_BASE_OPTIONS } from '../config/marketData.js'
import { toNum } from './values.js'

function displayRate(rate) {
  return new Intl.NumberFormat('en-US', {
    minimumFractionDigits: 4,
    maximumFractionDigits: 6,
    useGrouping: false,
  }).format(rate)
}

export function fxOf(raw) {
  if (raw == null) return null
  const rate = toNum(raw.rate)
  if (rate == null) return { rate: null, label: null, reason: raw.reason ?? null }
  return {
    rate,
    label: raw.provider == null
      ? null
      : `${raw.path} ${displayRate(rate)} · ${raw.provider} · as of ${raw.as_of}`,
    reason: null,
  }
}

export function amountsOf(raw) {
  return {
    grossEntry: toNum(raw?.gross_entry),
    unrealized: toNum(raw?.unrealized),
    realized: toNum(raw?.realized),
    total: toNum(raw?.total),
  }
}

export function reportedOf(raw) {
  const excluded = (Array.isArray(raw?.excluded) ? raw.excluded : []).map((row) => ({
    currency: row.currency,
    reason: row.reason,
  }))
  return {
    currency: raw?.currency ?? 'MIXED',
    values: amountsOf(raw),
    excluded,
    title: excluded.length > 0 ? excluded.map((row) => row.reason).join('; ') : undefined,
  }
}

export function reportingCurrencyOptions(subtotals) {
  const options = new Set(REPORTING_CURRENCY_BASE_OPTIONS)
  for (const row of subtotals) options.add(row.currency)
  return [...options].sort()
}
