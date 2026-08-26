import StatusPill from '../status/StatusPill.jsx'
import { VALUATION_STATUS_LABEL, VALUATION_STATUS_LEVEL } from '../../config/valuations.js'
import { providerLabel } from '../../config/providers.js'
import { assetClassLabel } from '../../config/tradeActions.js'
import {
  formatAmount,
  formatClockTime,
  formatPercent,
  formatShortId,
  formatSignedAmount,
  formatUnitPrice,
} from '../../domain/formatting.js'

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
          {assetClassLabel(valuation.assetClass)}
        </span>
      )
    case 'symbol':
      return valuation.symbol ?? '—'
    case 'provider':
      return valuation.marketDataProvider ? providerLabel(valuation.marketDataProvider) : '—'
    case 'price':
      return formatUnitPrice(valuation.price, valuation.assetClass)
    case 'fairValue':
      return formatAmount(valuation.fairValue)
    case 'notional':
      return formatAmount(valuation.notional)
    case 'unrealized':
      return valuation.closed ? '—' : formatSignedAmount(valuation.unrealizedPnl)
    case 'return':
      return valuation.closed ? '—' : formatPercent(valuation.returnPercent)
    case 'updated':
      return formatClockTime(valuation.valuationTimeMs, { millis: true })
    case 'valuation':
      return (
        <StatusPill
          level={VALUATION_STATUS_LEVEL[status]}
          label={VALUATION_STATUS_LABEL[status] ?? status}
          compact
        />
      )
    default:
      return null
  }
}
