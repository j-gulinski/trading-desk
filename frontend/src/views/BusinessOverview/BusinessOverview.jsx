import { useMarketFeedContext, useValuationFeedContext } from '../../providers/feedContext.js'
import { useElapsedTime } from '../../hooks/useElapsedTime.js'
import { usePolling } from '../../hooks/usePolling.js'
import { apiGet } from '../../services/apiClient.js'
import { endpoints } from '../../services/endpoints.js'
import { BOOK_SUMMARY_POLL_INTERVAL_MS } from '../../config/books.js'
import { bookSummariesOf } from '../../domain/books.js'
import {
  bookRisksOf,
  summarizeValuations,
  valuationRowsOf,
} from '../../domain/valuations.js'
import { reportedTotalsOf } from '../../domain/fx.js'
import { reportedPortfolioSummaryOf } from '../../domain/portfolio.js'
import { useFxRates } from '../../hooks/useFxRates.js'
import { useReportingCurrency } from '../../hooks/useReportingCurrency.js'
import {
  directionOf,
  formatAmount,
  formatClockTime,
  formatSignedAmount,
} from '../../domain/formatting.js'
import StatCard from '../../components/cards/StatCard.jsx'
import StreamHeader from '../../components/status/StreamHeader.jsx'
import StatusPill from '../../components/status/StatusPill.jsx'
import Panel from '../../components/Panel.jsx'
import EmptyState from '../../components/EmptyState.jsx'
import LoadingSkeleton from '../../components/LoadingSkeleton.jsx'

const FX_METRICS = ['unrealized', 'realized']

function BookPnlRow({ book }) {
  const value = book.reported.values?.unrealized ?? null
  return (
    <li className="book-pnl__row" title={book.reported.title}>
      <span className="book-pnl__name">{book.name}</span>
      <span className={`book-pnl__value delta--${directionOf(value)}`}>
        {value == null ? '—' : formatSignedAmount(value)} {book.reported.currency}
      </span>
    </li>
  )
}

