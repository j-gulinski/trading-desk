import StatusPill from '../status/StatusPill.jsx'
import {
  formatAmount,
  formatClockTime,
  formatPercent,
  formatShortId,
  formatSignedAmount,
  formatUnitPrice,
} from '../../domain/formatting.js'

const STATUS_LEVEL = { LIVE: 'info', STALE: 'stale', CLOSED: 'unknown' }

export default function ValuationCell({ column, row }) {
  const { valuation, status } = row

  switch (column.id) {
    case 'trade':
      return valuation.tradeRef
    case 'book':
      return valuation.bookName ?? formatShortId(valuation.bookId)
    case 'assetClass':
      return (
        <span className="class-tag">
          <span className="class-tag__dot" />
          {valuation.assetClass}
        </span>
      )
    case 'symbol':
      return valuation.symbol ?? '—'
    case 'price':
      return formatUnitPrice(valuation.price, valuation.assetClass)
    case 'fairValue':
      return formatAmount(valuation.fairValue)
    case 'unrealized':
      return valuation.closed ? '—' : formatSignedAmount(valuation.unrealizedPnl)
    case 'return':
      return valuation.closed ? '—' : formatPercent(valuation.returnPercent)
    case 'realized':
      return formatSignedAmount(valuation.realizedPnl)
    case 'updated':
      return formatClockTime(valuation.valuationTimeMs, { millis: true })
    case 'valuation':
      return <StatusPill level={STATUS_LEVEL[status]} label={status} compact />
    default:
      return null
  }
}
