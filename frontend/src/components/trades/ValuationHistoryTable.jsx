import DataTable from '../tables/DataTable.jsx'
import {
  directionOf,
  formatAmount,
  formatDateTime,
  formatSignedAmount,
} from '../../domain/formatting.js'

const HISTORY_COLUMNS = [
  { id: 'time', label: 'Valuation time', cellClass: 'data-table__cell--time' },
  { id: 'fairValue', label: 'Position value', numeric: true },
  { id: 'unrealized', label: 'Unrealized PnL', numeric: true },
  { id: 'realized', label: 'Realized PnL', numeric: true },
  { id: 'total', label: 'Total PnL', numeric: true },
]

function withCurrency(value, currency) {
  return value === '—' || !currency ? value : `${value} ${currency}`
}

function HistoryCell({ column, valuation }) {
  if (column.id === 'time') return formatDateTime(valuation.valuationTimeMs, { millis: true })
  if (column.id === 'fairValue') {
    return withCurrency(formatAmount(valuation.fairValue), valuation.currency)
  }
  if (column.id === 'unrealized') {
    return withCurrency(formatSignedAmount(valuation.unrealizedPnl), valuation.currency)
  }
  if (column.id === 'realized') {
    return withCurrency(formatSignedAmount(valuation.realizedPnl), valuation.currency)
  }
  if (column.id === 'total') {
    return withCurrency(formatSignedAmount(valuation.totalPnl), valuation.currency)
  }
  return null
}

const TONE_SOURCE = {
  unrealized: (valuation) => valuation.unrealizedPnl,
  realized: (valuation) => valuation.realizedPnl,
  total: (valuation) => valuation.totalPnl,
}

function cellClassName(column, valuation) {
  const value = TONE_SOURCE[column.id]?.(valuation)
  return value == null ? null : `delta delta--${directionOf(value)}`
}

export default function ValuationHistoryTable({ valuations }) {
  return (
    <DataTable
      columns={HISTORY_COLUMNS}
      rows={valuations}
      rowKey={(valuation) => valuation.id}
      renderCell={(column, valuation) => (
        <HistoryCell column={column} valuation={valuation} />
      )}
      cellClassName={cellClassName}
      caption="Newest-first valuation history for the selected trade"
    />
  )
}
