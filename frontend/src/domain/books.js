import {
  BOOK_ASSET_CLASSES,
  BOOK_DESCRIPTION_MAX_LENGTH,
  BOOK_NAME_MAX_LENGTH,
} from '../config/books.js'
import { statusOf } from './valuations.js'
import { toNum, toTime } from './values.js'

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
      subtotals: (Array.isArray(book.subtotals) ? book.subtotals : []).map((row) => ({
        currency: row.currency,
        values: {
          unrealized: toNum(row.values?.unrealized) ?? 0,
          realized: toNum(row.values?.realized) ?? 0,
        },
      })),
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

function positionStatusOf(position, now, instruments, curves) {
  const unvalued = toNum(position.unvalued) ?? 0
  const valuedAt = toTime(position.valuation_time)
  if (unvalued > 0 || !Number.isFinite(valuedAt)) return 'PENDING'

  const payload = position.valuation_payload ?? {}
  const provider = position.market_data_provider ?? null
  const underlying = payload.underlying_symbol ?? null
  const discountCurve = payload.discount_curve ?? null

  return statusOf(
    {
      closed: false,
      symbol: position.symbol,
      marketDataProvider: provider,
      marketDataTimestampMs: toTime(
        position.oldest_market_data_timestamp ?? position.market_data_timestamp,
      ),
      receivedAtMs: toTime(position.oldest_valuation_time ?? position.valuation_time),
      discountCurve,
      curveAsOf: payload.curve_as_of ?? null,
      curveReceivedAtMs: toTime(payload.curve_received_at),
      projectionCurve: payload.projection_curve ?? null,
      projectionCurveAsOf: payload.projection_curve_as_of ?? null,
      projectionCurveReceivedAtMs: toTime(payload.projection_curve_received_at),
      underlyingSymbol: underlying,
    },
    now,
    instruments,
    curves,
  )
}

export function bookPositionsOf(book, now, instruments = {}, curves = {}) {
  return (book?.positions ?? []).map((position) => {
    const provider = position.market_data_provider ?? null
    return {
      id: `${position.symbol}:${position.currency ?? 'N/A'}:${provider ?? 'MODEL'}`,
      symbol: position.symbol,
      provider,
      currency: position.currency ?? null,
      assetClass: position.asset_class ?? 'UNKNOWN',
      netQuantity: toNum(position.net_quantity) ?? 0,
      averageEntry: toNum(position.average_entry),
      price: toNum(position.current_price),
      unrealizedPnl: toNum(position.unrealized_pnl) ?? 0,
      status: positionStatusOf(position, now, instruments, curves),
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
