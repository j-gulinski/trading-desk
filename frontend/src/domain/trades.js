import { VALUATION_STALE_AFTER_MS } from '../config/valuations.js'
import { groupOptions } from './filters.js'
import { formatShortId } from './formatting.js'
import { sortRows } from './tableSort.js'
import { statusOf as liveValuationStatusOf } from './valuations.js'

const VALUATION_STATUS_RANK = {
  LIVE: 4,
  STALE: 3,
  PENDING: 2,
  CLOSED: 1,
  CANCELLED: 0,
}

function toNum(value) {
  if (value == null || value === '') return null
  const n = Number(value)
  return Number.isFinite(n) ? n : null
}

function toTime(value) {
  const parsed = Date.parse(value ?? '')
  return Number.isFinite(parsed) ? parsed : null
}

export function booksFromSummary(data) {
  if (!Array.isArray(data)) return []
  return data
    .filter((book) => typeof book?.book_id === 'string')
    .map((book) => ({
      id: book.book_id,
      name: book.name ?? formatShortId(book.book_id),
      closedTrades: toNum(book.closed_trades) ?? 0,
    }))
}

export function bookNamesOf(books) {
  return new Map(books.map((book) => [book.id, book.name]))
}

export function closedTradeCountOf(books) {
  return books.reduce((total, book) => total + book.closedTrades, 0)
}

function snapshotValuationOf(data, trade) {
  if (!data || typeof data !== 'object') return null

  return {
    id: trade.id,
    fairValue: toNum(data.fair_value),
    unrealizedPnl: toNum(data.unrealized_pnl),
    realizedPnl: toNum(data.realized_pnl),
    currency: data.currency ?? trade.currency,
    valuationTimeMs: toTime(data.valuation_time),
    receivedAtMs: null,
    closed: trade.status !== 'ACTIVE',
  }
}

export function tradeOf(data, bookNames = new Map()) {
  if (!data || typeof data.trade_id !== 'string' || data.trade_id.length === 0) return null

  const status = String(data.status ?? 'UNKNOWN').toUpperCase()
  const side = String(data.side ?? 'UNKNOWN').toUpperCase()
  const quantity = toNum(data.quantity)
  const trade = {
    latestValuation: null,
    id: data.trade_id,
    tradeRef: formatShortId(data.trade_id),
    bookId: data.book_id ?? null,
    bookName: bookNames.get(data.book_id) ?? formatShortId(data.book_id),
    assetClass: data.asset_class ?? 'UNKNOWN',
    symbol: data.symbol ?? null,
    side,
    quantity: Number.isFinite(quantity) ? Math.abs(quantity) : null,
    entryPrice: toNum(data.trade_price),
    currency: data.currency ?? null,
    status,
    openedAtMs: toTime(data.opened_at),
    closedAtMs: toTime(data.closed_at),
    closePrice: toNum(data.close_price),
    closeReason: data.close_reason ?? null,
  }

  trade.latestValuation = snapshotValuationOf(data.latest_valuation, trade)
  return trade
}

export function tradesFromSnapshot(data, bookNames) {
  if (!Array.isArray(data)) return []
  const trades = new Map()
  for (const dataTrade of data) {
    const trade = tradeOf(dataTrade, bookNames)
    if (!trade) continue
    const current = trades.get(trade.id)
    if (!current || (current.status === 'ACTIVE' && trade.status !== 'ACTIVE')) {
      trades.set(trade.id, trade)
    }
  }
  return Array.from(trades.values())
}

function latestValuationOf(trade, liveValuation) {
  const snapshot = trade.latestValuation
  if (!snapshot) return { valuation: liveValuation ?? null, source: liveValuation ? 'feed' : null }
  if (!liveValuation) return { valuation: snapshot, source: 'blotter' }

  if (snapshot.closed && !liveValuation.closed) {
    return { valuation: snapshot, source: 'blotter' }
  }
  if (liveValuation.closed && !snapshot.closed) {
    return { valuation: liveValuation, source: 'feed' }
  }

  const snapshotTime = snapshot.valuationTimeMs
  const liveTime = liveValuation.valuationTimeMs
  if (!Number.isFinite(snapshotTime) || (Number.isFinite(liveTime) && liveTime >= snapshotTime)) {
    return { valuation: liveValuation, source: 'feed' }
  }
  return { valuation: snapshot, source: 'blotter' }
}

function lifecycleOf(trade, valuation) {
  return trade.status === 'ACTIVE' && !valuation?.closed ? 'OPEN' : 'CLOSED'
}

