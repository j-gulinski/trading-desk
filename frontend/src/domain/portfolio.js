import { reportedTotalsOf } from './fx.js'

export const PORTFOLIO_METRICS = ['grossEntry', 'unrealized', 'realized', 'total']


export function portfolioSummaryOf(books) {
  const buckets = new Map()
  let openCount = 0
  let closedCount = 0

  for (const book of books) {
    openCount += book.activeTrades ?? 0
    closedCount += book.closedTrades ?? 0
    for (const row of book.subtotals ?? []) {
      const bucket = buckets.get(row.currency) ?? {
        grossEntry: 0,
        unrealized: 0,
        realized: 0,
        total: 0,
      }
      for (const metric of PORTFOLIO_METRICS) {
        bucket[metric] += Number.isFinite(row.values?.[metric])
          ? row.values[metric]
          : 0
      }
      buckets.set(row.currency, bucket)
    }
  }

  const subtotals = [...buckets.entries()]
    .map(([currency, values]) => ({ currency, values }))
    .sort((a, b) => a.currency.localeCompare(b.currency))
  const currency = subtotals.length === 1 ? subtotals[0].currency : null
  const values = subtotals.length === 1 ? subtotals[0].values : null

  return {
    bookCount: books.length,
    openCount,
    closedCount,
    currency,
    values,
    subtotals,
  }
}


export function reportedPortfolioSummaryOf(books, rates, reportingCurrency) {
  const summary = portfolioSummaryOf(books)
  return {
    ...summary,
    reported: reportedTotalsOf(
      summary,
      rates,
      reportingCurrency,
      PORTFOLIO_METRICS,
    ),
  }
}
