import StatusPill from '../status/StatusPill.jsx'
import { VALUATION_STATUS_LABEL, VALUATION_STATUS_LEVEL } from '../../config/valuations.js'
import { providerLabel } from '../../config/providers.js'
import {
  directionOf,
  formatAmount,
  formatNumber,
  formatShortId,
  formatSignedAmount,
  formatUnitPrice,
} from '../../domain/formatting.js'
import {
  priceUnitLabelOf,
  quantityUnitLabelOf,
} from '../../domain/marketFormat.js'
import { instrumentLabelOf } from '../../domain/contracts.js'
import { irsDirectionLabel } from '../../domain/trades.js'

function PnlMetric({ label, value, title, signed = true }) {
  return (
    <div className="book-tile__metric" title={title}>
      <span className="book-tile__metric-label">{label}</span>
      <strong
        className={`book-tile__metric-value${signed ? ` delta--${directionOf(value)}` : ''}`}
      >
        {value == null ? '—' : signed ? formatSignedAmount(value) : formatAmount(value)}
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

function withUnit(value, unit) {
  return value === '—' || !unit ? value : `${value} ${unit}`
}

function positionTitle(position) {
  const terms = position.terms ?? {}
  const instrument = instrumentLabelOf(position)
  if (position.assetClass === 'IRS') {
    return `${instrument} · ${irsDirectionLabel(terms.direction)}`
  }
  return instrument
}

function positionSize(position) {
  const terms = position.terms ?? {}
  if (position.assetClass === 'IRS') {
    return {
      label: 'NOTIONAL',
      value: withUnit(formatAmount(Number(terms.notional)), position.currency),
    }
  }
  if (position.assetClass === 'BOND') {
    const face = Number(terms.face_value)
    const total = Number.isFinite(face) ? Math.abs(position.netQuantity) * face : null
    return { label: 'FACE', value: withUnit(formatAmount(total), position.currency) }
  }
  const labels = {
    EQUITY: 'NET SHARES',
    EUROPEAN_OPTION: 'NET CONTRACTS',
    FX: 'NET NOTIONAL',
    COMMODITY: 'NET UNITS',
  }
  return {
    label: labels[position.assetClass] ?? 'NET QUANTITY',
    value: withUnit(
      formatSignedAmount(position.netQuantity, 0),
      quantityUnitLabelOf(position),
    ),
  }
}

function positionValue(position, value) {
  let displayed = value
  const face = Number(position.terms?.face_value)
  if (position.assetClass === 'BOND' && Number.isFinite(value) && face > 0) {
    displayed = value / face * 100
  }
  const amount = position.assetClass === 'IRS'
    ? formatSignedAmount(displayed)
    : formatUnitPrice(displayed, position.assetClass)
  return withUnit(amount, priceUnitLabelOf(position))
}

function positionValueLabels(position) {
  if (position.assetClass === 'IRS') return ['ENTRY NPV', 'CURRENT NPV']
  if (position.assetClass === 'BOND') return ['ENTRY / 100', 'CURRENT / 100']
  if (position.assetClass === 'EUROPEAN_OPTION') return ['ENTRY PREMIUM', 'MODEL PREMIUM']
  if (position.assetClass === 'FX') return ['AVG ENTRY RATE', 'MARK RATE']
  return ['AVG ENTRY', 'MARK']
}

function PositionList({ positions }) {
  return (
    <ul className="book-positions">
      {positions.map((position) => {
        const size = positionSize(position)
        const [entryLabel, currentLabel] = positionValueLabels(position)
        return (
          <li key={position.id} className="book-position">
            <div className="book-position__head">
              <span className="book-position__symbol">
                {positionTitle(position)}
                {position.provider != null && ` · ${providerLabel(position.provider)}`}
              </span>
              <StatusPill
                level={VALUATION_STATUS_LEVEL[position.status]}
                label={VALUATION_STATUS_LABEL[position.status] ?? position.status}
                compact
              />
            </div>
            <div className="book-position__stats">
              <PositionStat label={size.label} value={size.value} />
              <PositionStat
                label={entryLabel}
                value={positionValue(position, position.averageEntry)}
              />
              <PositionStat
                label={currentLabel}
                value={positionValue(position, position.price)}
              />
              <PositionStat
                label="UNREALIZED PNL"
                value={`${formatSignedAmount(position.unrealizedPnl)} ${position.currency ?? '—'}`}
                tone={directionOf(position.unrealizedPnl)}
              />
            </div>
          </li>
        )
      })}
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
          label={`Gross entry · ${reported.currency}`}
          value={reported.values?.grossEntry ?? null}
          title={reported.title}
          signed={false}
        />
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
        <PnlMetric
          label={`Total PnL · ${reported.currency}`}
          value={reported.values?.total ?? null}
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
