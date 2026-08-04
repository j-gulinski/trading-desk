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
      positions: Array.isArray(book.positions) ? book.positions : [],
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

export function bookPositionsOf(book, now) {
  return (book?.positions ?? []).map((position) => {
    const valuedAt = Date.parse(position.valuation_time ?? '')
    const stale =
      position.unvalued > 0 ||
      !Number.isFinite(valuedAt) ||
      now - valuedAt > VALUATION_STALE_AFTER_MS
    return {
      id: position.symbol,
      symbol: position.symbol,
      assetClass: position.asset_class ?? 'UNKNOWN',
      netQuantity: toNum(position.net_quantity) ?? 0,
      averageEntry: toNum(position.average_entry),
      price: toNum(position.current_price),
      unrealizedPnl: toNum(position.unrealized_pnl) ?? 0,
      status: stale ? 'STALE' : 'LIVE',
    }
  })
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
