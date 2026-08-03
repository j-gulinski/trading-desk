import {
  BOOK_ASSET_CLASSES,
  BOOK_DESCRIPTION_MAX_LENGTH,
  BOOK_NAME_MAX_LENGTH,
} from '../config/books.js'

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
    }))
}

export function summarizeBooks(books) {
  return {
    books: books.length,
    openPositions: books.reduce((sum, book) => sum + book.activeTrades, 0),
  }
}

export function bookPositionsOf(positions, bookId) {
  return positions.filter((position) => position.id.startsWith(`${bookId}::`))
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
