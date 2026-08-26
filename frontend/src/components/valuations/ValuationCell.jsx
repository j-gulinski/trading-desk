import StatusPill from '../status/StatusPill.jsx'
import { VALUATION_STATUS_LABEL, VALUATION_STATUS_LEVEL } from '../../config/valuations.js'
import { providerLabel } from '../../config/providers.js'
import { assetClassLabel } from '../../config/tradeActions.js'
import {
  formatClockTime,
  formatPercent,
  formatShortId,
  formatSignedAmount,
  formatUnitPrice,
} from '../../domain/formatting.js'
import { priceUnitLabelOf } from '../../domain/marketFormat.js'
import { instrumentLabelOf } from '../../domain/contracts.js'
import MoneyCell from '../tables/MoneyCell.jsx'

function currentValueText(valuation) {
  let value = valuation.price
  if (
    valuation.assetClass === 'BOND' &&
    Number.isFinite(value) &&
    Number.isFinite(valuation.faceValue) &&
    valuation.faceValue > 0
  ) {
    value = value / valuation.faceValue * 100
  }
  const amount = valuation.assetClass === 'IRS'
    ? formatSignedAmount(value)
    : formatUnitPrice(value, valuation.assetClass)
  const unit = priceUnitLabelOf(valuation)
  return amount === '—' || !unit ? amount : `${amount} ${unit}`
}

export default function ValuationCell({
  column,
  row,
  comparisonValue,
  comparisonCurrency,
}) {
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
      return instrumentLabelOf(valuation)
    case 'provider':
      return valuation.marketDataProvider ? providerLabel(valuation.marketDataProvider) : '—'
    case 'price':
      return currentValueText(valuation)
    case 'fairValue':
      return (
        <MoneyCell
          value={valuation.fairValue}
          currency={valuation.currency}
          comparisonValue={comparisonValue}
          comparisonCurrency={comparisonCurrency}
        />
      )
    case 'notional':
      return (
        <MoneyCell
          value={valuation.notional}
          currency={valuation.currency}
          comparisonValue={comparisonValue}
          comparisonCurrency={comparisonCurrency}
        />
      )
    case 'unrealized':
      return valuation.closed
        ? '—'
        : (
            <MoneyCell
              value={valuation.unrealizedPnl}
              currency={valuation.currency}
              signed
              comparisonValue={comparisonValue}
              comparisonCurrency={comparisonCurrency}
            />
          )
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
