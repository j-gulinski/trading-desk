import { VALUATION_STALE_AFTER_MS } from '../config/valuations.js'
import { groupOptions } from './filters.js'
import { formatShortId } from './formatting.js'
import { sortRows } from './tableSort.js'

const STATUS_RANK = { LIVE: 2, STALE: 1, CLOSED: 0 }

function toNum(value) {
  if (value == null || value === '') return null
  const n = Number(value)
  return Number.isFinite(n) ? n : null
}

export function valuationOf(data) {
  if (!data || typeof data.trade_id !== 'string' || data.trade_id.length === 0) return null
  const payload = data.valuation_payload ?? {}
  const valuationTime = Date.parse(data.valuation_time ?? '')

  const signedQuantity = toNum(data.quantity)
  const entryPrice = toNum(data.trade_price)
  const multiplier = toNum(payload.multiplier) ?? 1
  const unrealizedPnl = toNum(data.unrealized_pnl)
  const notional =
    Number.isFinite(signedQuantity) && Number.isFinite(entryPrice)
      ? Math.abs(signedQuantity) * entryPrice * multiplier
      : null

  return {
    id: data.trade_id,
    tradeRef: formatShortId(data.trade_id),
    bookId: data.book_id ?? null,
    bookName: data.book_name ?? null,
    assetClass: data.asset_class ?? 'UNKNOWN',
    symbol: data.symbol ?? null,
    currency: data.currency ?? null,
    signedQuantity,
    entryPrice,
    notional,
    fairValue: toNum(data.fair_value),
    unrealizedPnl,
    realizedPnl: toNum(data.realized_pnl),
    returnPercent:
      Number.isFinite(unrealizedPnl) && Number.isFinite(notional) && notional !== 0
        ? (unrealizedPnl / notional) * 100
        : null,
    price: toNum(payload.current_price ?? payload.close_price),
    closed: payload.final === true,
    valuationTimeMs: Number.isFinite(valuationTime) ? valuationTime : null,
  }
}

export function valuationsFromSeed(seed) {
  const receivedAtMs = Date.now()
  return (Array.isArray(seed) ? seed : [])
    .map(valuationOf)
    .filter(Boolean)
    .map((valuation) => ({ ...valuation, receivedAtMs }))
}

export function mergeValuation(previous, update) {
  if (previous?.closed) return previous
  if (update.closed) return update

  const previousTime = previous?.valuationTimeMs
  const nextTime = update.valuationTimeMs
  if (Number.isFinite(previousTime) && Number.isFinite(nextTime) && nextTime <= previousTime) {
    return previous
  }
  return update
}

export function mergeValuations(previous, updates) {
  let valuations = previous
  let accepted = false

  for (const update of updates) {
    const current = valuations[update.id]
    const merged = mergeValuation(current, update)
    if (merged === current) continue
    if (valuations === previous) valuations = { ...valuations }
    valuations[update.id] = merged
    accepted = true
  }

  return accepted ? valuations : previous
}

export function statusOf(valuation, now) {
  if (valuation.closed) return 'CLOSED'
  if (valuation.receivedAtMs == null) return 'STALE'
  return now - valuation.receivedAtMs > VALUATION_STALE_AFTER_MS ? 'STALE' : 'LIVE'
}

export function valuationRowsOf(valuations, now) {
  return valuations.map((valuation) => ({ valuation, status: statusOf(valuation, now) }))
}

function singleCurrencyOf(rows) {
  let currency = null
  for (const row of rows) {
    const rowCurrency = row.valuation.currency
    if (rowCurrency == null) continue
    if (currency == null) currency = rowCurrency
    else if (currency !== rowCurrency) return null
  }
  return currency
}