function valuationStatusOf(trade, valuation, source, now) {
  if (trade.status === 'CANCELLED') return 'CANCELLED'
  if (trade.status !== 'ACTIVE' || valuation?.closed) return 'CLOSED'
  if (!valuation) return 'PENDING'
  if (source === 'feed') return liveValuationStatusOf(valuation, now)
  if (!Number.isFinite(valuation.valuationTimeMs)) return 'STALE'
  return now - valuation.valuationTimeMs > VALUATION_STALE_AFTER_MS ? 'STALE' : 'LIVE'
}

export function tradeRowsOf(trades, liveValuations, now) {
  return trades.map((trade) => {
    const { valuation, source } = latestValuationOf(trade, liveValuations[trade.id])
    const lifecycle = lifecycleOf(trade, valuation)
    const valuationStatus = valuationStatusOf(trade, valuation, source, now)
    return {
      trade,
      valuation,
      valuationSource: source,
      valuationStatus,
      lifecycle,
      pnl: lifecycle === 'CLOSED' ? valuation?.realizedPnl ?? null : valuation?.unrealizedPnl ?? null,
    }
  })
}

export function summarizeTradeRows(rows) {
  const summary = { open: 0, closed: 0 }

  for (const row of rows) {
    if (row.lifecycle === 'OPEN') summary.open += 1
    else summary.closed += 1
  }
  return summary
}

export function tradeBookOptionsOf(rows) {
  return groupOptions(
    rows,
    (row) => row.trade.bookId,
    (row) => row.trade.bookName,
  )
}

const SEARCHED_FIELDS = ['tradeRef', 'id', 'bookName', 'symbol', 'assetClass']

export function matchesTradeFilters(row, { book, assetClass, search }) {
  const { trade } = row
  if (book && trade.bookId !== book) return false
  if (assetClass && trade.assetClass !== assetClass) return false
  if (!search) return true
  return SEARCHED_FIELDS.some((field) => trade[field]?.toLowerCase().includes(search))
}

function structuralValueOf(row, column) {
  const { trade } = row
  if (column === 'trade') return trade.tradeRef
  if (column === 'book') return trade.bookName
  if (column === 'assetClass') return trade.assetClass
  if (column === 'symbol') return trade.symbol
  if (column === 'side') return trade.side
  if (column === 'quantity') return trade.quantity
  if (column === 'entry') return trade.entryPrice
  if (column === 'opened') return trade.openedAtMs
  return undefined
}

function snapshotValueOf(row, column) {
  if (column === 'price') return row.valuation?.price ?? null
  if (column === 'fairValue') return row.valuation?.fairValue ?? null
  if (column === 'pnl') return row.pnl
  if (column === 'return') return row.valuation?.closed ? null : row.valuation?.returnPercent ?? null
  if (column === 'updated') return row.valuation?.valuationTimeMs ?? null
  if (column === 'valuation') return VALUATION_STATUS_RANK[row.valuationStatus] ?? null
  return null
}

export function captureTradeSnapshot(rows, column) {
  const values = {}
  for (const row of rows) values[row.trade.id] = snapshotValueOf(row, column)
  return values
}

export function sortTradeRows(rows, sort) {
  return sortRows(rows, sort, {
    valueOf: (row) => {
      const structural = structuralValueOf(row, sort.column)
      return structural === undefined ? (sort.snapshot?.[row.trade.id] ?? null) : structural
    },
    tieBreak: (a, b) => a.trade.tradeRef.localeCompare(b.trade.tradeRef),
  })
}

export function valuationHistoryOf(data) {
  if (!Array.isArray(data)) return []
  return data.map((valuation, index) => ({
    id: `${valuation.valuation_time ?? 'unknown'}:${index}`,
    valuationTimeMs: toTime(valuation.valuation_time),
    fairValue: toNum(valuation.fair_value),
    unrealizedPnl: toNum(valuation.unrealized_pnl),
    realizedPnl: toNum(valuation.realized_pnl),
    totalPnl: toNum(valuation.total_pnl),
    currency: valuation.currency ?? null,
  }))
}

export function tradeDetailOf(data, bookNames) {
  if (!data || typeof data !== 'object') return null
  const trade = tradeOf(
    {
      ...data.trade,
      latest_valuation: data.latest_valuation,
    },
    bookNames,
  )
  if (!trade) return null
  return {
    trade,
    valuationHistory: valuationHistoryOf(data.valuation_history),
  }
}
