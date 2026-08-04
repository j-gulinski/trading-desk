import { TRADE_QUANTITY_BOUNDS } from '../config/tradeActions.js'
import { formatNumber } from './formatting.js'

export function newOpenTradeRequestId() {
  return `manual-open-${crypto.randomUUID()}`
}

export function tradeableInstrumentsOf(instruments, assetClass) {
  if (!assetClass) return []
  return Object.values(instruments ?? {})
    .filter(
      (instrument) => instrument.unit === 'price' && instrument.assetClass === assetClass,
    )
    .sort((a, b) => a.symbol.localeCompare(b.symbol))
}

export function tradeFormErrorsOf({ bookId, symbol, quantity, price }) {
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
}) {
  return {
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

export function queueStatusOf(raw) {
  if (raw == null) {
    return {
      available: false,
      accepted: 0,
      processed: 0,
      created: 0,
      closed: 0,
      rejected: 0,
    }
  }

  return {
    available: true,
    accepted: count(raw.accepted),
    processed: count(raw.processed),
    created: count(raw.created),
    closed: count(raw.closed),
    rejected: count(raw.rejected),
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
