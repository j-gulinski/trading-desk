import StatusPill from '../status/StatusPill.jsx'
import { VALUATION_STATUS_LABEL, VALUATION_STATUS_LEVEL } from '../../config/valuations.js'
import { providerLabel } from '../../config/providers.js'
import {
  directionOf,
  formatNumber,
  formatShortId,
  formatSignedAmount,
  formatUnitPrice,
} from '../../domain/formatting.js'

function PnlMetric({ label, value, title }) {
  return (
    <div className="book-tile__metric" title={title}>
      <span className="book-tile__metric-label">{label}</span>
      <strong className={`book-tile__metric-value delta--${directionOf(value)}`}>
        {value == null ? '—' : formatSignedAmount(value)}
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
            <span className="book-position__symbol">
              {position.symbol}
              {position.provider != null && ` · ${providerLabel(position.provider)}`}
            </span>
            <StatusPill
              level={VALUATION_STATUS_LEVEL[position.status]}
              label={VALUATION_STATUS_LABEL[position.status] ?? position.status}
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
              value={`${formatUnitPrice(position.averageEntry, position.assetClass)} ${position.currency ?? '—'}`}
            />
            <PositionStat
              label="MARK"
              value={`${formatUnitPrice(position.price, position.assetClass)} ${position.currency ?? '—'}`}
            />
            <PositionStat
              label="UNREALIZED"
              value={`${formatSignedAmount(position.unrealizedPnl)} ${position.currency ?? '—'}`}
              tone={directionOf(position.unrealizedPnl)}
            />
          </div>
        </li>
      ))}
    </ul>
  )
}

export default function BookCard({
  book,
  reported,
  expanded,
  positions,
  onToggleExpand,
  onEdit,
  onMove,
  onDelete,
}) {
  return (
    <article
      className={`book-tile${expanded ? ' book-tile--expanded' : ''}${
        book.isActive ? '' : ' book-tile--inactive'
      }`}
    >
      <header className="book-tile__head">
        <div>
          <h3 className="book-tile__name">{book.name}</h3>
          <span className="book-tile__code">{formatShortId(book.id)}</span>
        </div>
        <span className="book-tile__class">
          <span className="book-tile__badge-dot" />
          {book.assetClass}
        </span>
      </header>

      <div className="book-tile__pnl">
        <PnlMetric
          label={`Unrealized · ${reported.currency}`}
          value={reported.values?.unrealized ?? null}
          title={reported.title}
        />
        <PnlMetric
          label={`Realized · ${reported.currency}`}
          value={reported.values?.realized ?? null}
          title={reported.title}
        />
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
        {book.isActive ? (
          <div className="book-tile__actions">
            <button
              type="button"
              className="book-tile__action"
              data-panel-trigger
              onClick={onEdit}
            >
              Edit
            </button>
            {book.activeTrades > 0 && (
              <button
                type="button"
                className="book-tile__action"
                data-panel-trigger
                onClick={onMove}
              >
                Move
              </button>
            )}
            <button
              type="button"
              className="book-tile__action book-tile__action--danger"
              data-panel-trigger
              onClick={onDelete}
            >
              Delete
            </button>
          </div>
        ) : (
          <StatusPill level="stale" label="DEACTIVATED" compact />
        )}
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
