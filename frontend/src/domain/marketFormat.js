import { unitPriceDecimals } from './formatting.js'

function currencyPair(symbol) {
  if (!/^[A-Z]{6}$/.test(symbol ?? '')) return null
  return { base: symbol.slice(0, 3), quote: symbol.slice(3) }
}

export function formatAge(ms) {
  if (!Number.isFinite(ms)) return '—'
  const s = Math.max(0, Math.floor(ms / 1000))
  if (s < 60) return `${s}s`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m ${s % 60}s`
  const h = Math.floor(m / 60)
  return `${h}h ${m % 60}m`
}

export function formatMarketSymbol(instrument) {
  const pair = currencyPair(instrument.symbol)
  if (pair && (instrument.assetClass === 'FX' || instrument.assetClass === 'COMMODITY')) {
    return `${pair.base}/${pair.quote}`
  }
  return instrument.symbol
}

export function formatDelta(instrument, delta) {
  if (!Number.isFinite(delta)) return '—'
  let dp = unitPriceDecimals(instrument.assetClass)
  let rounded = Number(delta.toFixed(dp))
  if (rounded === 0 && delta !== 0) {
    dp += 1
    rounded = Number(delta.toFixed(dp))
  }
  if (rounded === 0) return '0'
  const sign = rounded > 0 ? '+' : '-'
  return `${sign}${Math.abs(rounded).toFixed(dp)}`
}

export function formatPercentDelta(percent) {
  if (!Number.isFinite(percent)) return null
  const decimals = percent !== 0 && Math.abs(percent) < 0.01 ? 3 : 2
  const rounded = Number(percent.toFixed(decimals))
  if (rounded === 0) return `${(0).toFixed(decimals)}%`
  const sign = rounded > 0 ? '+' : '-'
  return `${sign}${Math.abs(rounded).toFixed(decimals)}%`
}
