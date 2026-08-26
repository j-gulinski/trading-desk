import { VALUATION_STALE_AFTER_MS } from '../config/valuations.js'
import { groupOptions } from './filters.js'
import { formatShortId } from './formatting.js'
import { freshnessOf } from './marketData.js'
import { sortRows } from './tableSort.js'
import { toNum, toTime } from './values.js'

const STATUS_RANK = { LIVE: 3, MARKET_CLOSED: 2, STALE: 1, CLOSED: 0 }

const DEFAULT_QUOTE_PROVIDER = 'FINNHUB'

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
    marketDataProvider: data.market_data_provider ?? null,
    marketDataTimestampMs: toTime(data.market_data_timestamp),
    discountCurve: payload.discount_curve ?? null,
    curveAsOf: payload.curve_as_of ?? null,
    curveReceivedAtMs: toTime(payload.curve_received_at),
    projectionCurve: payload.projection_curve ?? null,
    projectionCurveAsOf: payload.projection_curve_as_of ?? null,
    projectionCurveReceivedAtMs: toTime(payload.projection_curve_received_at),
    underlyingSymbol: payload.underlying_symbol ?? null,
    valuationTimeMs: Number.isFinite(valuationTime) ? valuationTime : null,
  }
}

export function bookRiskOf(data) {
  if (!data || typeof data.book_id !== 'string') return null
  return {
    id: data.book_id,
    bookName: data.book_name ?? null,
    benchmark: data.benchmark ?? null,
    benchmarkProvider: data.benchmark_provider ?? null,
    benchmarkLevel: toNum(data.benchmark_level),
    benchmarkWindowReturn: toNum(data.benchmark_window_return),
    alpha: toNum(data.alpha),
    alphaWindowReturn: toNum(data.alpha_window_return),
    alphaWindowPnl: toNum(data.alpha_window_pnl),
    bookWindowReturn: toNum(data.book_window_return),
    bookWindowPnl: toNum(data.book_window_pnl),
    beta: toNum(data.beta),
    dollarBeta: toNum(data.dollar_beta),
    rSquared: toNum(data.r_squared),
    capitalBase: toNum(data.capital_base),
    observations: toNum(data.observations) ?? 0,
    minimumObservations: toNum(data.minimum_observations) ?? 20,
    window: toNum(data.window) ?? 100,
    status: data.status ?? 'INSUFFICIENT_DATA',
    calculatedAtMs: toTime(data.calculated_at),
  }
}

export function benchmarkOf(riskMetrics) {
  let chosen = riskMetrics?.PORTFOLIO ?? null
  if (chosen == null) {
    for (const metric of Object.values(riskMetrics)) {
      if (
        chosen == null ||
        (Number.isFinite(metric.calculatedAtMs) &&
          (!Number.isFinite(chosen.calculatedAtMs) || metric.calculatedAtMs > chosen.calculatedAtMs))
      ) {
        chosen = metric
      }
    }
  }
  if (!chosen) return null
  return {
    symbol: chosen.benchmark,
    provider: chosen.benchmarkProvider ?? DEFAULT_QUOTE_PROVIDER,
    level: chosen.benchmarkLevel,
    windowReturn: chosen.benchmarkWindowReturn,
    observations: chosen.observations,
    window: chosen.window,
  }
}

export function benchmarkDayChangeOf(instruments, benchmark) {
  if (benchmark?.symbol == null) return null
  const provider = benchmark.provider ?? DEFAULT_QUOTE_PROVIDER
  const instrument = instruments?.[`${provider}:${benchmark.symbol}`]
  const previousClose = toNum(instrument?.previousClose)
  const value = toNum(instrument?.value)
  if (previousClose == null || previousClose === 0 || value == null) return null
  return ((value - previousClose) / previousClose) * 100
}

export function bookRisksFromSeed(seed) {
  return (Array.isArray(seed) ? seed : []).map(bookRiskOf).filter(Boolean)
}

export function mergeBookRisks(previous, updates) {
  let result = previous
  for (const update of updates) {
    const current = result[update.id]
    if (
      current &&
      Number.isFinite(current.calculatedAtMs) &&
      Number.isFinite(update.calculatedAtMs) &&
      update.calculatedAtMs <= current.calculatedAtMs
    ) {
      continue
    }
    if (result === previous) result = { ...result }
    result[update.id] = update
  }
  return result
}

export function valuationsFromSeed(seed) {
  const receivedAtMs = Date.now()
  return (Array.isArray(seed) ? seed : [])
    .map(valuationOf)
    .filter(Boolean)
    .map((valuation) => ({ ...valuation, receivedAtMs }))
}

