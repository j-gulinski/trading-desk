import StatusPill from '../status/StatusPill.jsx'
import { VALUATION_STATUS_LABEL, VALUATION_STATUS_LEVEL } from '../../config/valuations.js'
import { providerLabel } from '../../config/providers.js'
import { assetClassLabel } from '../../config/tradeActions.js'
import {
  formatClockTime,
  formatDateTime,
  formatNumber,
  formatPercent,
  formatSignedAmount,
  formatUnitPrice,
} from '../../domain/formatting.js'
import {
  tradePositionLabel,
  tradePriceForDisplay,
  tradeSize,
} from '../../domain/trades.js'
import { instrumentLabelOf } from '../../domain/contracts.js'
import { priceUnitLabelOf, quantityUnitLabelOf } from '../../domain/marketFormat.js'
import MoneyCell from '../tables/MoneyCell.jsx'

function withUnit(value, unit) {
  return value === '—' || !unit ? value : `${value} ${unit}`
}

function tradeValueText(trade, value) {
  const display = tradePriceForDisplay(trade, value)
  const amount = trade.assetClass === 'IRS'
    ? formatSignedAmount(display)
    : formatUnitPrice(display, trade.assetClass)
  return withUnit(amount, priceUnitLabelOf(trade))
}

export default function TradeCell({
  column,
  row,
  onSelect,
  comparisonValue,
  comparisonCurrency,
}) {
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
          {assetClassLabel(trade.assetClass)}
        </span>
      )
    case 'symbol':
      return instrumentLabelOf(trade)
    case 'side':
      return (
        <span className={`trade-side trade-side--${trade.side.toLowerCase()}`}>
          {tradePositionLabel(trade)}
        </span>
      )
    case 'quantity':
      return withUnit(formatNumber(tradeSize(trade)), quantityUnitLabelOf(trade))
    case 'entry':
      return tradeValueText(trade, trade.entryPrice)
    case 'provider':
      return trade.provider || valuation?.marketDataProvider
        ? providerLabel(trade.provider ?? valuation.marketDataProvider)
        : '—'
    case 'price':
      return tradeValueText(trade, valuation?.price)
    case 'fairValue':
      return (
        <MoneyCell
          value={valuation?.fairValue}
          currency={valuation?.currency ?? trade.currency}
          comparisonValue={comparisonValue}
          comparisonCurrency={comparisonCurrency}
        />
      )
    case 'pnl':
      return (
        <MoneyCell
          value={row.pnl}
          currency={valuation?.currency ?? trade.currency}
          signed
          comparisonValue={comparisonValue}
          comparisonCurrency={comparisonCurrency}
        />
      )
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
