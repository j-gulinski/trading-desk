import { useValuationFeedContext } from '../../providers/feedContext.js'
import { useElapsedTime } from '../../hooks/useElapsedTime.js'
import {
  bookRisksOf,
  summarizeValuations,
  valuationRowsOf,
} from '../../domain/valuations.js'
import { directionOf, formatClockTime, formatSignedAmount } from '../../domain/formatting.js'
import StatCard from '../../components/cards/StatCard.jsx'
import StreamHeader from '../../components/status/StreamHeader.jsx'
import StatusPill from '../../components/status/StatusPill.jsx'
import Panel from '../../components/Panel.jsx'
import EmptyState from '../../components/EmptyState.jsx'

function BookPnlRow({ book }) {
  return (
    <li className="book-pnl__row">
      <span className="book-pnl__name">{book.name}</span>
      <span className={`book-pnl__value delta--${directionOf(book.unrealized)}`}>
        {formatSignedAmount(book.unrealized)}
      </span>
    </li>
  )
}

export default function BusinessOverview() {
  const { valuations, status, seedStatus } = useValuationFeedContext()
  const { now } = useElapsedTime()

  const rows = valuationRowsOf(Object.values(valuations), now)

  const summary = summarizeValuations(rows)
  const books = bookRisksOf(rows)
  const currency = summary.currency ?? 'MIXED'
  const valued = summary.live + summary.stale
  const livePercent = valued > 0 ? (summary.live / valued) * 100 : 0

  const emptyMessage =
    seedStatus === 'error'
      ? 'Could not load current valuations — retrying on reconnect.'
      : seedStatus === 'loading' || status === 'CONNECTING'
        ? 'Connecting to the valuation stream…'
        : status === 'RECONNECTING'
          ? 'Valuation stream unavailable — retrying.'
          : 'No trades are being valued yet.'

  return (
    <section className="page">
      <StreamHeader
        title="PORTFOLIO POSITION"
        note={`as of ${formatClockTime(summary.lastUpdateMs)}`}
        status={status}
      />

      <div className="business-summary">
        <StatCard
          label={`UNREALIZED PNL · ALL BOOKS · ${currency}`}
          value={formatSignedAmount(summary.unrealized)}
          sub={`${summary.open} open positions · ${summary.books} books`}
          tone={summary.unrealized >= 0 ? 'pos' : 'neg'}
        />
        <StatCard
          label={`REALIZED PNL · ALL BOOKS · ${currency}`}
          value={formatSignedAmount(summary.realized)}
          sub={`${summary.closed} closed positions`}
          tone={summary.realized >= 0 ? 'pos' : 'neg'}
        />
        <StatCard
          label="OPEN TRADES"
          value={summary.open}
          sub="Valuations & Risk →"
          href="#/valuations"
        />
        <StatCard label="BOOKS" value={summary.books} sub="with a valuation" />
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
          {books.length > 0 ? (
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
          {valued > 0 ? (
            <div className="freshness">
              <div className="freshness__counts">
                <span className="freshness__count">
                  <StatusPill level="info" label="LIVE" compact />
                  <strong>{summary.live}</strong>
                </span>
                <span className="freshness__count">
                  <StatusPill level="stale" label="STALE" compact />
                  <strong>{summary.stale}</strong>
                </span>
              </div>
              <div
                className="freshness__bar"
                role="img"
                aria-label={`${summary.live} of ${valued} open valuations are live`}
              >
                <span className="freshness__fill" style={{ width: `${livePercent}%` }} />
              </div>
              <p className="freshness__note">
                {summary.closed} closed valuations are final and excluded from freshness.
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