function mergeValuation(previous, update) {
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

function feedInstrumentOf(valuation, instruments) {
  const symbol = valuation.underlyingSymbol ?? valuation.symbol
  if (symbol == null) return null
  const provider = valuation.marketDataProvider ?? DEFAULT_QUOTE_PROVIDER
  return instruments?.[`${provider}:${symbol}`] ?? null
}

function keepsUpWith(valuation, instrument, now) {
  const window = Number.isFinite(instrument.staleAfterMs)
    ? instrument.staleAfterMs
    : VALUATION_STALE_AFTER_MS
  if (
    Number.isFinite(valuation.marketDataTimestampMs) &&
    Number.isFinite(instrument.providerTimestampMs)
  ) {
    return valuation.marketDataTimestampMs >= instrument.providerTimestampMs - window
  }
  return valuation.receivedAtMs != null && now - valuation.receivedAtMs <= window
}

export function statusOf(valuation, now, instruments = null, curves = null) {
  if (valuation.closed) return 'CLOSED'

  if (valuation.discountCurve != null) {
    const discount = curves?.[valuation.discountCurve]
    if (
      discount?.asOfDate == null ||
      valuation.curveAsOf !== discount.asOfDate ||
      (Number.isFinite(discount.receivedAtMs) &&
        (!Number.isFinite(valuation.curveReceivedAtMs) ||
          valuation.curveReceivedAtMs < discount.receivedAtMs))
    ) {
      return 'STALE'
    }
  }
  if (valuation.projectionCurve != null) {
    const projection = curves?.[valuation.projectionCurve]
    if (
      projection?.asOfDate == null ||
      valuation.projectionCurveAsOf !== projection.asOfDate ||
      (Number.isFinite(projection.receivedAtMs) &&
        (!Number.isFinite(valuation.projectionCurveReceivedAtMs) ||
          valuation.projectionCurveReceivedAtMs < projection.receivedAtMs))
    ) {
      return 'STALE'
    }
  }

  if (valuation.discountCurve != null && valuation.underlyingSymbol == null) return 'LIVE'
  const instrument = feedInstrumentOf(valuation, instruments)
  if (instrument == null) {
    if (valuation.receivedAtMs == null) return 'STALE'
    return now - valuation.receivedAtMs > VALUATION_STALE_AFTER_MS ? 'STALE' : 'LIVE'
  }
  const feedState = freshnessOf(instrument, now)
  if (feedState === 'CLOSED') return 'MARKET_CLOSED'
  if (feedState !== 'LIVE') return 'STALE'
  return keepsUpWith(valuation, instrument, now) ? 'LIVE' : 'STALE'
}

export function valuationRowsOf(valuations, now, instruments = null, curves = null) {
  return valuations.map((valuation) => ({
    valuation,
    status: statusOf(valuation, now, instruments, curves),
  }))
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

function accumulate(target, row) {
  const { valuation } = row
  if (valuation.closed) target.closed += 1
  else {
    target.open += 1
    target.notional += valuation.notional ?? 0
    target.unrealized += valuation.unrealizedPnl ?? 0
  }
  target.realized += valuation.realizedPnl ?? 0
  if (row.status === 'LIVE') target.live += 1
  else if (row.status === 'MARKET_CLOSED') target.marketClosed += 1
  else if (row.status === 'STALE') target.stale += 1
}

export function summarizeValuations(rows) {
  const summary = {
    total: rows.length,
    open: 0,
    closed: 0,
    live: 0,
    marketClosed: 0,
    stale: 0,
    notional: 0,
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

export function bookRisksOf(rows, riskMetrics = {}) {
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
        marketClosed: 0,
        stale: 0,
        notional: 0,
        unrealized: 0,
        realized: 0,
        byCurrency: new Map(),
        alpha: null,
        beta: null,
      }
      books.set(id, book)
    }

    book.trades += 1
    if (book.assetClass !== valuation.assetClass) book.assetClass = 'MIXED'
    if (book.currency !== valuation.currency) book.currency = null
    if (valuation.currency != null) {
      const bucket = book.byCurrency.get(valuation.currency)
        ?? { notional: 0, unrealized: 0, realized: 0 }
      if (!valuation.closed) {
        bucket.notional += valuation.notional ?? 0
        bucket.unrealized += valuation.unrealizedPnl ?? 0
      }
      bucket.realized += valuation.realizedPnl ?? 0
      book.byCurrency.set(valuation.currency, bucket)
    }
    accumulate(book, row)
  }

  for (const [id, book] of books) {
    const metric = riskMetrics[id]
    if (!metric) continue
    book.alpha = metric.alpha
    book.alphaWindowReturn = metric.alphaWindowReturn
    book.alphaWindowPnl = metric.alphaWindowPnl
    book.bookWindowReturn = metric.bookWindowReturn
    book.bookWindowPnl = metric.bookWindowPnl
    book.benchmarkWindowReturn = metric.benchmarkWindowReturn
    book.beta = metric.beta
    book.dollarBeta = metric.dollarBeta
    book.rSquared = metric.rSquared
    book.capitalBase = metric.capitalBase
    book.riskStatus = metric.status
    book.riskObservations = metric.observations
    book.riskMinimumObservations = metric.minimumObservations
    book.riskWindow = metric.window
    book.benchmark = metric.benchmark
  }

  return Array.from(books.values())
    .map(({ byCurrency, ...book }) => ({
      ...book,
      subtotals: [...byCurrency.entries()]
        .map(([currency, values]) => ({ currency, values }))
        .sort((a, b) => a.currency.localeCompare(b.currency)),
    }))
    .sort((a, b) => a.name.localeCompare(b.name))
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
  if (column === 'provider') return valuation.marketDataProvider
  return undefined
}

function snapshotValueOf(row, column) {
  const { valuation } = row
  if (column === 'price') return valuation.price
  if (column === 'fairValue') return valuation.fairValue
  if (column === 'notional') return valuation.notional
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
