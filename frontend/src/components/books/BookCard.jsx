import StatusPill from '../status/StatusPill.jsx'
import {
  directionOf,
  formatNumber,
  formatShortId,
  formatSignedAmount,
  formatUnitPrice,
} from '../../domain/formatting.js'

function PnlMetric({ label, value }) {
  return (
    <div className="book-tile__metric">
      <span className="book-tile__metric-label">{label}</span>
      <strong className={`book-tile__metric-value delta--${directionOf(value)}`}>
        {formatSignedAmount(value)}
      </strong>
    </div>
  )
}

function PositionStat({ label, value, tone = null }) {
  return (
    <div className="book-position__stat">
      <span className="book-position__stat-label">{label}</span>
      <span className={`book-position__stat-value${tone ? ` delta--${tone}` : ''}`}>
        {value}
      </span>
    </div>
  )
}

function PositionList({ positions }) {
  return (
    <ul className="book-positions">
      {positions.map((position) => (
        <li key={position.id} className="book-position">
          <div className="book-position__head">
            <span className="book-position__symbol">{position.symbol}</span>
            <StatusPill
              level={position.status === 'LIVE' ? 'info' : 'stale'}
              label={position.status}
              compact
            />
          </div>
          <div className="book-position__stats">
            <PositionStat
              label="NET QTY"
              value={formatSignedAmount(position.netQuantity, 0)}
            />
            <PositionStat
              label="AVG ENTRY"
              value={formatUnitPrice(position.averageEntry, position.assetClass)}
            />
            <PositionStat
              label="MARK"
              value={formatUnitPrice(position.price, position.assetClass)}
            />
            <PositionStat
              label="UNREALIZED"
              value={formatSignedAmount(position.unrealizedPnl)}
              tone={directionOf(position.unrealizedPnl)}
            />
          </div>
        </li>
      ))}
    </ul>
  )
}

export default function BookCard({ book, expanded, positions, onToggleExpand, onEdit }) {
  return (
    <article className={`book-tile${expanded ? ' book-tile--expanded' : ''}`}>
      <header className="book-tile__head">
        <div>
          <h3 className="book-tile__name">{book.name}</h3>
          <span className="book-tile__code">{formatShortId(book.id)}</span>
        </div>
        <span className="book-tile__badge">
          <span className="book-tile__badge-dot" />
          {book.assetClass}
        </span>
      </header>

      <div className="book-tile__pnl">
        <PnlMetric label={`UNREALIZED · ${book.currency ?? 'USD'}`} value={book.unrealizedPnl} />
        <PnlMetric label="REALIZED" value={book.realizedPnl} />
      </div>

      <footer className="book-tile__foot">
        <button
          type="button"
          className="book-tile__positions-toggle"
          aria-expanded={expanded}
          onClick={onToggleExpand}
        >
          {formatNumber(book.activeTrades)} open · {formatNumber(book.closedTrades)} closed{' '}
          {expanded ? '↑' : '→'}
        </button>
        <button type="button" className="book-tile__edit" onClick={onEdit}>
          Edit
        </button>
      </footer>

      {expanded && (
        <div className="book-tile__positions">
          {positions.length > 0 ? (
            <PositionList positions={positions} />
          ) : (
            <p className="book-tile__positions-note">
              No open position in this book is being valued right now.
            </p>
          )}
        </div>
      )}
    </article>
  )
}