export default function BusinessOverview() {
  const { valuations, bookRisk, status, seedStatus } = useValuationFeedContext()
  const { instruments, curves } = useMarketFeedContext()
  const { now } = useElapsedTime()
  const booksRequest = usePolling(
    ({ signal }) => apiGet(endpoints.blotter.booksSummary, { signal }),
    { intervalMs: BOOK_SUMMARY_POLL_INTERVAL_MS },
  )

  const rows = valuationRowsOf(Object.values(valuations), now, instruments, curves)

  const summary = summarizeValuations(rows)
  const bookRoster = bookSummariesOf(booksRequest.data)
  const [reportingCurrency] = useReportingCurrency()
  const fx = useFxRates(reportingCurrency)
  const portfolio = reportedPortfolioSummaryOf(bookRoster, fx.rates, reportingCurrency)
  const actualOpen = booksRequest.data == null ? summary.open : portfolio.openCount
  const actualBooks = booksRequest.data == null ? summary.books : portfolio.bookCount
  const unvaluedOpen = Math.max(0, actualOpen - summary.open)

  function reported(subtotals, ownCurrency, values) {
    return reportedTotalsOf(
      { subtotals, currency: ownCurrency, values }, fx.rates, reportingCurrency, FX_METRICS,
    )
  }

  const books = bookRisksOf(rows, bookRisk).map((book) => ({
    ...book,
    reported: reported(book.subtotals, book.currency, book),
  }))
  const headline = portfolio.reported
  const currency = headline.currency
  const fresh = summary.live + summary.marketClosed
  const livePercent = actualOpen > 0 ? (fresh / actualOpen) * 100 : 0
  const initialLoading = seedStatus === 'loading' || status === 'CONNECTING'

  const emptyMessage =
    seedStatus === 'error'
      ? 'Could not load current valuations — retrying on reconnect.'
      : status === 'RECONNECTING'
        ? 'Valuation stream unavailable — retrying.'
        : 'No trades are being valued yet.'

  return (
    <section className="page">
      <StreamHeader
        title="PORTFOLIO POSITION"
        note={`as of ${formatClockTime(summary.lastUpdateMs)}`}
        status={status}
        stream="PRICING"
      />

      <div className="business-summary">
        <StatCard
          label={`OPEN GROSS ENTRY VALUE · ${currency}`}
          value={
            headline.values == null ? '—' : formatAmount(headline.values.grossEntry)
          }
          sub={`${actualOpen} open positions`}
          title={headline.title}
        />
        <StatCard
          label={`UNREALIZED PNL · ALL BOOKS · ${currency}`}
          value={
            headline.values == null ? '—' : formatSignedAmount(headline.values.unrealized)
          }
          sub={`${summary.open} valued of ${actualOpen} open · ${summary.books} books`}
          tone={
            headline.values == null
              ? 'default'
              : headline.values.unrealized >= 0 ? 'pos' : 'neg'
          }
          title={headline.title}
        />
        <StatCard
          label={`REALIZED PNL · ALL BOOKS · ${currency}`}
          value={headline.values == null ? '—' : formatSignedAmount(headline.values.realized)}
          sub={`${portfolio.closedCount} closed positions`}
          tone={
            headline.values == null
              ? 'default'
              : headline.values.realized >= 0 ? 'pos' : 'neg'
          }
          title={headline.title}
        />
        <StatCard
          label={`TOTAL PNL · ALL BOOKS · ${currency}`}
          value={headline.values == null ? '—' : formatSignedAmount(headline.values.total)}
          sub="realized + unrealized"
          tone={
            headline.values == null
              ? 'default'
              : headline.values.total >= 0 ? 'pos' : 'neg'
          }
          title={headline.title}
        />
        <StatCard
          label="OPEN TRADES"
          value={actualOpen}
          sub={`${summary.open} valued${unvaluedOpen > 0 ? ` · ${unvaluedOpen} unvalued` : ''}`}
          tone={unvaluedOpen > 0 ? 'warn' : 'default'}
          href="#/valuations"
        />
        <StatCard
          label="CLOSED TRADES"
          value={portfolio.closedCount}
          sub={`${actualBooks} books · ${summary.books} with a valuation`}
        />
      </div>

      <div className="business-panels">
        <Panel
          title="UNREALIZED PNL BY BOOK"
          meta={
            <a className="panel__link" href="#/valuations">
              alpha/beta in Valuations &amp; Risk →
            </a>
          }
        >
          {initialLoading ? (
            <LoadingSkeleton variant="list" label="Loading book valuations" />
          ) : books.length > 0 ? (
            <ul className="book-pnl">
              {books.map((book) => (
                <BookPnlRow key={book.id} book={book} />
              ))}
            </ul>
          ) : (
            <EmptyState message={emptyMessage} />
          )}
        </Panel>

        <Panel title="VALUATION FRESHNESS">
          {initialLoading ? (
            <LoadingSkeleton variant="panel" rows={4} label="Loading valuation freshness" />
          ) : actualOpen > 0 ? (
            <div className="freshness">
              <div className="freshness__counts">
                <span className="freshness__count">
                  <StatusPill level="info" label="LIVE" compact />
                  <strong>{summary.live}</strong>
                </span>
                {summary.marketClosed > 0 && (
                  <span className="freshness__count">
                    <StatusPill level="closed" label="MKT CLOSED" compact />
                    <strong>{summary.marketClosed}</strong>
                  </span>
                )}
                <span className="freshness__count">
                  <StatusPill level="stale" label="STALE" compact />
                  <strong>{summary.stale}</strong>
                </span>
                {unvaluedOpen > 0 && (
                  <span className="freshness__count">
                    <StatusPill level="unknown" label="UNVALUED" compact />
                    <strong>{unvaluedOpen}</strong>
                  </span>
                )}
              </div>
              <div
                className="freshness__bar"
                role="img"
                aria-label={`${fresh} of ${actualOpen} open trades have a current valuation`}
              >
                <span className="freshness__fill" style={{ transform: `scaleX(${livePercent / 100})` }} />
              </div>
              <p className="freshness__note">
                Excludes {portfolio.closedCount} closed positions.
              </p>
            </div>
          ) : (
            <EmptyState message={emptyMessage} />
          )}
        </Panel>
      </div>
    </section>
  )
}
