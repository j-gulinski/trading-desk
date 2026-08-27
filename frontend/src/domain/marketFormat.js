import { unitPriceDecimals } from './formatting.js'

function currencyPair(symbol) {
  if (!/^[A-Z]{6}$/.test(symbol ?? '')) return null
  return { base: symbol.slice(0, 3), quote: symbol.slice(3) }
}

function baseCurrencyOf(symbol) {
  return currencyPair(symbol)?.base ?? null
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
  if (instrument.symbol === 'XAUPLN_G') return 'GOLD (1 g)'
  const pair = currencyPair(instrument.symbol)
  if (pair && (instrument.assetClass === 'FX' || instrument.assetClass === 'COMMODITY')) {
    return `${pair.base}/${pair.quote}`
  }
  return instrument.symbol
}

export function marketLabelOf(instrument) {
  if (instrument.assetClass === 'FX' || instrument.assetClass === 'COMMODITY') return 'OTC'
  if (instrument.assetClass !== 'EQUITY') return '—'
  if (typeof instrument.market === 'string' && instrument.market.length > 0) {
    return instrument.market
  }
  const separator = instrument.symbol?.lastIndexOf(':') ?? -1
  if (separator > 0 && separator < instrument.symbol.length - 1) {
    return instrument.symbol.slice(separator + 1)
  }
  return '—'
}

export function unitLabelOf(instrument) {
  if (instrument.symbol === 'XAUPLN_G') return 'PLN per gram'
  const pair = currencyPair(instrument.symbol)
  if (pair && instrument.assetClass === 'FX') {
    return `${pair.quote} per ${pair.base}`
  }
  if (pair && instrument.assetClass === 'COMMODITY') {
    return `${pair.quote} per ${pair.base} (troy oz)`
  }
  return null
}

export function priceUnitLabelOf(instrument) {
  if (instrument.symbol === 'XAUPLN_G') return 'PLN/g'
  const pair = currencyPair(instrument.symbol)
  if (pair && instrument.assetClass === 'FX') return `${pair.quote}/${pair.base}`
  if (pair && instrument.assetClass === 'COMMODITY') return `${pair.quote}/${pair.base} oz`
  if (instrument.assetClass === 'EQUITY') {
    return instrument.currency ? `${instrument.currency}/sh` : '/sh'
  }
  if (instrument.assetClass === 'EUROPEAN_OPTION') {
    return instrument.currency ? `${instrument.currency}/contract` : '/contract'
  }
  if (instrument.assetClass === 'BOND') {
    return instrument.currency ? `${instrument.currency}/100` : '/100'
  }
  if (instrument.assetClass === 'IRS') {
    return instrument.currency ? `${instrument.currency} NPV` : 'NPV'
  }
  return instrument.currency ?? null
}

export function quantityUnitLabelOf(instrument) {
  if (instrument.assetClass === 'IRS') {
    return instrument.currency ? `${instrument.currency} notional` : 'notional'
  }
  if (instrument.assetClass === 'BOND') {
    return instrument.currency ? `${instrument.currency} face` : 'face'
  }
  if (instrument.assetClass === 'EUROPEAN_OPTION') return 'contracts'
  if (instrument.assetClass === 'EQUITY') return 'shares'
  if (instrument.symbol === 'XAUPLN_G') return 'grams'
  const base = baseCurrencyOf(instrument.symbol)
  return base ?? null
}

export function formatAsOfDate(ms) {
  if (!Number.isFinite(ms)) return '—'
  const d = new Date(ms)
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}`
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
