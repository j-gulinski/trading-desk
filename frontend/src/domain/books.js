import {
  BOOK_ASSET_CLASSES,
  BOOK_DESCRIPTION_MAX_LENGTH,
  BOOK_NAME_MAX_LENGTH,
} from '../config/books.js'
import { VALUATION_STALE_AFTER_MS } from '../config/valuations.js'

function toNum(value) {
  if (value == null || value === '') return null
  const n = Number(value)
  return Number.isFinite(n) ? n : null
}

export function bookSummariesOf(raw) {
  return (Array.isArray(raw) ? raw : [])
    .filter((book) => typeof book?.book_id === 'string' && book.book_id.length > 0)
    .map((book) => ({
      id: book.book_id,
      name: book.name ?? book.book_id,
      assetClass: book.expected_asset_class ?? 'UNKNOWN',
      activeTrades: toNum(book.active_trades) ?? 0,
      closedTrades: toNum(book.closed_trades) ?? 0,
      realizedPnl: toNum(book.realized_pnl),
      unrealizedPnl: toNum(book.unrealized_pnl),
      currency: book.currency ?? null,
      isActive: book.is_active !== false,
    }))
}

export function moveTargetsOf(books, book) {
  if (book == null) return []
  return books.filter(
    (other) => other.isActive && other.id !== book.id && other.assetClass === book.assetClass,
  )
}

export function summarizeBooks(books) {
  return {
    books: books.length,
    openPositions: books.reduce((sum, book) => sum + book.activeTrades, 0),
  }
}

export function bookPositionsOf(trades, now) {
  const positions = new Map()

  for (const trade of Array.isArray(trades) ? trades : []) {
    const symbol = trade.symbol ?? 'UNKNOWN'
    let position = positions.get(symbol)
    if (!position) {
      position = {
        id: symbol,
        symbol,
        assetClass: trade.asset_class ?? 'UNKNOWN',
        trades: 0,
        netQuantity: 0,
        grossQuantity: 0,
        entryCost: 0,
        unrealizedPnl: 0,
        price: null,
        valuedAtMs: null,
        unvalued: 0,
        stale: 0,
      }
      positions.set(symbol, position)
    }

    const quantity = toNum(trade.quantity) ?? 0
    const signed = trade.side === 'SELL' ? -quantity : quantity
    const entryPrice = toNum(trade.trade_price)
    position.trades += 1
    position.netQuantity += signed
    position.grossQuantity += Math.abs(quantity)
    if (entryPrice != null) position.entryCost += Math.abs(quantity) * entryPrice

    const valuation = trade.latest_valuation
    if (valuation == null) {
      position.unvalued += 1
      continue
    }
    position.unrealizedPnl += toNum(valuation.unrealized_pnl) ?? 0
    const valuedAt = Date.parse(valuation.valuation_time ?? '')
    if (!Number.isFinite(valuedAt)) {
      position.unvalued += 1
      continue
    }
    if (now - valuedAt > VALUATION_STALE_AFTER_MS) position.stale += 1
    if (position.valuedAtMs == null || valuedAt >= position.valuedAtMs) {
      position.valuedAtMs = valuedAt
      position.price = toNum(valuation.current_price)
    }
  }

  return Array.from(positions.values())
    .map((position) => ({
      ...position,
      averageEntry: position.grossQuantity > 0 ? position.entryCost / position.grossQuantity : null,
      status: position.unvalued > 0 || position.stale > 0 ? 'STALE' : 'LIVE',
    }))
    .sort((a, b) => a.symbol.localeCompare(b.symbol))
}

export function bookFormValuesOf(book) {
  return {
    name: book?.name ?? '',
    description: book?.description ?? '',
    assetClass: book?.expected_asset_class ?? '',
  }
}

export function bookFormErrorsOf(values) {
  const errors = {}
  const name = values.name.trim()
  if (name.length === 0) {
    errors.name = 'Name is required.'
  } else if (name.length > BOOK_NAME_MAX_LENGTH) {
    errors.name = `Name must be at most ${BOOK_NAME_MAX_LENGTH} characters.`
  }
  if (!BOOK_ASSET_CLASSES.includes(values.assetClass)) {
    errors.assetClass = 'Pick an asset class.'
  }
  if (values.description.trim().length > BOOK_DESCRIPTION_MAX_LENGTH) {
    errors.description = `Description must be at most ${BOOK_DESCRIPTION_MAX_LENGTH} characters.`
  }
  return errors
}

export function bookPayloadOf(values) {
  const description = values.description.trim()
  return {
    name: values.name.trim(),
    description: description.length > 0 ? description : null,
    expected_asset_class: values.assetClass,
  }
}
