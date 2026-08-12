import { TRADE_QUANTITY_BOUNDS } from '../config/tradeActions.js'
import { formatNumber } from './formatting.js'

export function newOpenTradeRequestId() {
  return `manual-open-${crypto.randomUUID()}`
}

export function instrumentCatalogOf(raw) {
  return (Array.isArray(raw) ? raw : [])
    .filter(
      (instrument) =>
        typeof instrument?.symbol === 'string' &&
        typeof instrument?.asset_class === 'string',
    )
    .map((instrument) => ({
      ...instrument,
      assetClass: instrument.asset_class,
      currency: instrument.currency ?? 'USD',
    }))
}

export function tradeableInstrumentsOf(instruments, assetClass) {
  if (!assetClass) return []
  return (Array.isArray(instruments) ? instruments : []).filter(
      (instrument) => instrument.assetClass === assetClass,
    )
    .sort((a, b) => a.symbol.localeCompare(b.symbol))
}

export function termSchemaOf(raw, assetClass) {
  const schema = raw?.[assetClass]
  if (schema == null || schema.customizable !== true || !Array.isArray(schema.fields)) return null
  return schema
}

function fieldScaleOf(field) {
  return field.unit === 'percent' ? 100 : 1
}

export function termErrorsOf(fields, values) {
  const errors = {}
  for (const field of fields) {
    const raw = values[field.name]
    if (raw == null || raw === '') {
      errors[field.name] = 'Required.'
      continue
    }
    if (field.type === 'choice') {
      if (!field.choices.includes(raw)) errors[field.name] = 'Pick a value.'
      continue
    }
    const scale = fieldScaleOf(field)
    const value = Number(raw)
    if (!Number.isFinite(value)) errors[field.name] = 'Must be a number.'
    else if (field.type === 'integer' && !Number.isInteger(value)) errors[field.name] = 'Must be a whole number.'
    else if (field.gt != null && !(value > field.gt * scale)) errors[field.name] = `Must be greater than ${field.gt * scale}.`
    else if (field.ge != null && !(value >= field.ge * scale)) errors[field.name] = `Must be at least ${field.ge * scale}.`
    else if (field.max != null && !(value <= field.max * scale)) errors[field.name] = `Must be at most ${field.max * scale}.`
  }
  return errors
}

export function termsFromValues(fields, values) {
  const terms = {}
  for (const field of fields) {
    terms[field.name] = field.type === 'choice'
      ? values[field.name]
      : Number(values[field.name]) / fieldScaleOf(field)
  }
  return terms
}

function maturityTag(maturityYears) {
  const maturity = Number(maturityYears)
  if (!Number.isFinite(maturity) || maturity <= 0) return ''
  return maturity < 1 ? `${Math.round(maturity * 12)}M` : `${maturity}Y`
}

export function derivedSymbolOf(assetClass, terms) {
  const tag = maturityTag(terms.maturity_years)
  let symbol = ''
  if (assetClass === 'EUROPEAN_OPTION' && terms.underlying_symbol && terms.option_type) {
    symbol = `${terms.underlying_symbol}_${terms.option_type}_${terms.strike ?? ''}_${tag}`
  } else if (assetClass === 'IRS' && terms.direction) {
    const direction = terms.direction === 'PAY_FIXED_RECEIVE_FLOAT' ? 'PAY_FIXED' : 'RECEIVE_FIXED'
    symbol = `USD_IRS_${direction}_${tag}`
  }
  return String(symbol)
    .toUpperCase()
    .replace(/[^A-Z0-9_.-]/g, '_')
    .replace(/_+/g, '_')
    .replace(/^_+|_+$/g, '')
    .slice(0, 32)
}

export function tradeFormErrorsOf({ bookId, symbol, quantity, price, assetClass }) {
  const errors = {}
  if (!bookId) errors.book = 'Pick a book.'
  if (!symbol) errors.instrument = 'Pick an instrument.'
  if (
    !Number.isSafeInteger(quantity) ||
    quantity < TRADE_QUANTITY_BOUNDS.min ||
    quantity > TRADE_QUANTITY_BOUNDS.max
  ) {
    errors.quantity = `Quantity must be a whole number between ${formatNumber(
      TRADE_QUANTITY_BOUNDS.min,
    )} and ${formatNumber(TRADE_QUANTITY_BOUNDS.max)}.`
  }
  if (symbol && !Number.isFinite(price)) {
    errors.price = 'No market price received for this instrument yet.'
  } else if (symbol && assetClass !== 'IRS' && price < 0.005) {
    errors.price = 'Mark rounds to 0.00 — not tradeable at these terms.'
  }
  return errors
}

export function buildOpenTradeIntent({
  clientRequestId,
  bookId,
  assetClass,
  symbol,
  side,
  quantity,
  price,
  currency,
  terms,
}) {
  const intent = {
    action_type: 'OPEN_TRADE',
    client_request_id: clientRequestId,
    book_id: bookId,
    asset_class: assetClass,
    symbol,
    side,
    quantity,
    trade_price: price.toFixed(4),
    currency: currency ?? 'USD',
    source: 'MANUAL',
  }
  if (terms != null) intent.terms = terms
  return intent
}

export function buildReassignIntent(sourceBookId, targetBookId) {
  return {
    action_type: 'REASSIGN_TRADES',
    book_id: sourceBookId,
    target_book_id: targetBookId,
    client_request_id: `manual-move-${crypto.randomUUID()}`,
  }
}

export function buildCloseTradeIntent(tradeId, closePrice) {
  return {
    action_type: 'CLOSE_TRADE',
    trade_id: tradeId,
    close_price: Number.isFinite(closePrice) ? closePrice : null,
    close_reason: 'MANUAL_CLOSE',
    client_request_id: crypto.randomUUID(),
  }
}

function count(value) {
  const n = Number(value)
  return Number.isFinite(n) ? n : 0
}

function countOrNull(value) {
  const n = Number(value)
  return Number.isFinite(n) ? n : null
}

export function queueStatusOf(raw) {
  if (raw == null) {
    return {
      available: false,
      accepted: 0,
      processed: 0,
      created: 0,
      closed: 0,
      rejected: 0,
      avgProcessingMs: null,
      lastProcessingMs: null,
    }
  }

  return {
    available: true,
    accepted: count(raw.accepted),
    processed: count(raw.processed),
    created: count(raw.created),
    closed: count(raw.closed),
    rejected: count(raw.rejected),
    avgProcessingMs: countOrNull(raw.avg_processing_ms),
    lastProcessingMs: countOrNull(raw.last_processing_ms),
  }
}

export function lastActionAtOf(rows) {
  if (!Array.isArray(rows)) return null
  let newest = null
  for (const row of rows) {
    if (Number.isFinite(row.atMs) && (newest == null || row.atMs > newest)) newest = row.atMs
  }
  return newest
}
