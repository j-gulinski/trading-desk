import { useValuationFeedContext } from '../../providers/feedContext.js'
import { useElapsedTime } from '../../hooks/useElapsedTime.js'
import { useBooksSummary } from '../../hooks/useBooksSummary.js'
import {
  bookRisksOf,
  summarizeValuations,
  valuationRowsOf,
} from '../../domain/valuations.js'
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

function toneOf(value) {
  if (value == null) return 'default'
  return value >= 0 ? 'pos' : 'neg'
}

function BookPnlRow({ book }) {
  const value = book.reported?.values.unrealized ?? null
  return (
    <li className="book-pnl__row" title={book.reported?.title}>
      <span className="book-pnl__name">{book.name}</span>
      <span className={`book-pnl__value delta--${directionOf(value)}`}>
        {formatSignedAmount(value)} {book.reported?.currency ?? ''}
      </span>
    </li>
  )
}

export default function BusinessOverview() {
  const { valuations, bookRisk, status, seedStatus } = useValuationFeedContext()
  const { now } = useElapsedTime()
  const booksSummary = useBooksSummary()

  const rows = valuationRowsOf(Object.values(valuations), now)

  const summary = summarizeValuations(rows)
  const { portfolio } = booksSummary
  const actualOpen = booksSummary.data == null ? summary.open : portfolio.activeTrades
  const actualBooks = booksSummary.data == null ? summary.books : portfolio.bookCount
  const unvaluedOpen = Math.max(0, actualOpen - summary.open)
  const reportedByBook = new Map(booksSummary.books.map((book) => [book.id, book.reported]))

  const books = bookRisksOf(rows, bookRisk)
    .map((book) => ({ ...book, reported: reportedByBook.get(book.id) ?? null }))
    .sort((left, right) => (
      Math.abs(right.reported?.values.unrealized ?? 0) -
      Math.abs(left.reported?.values.unrealized ?? 0)
    ))
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
          value={formatAmount(headline.values.grossEntry)}
          sub={`${actualOpen} open positions`}
          title={headline.title}
        />
        <StatCard
          label={`UNREALIZED PNL · ALL BOOKS · ${currency}`}
          value={formatSignedAmount(headline.values.unrealized)}
          sub={`${summary.open} valued of ${actualOpen} open · ${summary.books} books`}
          tone={toneOf(headline.values.unrealized)}
          title={headline.title}
        />
        {portfolio.closedTrades > 0 && (
          <StatCard
            label={`REALIZED PNL · ALL BOOKS · ${currency}`}
            value={formatSignedAmount(headline.values.realized)}
            sub={`${portfolio.closedTrades} closed positions`}
            tone={toneOf(headline.values.realized)}
            title={headline.title}
          />
        )}
        <StatCard
          label={`TOTAL PNL · ALL BOOKS · ${currency}`}
          value={formatSignedAmount(headline.values.total)}
          sub="realized + unrealized"
          tone={toneOf(headline.values.total)}
          title={headline.title}
        />
        <StatCard
          label="OPEN TRADES"
          value={actualOpen}
          sub={`${summary.open} valued${unvaluedOpen > 0 ? ` · ${unvaluedOpen} unvalued` : ''}`}
          tone={unvaluedOpen > 0 ? 'warn' : 'default'}
          href="#/valuations"
        />
        {portfolio.closedTrades > 0 && (
          <StatCard
            label="CLOSED TRADES"
            value={portfolio.closedTrades}
            sub={`${actualBooks} books · ${summary.books} with a valuation`}
          />
        )}
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
                Excludes {portfolio.closedTrades} closed positions.
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
