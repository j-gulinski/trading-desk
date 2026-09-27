import { formatAmount, formatSignedAmount } from '../../domain/formatting.js'

export default function MoneyCell({ value, currency, signed = false }) {
  const formatted = signed ? formatSignedAmount(value) : formatAmount(value)
  return (
    <span className="money-cell">
      {formatted === '—' || !currency ? formatted : `${formatted} ${currency}`}
    </span>
  )
}