export function positionsOf(rows) {
  const positions = new Map()

  for (const row of rows) {
    const { valuation } = row
    if (valuation.closed) continue

    const key = `${valuation.bookId}::${valuation.symbol}`
    let position = positions.get(key)
    if (!position) {
      position = {
        id: key,
        bookName: valuation.bookName ?? formatShortId(valuation.bookId),
        symbol: valuation.symbol,
        assetClass: valuation.assetClass,
        currency: valuation.currency,
        trades: 0,
        netQuantity: 0,
        grossQuantity: 0,
        entryCost: 0,
        marketValue: 0,
        unrealizedPnl: 0,
        notional: 0,
        price: null,
        live: 0,
        stale: 0,
        lastUpdateMs: null,
      }
      positions.set(key, position)
    }

    const quantity = valuation.signedQuantity
    position.trades += 1
    if (Number.isFinite(quantity)) {
      position.netQuantity += quantity
      position.grossQuantity += Math.abs(quantity)
      if (Number.isFinite(valuation.entryPrice)) {
        position.entryCost += Math.abs(quantity) * valuation.entryPrice
      }
    }
    position.marketValue += (quantity < 0 ? -1 : 1) * (valuation.fairValue ?? 0)
    position.unrealizedPnl += valuation.unrealizedPnl ?? 0
    position.notional += valuation.notional ?? 0
    if (row.status === 'LIVE') position.live += 1
    else position.stale += 1

    const seenAt = valuation.receivedAtMs
    if (seenAt != null && (position.lastUpdateMs == null || seenAt >= position.lastUpdateMs)) {
      position.lastUpdateMs = seenAt
      position.price = valuation.price
    }
  }

  return Array.from(positions.values())
    .map((position) => ({
      ...position,
      averageEntry: position.grossQuantity > 0 ? position.entryCost / position.grossQuantity : null,
      returnPercent:
        position.notional > 0 ? (position.unrealizedPnl / position.notional) * 100 : null,
      status: position.stale > 0 ? 'STALE' : 'LIVE',
    }))
    .sort((a, b) => a.bookName.localeCompare(b.bookName) || a.symbol.localeCompare(b.symbol))
}

function accumulate(target, row) {
  const { valuation } = row
  if (valuation.closed) target.closed += 1
  else {
    target.open += 1
    target.unrealized += valuation.unrealizedPnl ?? 0
  }
  target.realized += valuation.realizedPnl ?? 0
  if (row.status === 'LIVE') target.live += 1
  else if (row.status === 'STALE') target.stale += 1
}

export function summarizeValuations(rows) {
  const summary = {
    total: rows.length,
    open: 0,
    closed: 0,
    live: 0,
    stale: 0,
    unrealized: 0,
    realized: 0,
    books: new Set(),
    currency: singleCurrencyOf(rows),
    lastUpdateMs: null,
  }

  for (const row of rows) {
    accumulate(summary, row)
    const { valuation } = row
    if (valuation.bookId != null) summary.books.add(valuation.bookId)
    const seenAt = valuation.receivedAtMs
    if (seenAt != null && (summary.lastUpdateMs == null || seenAt > summary.lastUpdateMs)) {
      summary.lastUpdateMs = seenAt
    }
  }

  return { ...summary, books: summary.books.size }
}

export function bookRisksOf(rows) {
  const books = new Map()

  for (const row of rows) {
    const { valuation } = row
    const id = valuation.bookId ?? valuation.bookName
    if (id == null) continue

    let book = books.get(id)
    if (!book) {
      book = {
        id,
        name: valuation.bookName ?? formatShortId(valuation.bookId),
        assetClass: valuation.assetClass,
        currency: valuation.currency,
        trades: 0,
        open: 0,
        closed: 0,
        live: 0,
        stale: 0,
        unrealized: 0,
        realized: 0,
        alpha: null,
        beta: null,
      }
      books.set(id, book)
    }

    book.trades += 1
    if (book.assetClass !== valuation.assetClass) book.assetClass = 'MIXED'
    if (book.currency !== valuation.currency) book.currency = null
    accumulate(book, row)
  }

  return Array.from(books.values()).sort((a, b) => a.name.localeCompare(b.name))
}

export function bookOptionsOf(rows) {
  return groupOptions(
    rows,
    (row) => row.valuation.bookId,
    (row) => row.valuation.bookName ?? formatShortId(row.valuation.bookId),
  )
}

function structuralValueOf(valuation, column) {
  if (column === 'trade') return valuation.tradeRef
  if (column === 'book') return valuation.bookName ?? valuation.bookId
  if (column === 'assetClass') return valuation.assetClass
  if (column === 'symbol') return valuation.symbol
  return undefined
}

function snapshotValueOf(row, column) {
  const { valuation } = row
  if (column === 'price') return valuation.price
  if (column === 'fairValue') return valuation.fairValue
  if (column === 'return') return valuation.closed ? null : valuation.returnPercent
  if (column === 'unrealized') return valuation.closed ? null : valuation.unrealizedPnl
  if (column === 'realized') return valuation.realizedPnl
  if (column === 'updated') return valuation.valuationTimeMs
  if (column === 'valuation') return STATUS_RANK[row.status] ?? null
  return null
}

export function captureValuationSnapshot(rows, column) {
  const values = {}
  for (const row of rows) {
    values[row.valuation.id] = snapshotValueOf(row, column)
  }
  return values
}

export function sortValuationRows(rows, sort) {
  return sortRows(rows, sort, {
    valueOf: (row) => {
      const structural = structuralValueOf(row.valuation, sort.column)
      return structural === undefined ? (sort.snapshot?.[row.valuation.id] ?? null) : structural
    },
    tieBreak: (a, b) => a.valuation.tradeRef.localeCompare(b.valuation.tradeRef),
  })
}
