import { formatAmount, formatSignedAmount } from '../../domain/formatting.js'

export default function MoneyCell({
  value,
  currency,
  signed = false,
  comparisonValue = null,
  comparisonCurrency = null,
}) {
  const formatted = signed ? formatSignedAmount(value) : formatAmount(value)
  const nativeText = formatted === '—' || !currency ? formatted : `${formatted} ${currency}`
  const showComparison = (
    Number.isFinite(comparisonValue) &&
    comparisonValue !== 0 &&
    comparisonCurrency != null &&
    currency != null &&
    currency !== comparisonCurrency
  )

  return (
    <span className="money-cell">
      <span>{nativeText}</span>
      {showComparison && (
        <span
          className="money-cell__comparison"
          title={`Captured approximate ${comparisonCurrency} value used for this sort`}
        >
          ≈ {signed ? formatSignedAmount(comparisonValue) : formatAmount(comparisonValue)}{' '}
          {comparisonCurrency}
        </span>
      )}
    </span>
  )
}
