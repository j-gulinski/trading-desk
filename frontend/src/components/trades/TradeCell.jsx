import StatusPill from '../status/StatusPill.jsx'
import { VALUATION_STATUS_LABEL, VALUATION_STATUS_LEVEL } from '../../config/valuations.js'
import {
  formatAmount,
  formatClockTime,
  formatDateTime,
  formatPercent,
  formatSignedAmount,
  formatUnitPrice,
} from '../../domain/formatting.js'

export default function TradeCell({ column, row, onSelect }) {
  const { trade, valuation, valuationStatus } = row

  switch (column.id) {
    case 'trade':
      return (
        <button
          type="button"
          className="trade-cell__link"
          onClick={(event) => {
            event.stopPropagation()
            onSelect(trade.id)
          }}
        >
          {trade.tradeRef}
        </button>
      )
    case 'book':
      return trade.bookName
    case 'assetClass':
      return (
        <span className="class-tag">
          <span className="class-tag__dot" />
          {trade.assetClass}
        </span>
      )
    case 'symbol':
      return trade.symbol ?? '—'
    case 'side':
      return <span className={`trade-side trade-side--${trade.side.toLowerCase()}`}>{trade.side}</span>
    case 'quantity':
      return trade.quantity
    case 'entry':
      return formatUnitPrice(trade.entryPrice, trade.assetClass)
    case 'provider':
      return trade.provider ?? '—'
    case 'price':
      return formatUnitPrice(valuation?.price, trade.assetClass)
    case 'fairValue':
      return formatAmount(valuation?.fairValue)
    case 'pnl':
      return formatSignedAmount(row.pnl)
    case 'return':
      return valuation?.closed ? '—' : formatPercent(valuation?.returnPercent)
    case 'opened':
      // Closed history reaches back days, so a bare clock time would be ambiguous.
      return formatDateTime(trade.openedAtMs)
    case 'updated':
      return formatClockTime(valuation?.valuationTimeMs, { millis: true })
    case 'valuation':
      return (
        <StatusPill
          level={VALUATION_STATUS_LEVEL[valuationStatus]}
          label={VALUATION_STATUS_LABEL[valuationStatus] ?? valuationStatus}
          compact
        />
      )
    default:
      return null
  }
}
