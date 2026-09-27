import { catalogueFieldsOf } from './catalogue.js'
import { amountsOf, fxOf, reportedOf } from './fx.js'
import { toNum, toTime } from './values.js'

export function bookSummariesOf(raw) {
  return (Array.isArray(raw) ? raw : [])
    .filter((book) => typeof book?.book_id === 'string' && book.book_id.length > 0)
    .map((book) => ({
      id: book.book_id,
      name: book.name ?? book.book_id,
      assetClass: book.expected_asset_class ?? 'UNKNOWN',
      ...catalogueFieldsOf(book),
      activeTrades: toNum(book.active_trades) ?? 0,
      closedTrades: toNum(book.closed_trades) ?? 0,
      reported: reportedOf(book.reported),
      isActive: book.is_active !== false,
      positions: Array.isArray(book.positions) ? book.positions : [],
    }))
}

export function booksSummaryOf(data) {
  const portfolio = data?.portfolio ?? {}
  return {
    currency: data?.currency ?? null,
    books: bookSummariesOf(data?.books),
    portfolio: {
      bookCount: toNum(portfolio.book_count) ?? 0,
      activeTrades: toNum(portfolio.active_trades) ?? 0,
      closedTrades: toNum(portfolio.closed_trades) ?? 0,
      subtotals: (Array.isArray(portfolio.subtotals) ? portfolio.subtotals : []).map((row) => ({
        currency: row.currency,
        values: amountsOf(row.values),
        fx: fxOf(row.fx),
      })),
      reported: reportedOf(portfolio.reported),
    },
  }
}

export function moveTargetsOf(books, book) {
  if (book == null) return []
  return books.filter(
    (other) => other.isActive && other.id !== book.id && other.assetClass === book.assetClass,
  )
}

function positionStatusOf(position, now) {
  const staleAtMs = toTime(position.stale_at)
  if (position.status !== 'PENDING' && Number.isFinite(staleAtMs) && now >= staleAtMs) return 'STALE'
  return position.status ?? 'PENDING'
}

export function bookPositionsOf(book, now) {
  return (book?.positions ?? []).map((position) => {
    const provider = position.market_data_provider ?? null
    return {
      id: `${position.symbol}:${position.currency ?? 'N/A'}:${provider ?? 'MODEL'}:${position.contract_key ?? ''}`,
      symbol: position.symbol,
      provider,
      currency: position.currency ?? null,
      assetClass: position.asset_class ?? 'UNKNOWN',
      ...catalogueFieldsOf(position),
      terms: position.terms && typeof position.terms === 'object' ? position.terms : null,
      netQuantity: toNum(position.net_quantity) ?? 0,
      averageEntry: toNum(position.average_entry),
      price: toNum(position.current_price),
      unrealizedPnl: toNum(position.unrealized_pnl) ?? 0,
      status: positionStatusOf(position, now),
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
  if (values.name.trim().length === 0) errors.name = 'Name is required.'
  if (!values.assetClass) errors.assetClass = 'Pick an asset class.'
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
