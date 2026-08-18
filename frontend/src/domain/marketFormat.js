import { formatUnitPrice, unitPriceDecimals } from './formatting.js'

function currencyPair(symbol) {
  if (!/^[A-Z]{6}$/.test(symbol ?? '')) return null
  return { base: symbol.slice(0, 3), quote: symbol.slice(3) }
}

export function formatTenor(years) {
  return years < 1 ? `${Math.round(years * 12)}M` : `${years}Y`
}

export function formatValue(instrument) {
  if (!Number.isFinite(instrument.value)) return '—'
  if (instrument.unit === 'rate') return `${(instrument.value * 100).toFixed(4)}%`
  return formatUnitPrice(instrument.value, instrument.assetClass)
}

export function formatMarketSymbol(instrument) {
  const pair = currencyPair(instrument.symbol)
  if (pair && (instrument.assetClass === 'FX' || instrument.assetClass === 'COMMODITY')) {
    return `${pair.base}/${pair.quote}`
  }
  return instrument.symbol
}

export function formatValueUnit(instrument) {
  const pair = currencyPair(instrument.symbol)
  if (instrument.assetClass === 'EQUITY') return instrument.currency ?? 'USD'
  if (instrument.assetClass === 'FX' && pair) return ''
  if (instrument.assetClass === 'COMMODITY' && pair?.base === 'XAU') {
    return `${pair.quote}/oz`
  }
  if (instrument.unit === 'rate') return 'yield'
  return instrument.currency ?? ''
}

export function formatBidAsk(instrument) {
  if (!Number.isFinite(instrument.bid) || !Number.isFinite(instrument.ask)) return '—'
  return `${formatUnitPrice(instrument.bid, instrument.assetClass)} / ${formatUnitPrice(
    instrument.ask,
    instrument.assetClass,
  )}`
}

export function formatDelta(instrument, delta) {
  if (!Number.isFinite(delta)) return '—'
  if (instrument.unit === 'rate') {
    const basisPoints = delta * 10000
    if (basisPoints === 0) return '0 bp'
    const decimals = Math.abs(basisPoints) < 0.1 ? 2 : 1
    const rounded = Number(basisPoints.toFixed(decimals))
    if (rounded === 0) return '0 bp'
    const sign = rounded > 0 ? '+' : '-'
    const magnitude = Math.abs(rounded).toFixed(decimals).replace(/\.0+$/, '')
    return `${sign}${magnitude} bp`
  }
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
