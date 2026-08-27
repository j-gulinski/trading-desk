import DataTable from '../tables/DataTable.jsx'
import TradeCell from './TradeCell.jsx'
import { directionOf } from '../../domain/formatting.js'

function rowClassName(row, selectedTradeId) {
  return [
    row.valuationStatus !== 'LIVE' && 'data-table__row--muted',
    row.trade.id === selectedTradeId && 'data-table__row--selected',
  ]
    .filter(Boolean)
    .join(' ')
}

const TONE_SOURCE = {
  pnl: (row) => row.pnl,
  return: (row) => (row.valuation?.closed ? null : row.valuation?.returnPercent),
}

function cellClassName(column, row) {
  const toneOf = TONE_SOURCE[column.id]
  return toneOf ? `delta delta--${directionOf(toneOf(row))}` : null
}

function cellTitle(column, row) {
  if (column.id !== 'pnl') return undefined
  return row.lifecycle === 'OPEN' ? 'Unrealized PnL' : 'Realized PnL'
}

export default function TradeTable({
  table,
  rows,
  selectedTradeId,
  onSelect,
  caption,
  sortDisabledReason,
  comparisonCurrency,
}) {
  return (
    <DataTable
      columns={table.columns}
      rows={rows}
      rowKey={(row) => row.trade.id}
      renderCell={(column, row) => (
        <TradeCell
          column={column}
          row={row}
          onSelect={onSelect}
          comparisonValue={
            column.id === table.sort.column ? table.sort.snapshot?.[row.trade.id] : null
          }
          comparisonCurrency={comparisonCurrency}
        />
      )}
      sort={table.sort}
      onSort={table.toggleSort}
      sortDisabledReason={sortDisabledReason}
      rowClassName={(row) => rowClassName(row, selectedTradeId)}
      cellClassName={cellClassName}
      cellTitle={cellTitle}
      onRowClick={(row) => onSelect(row.trade.id)}
      caption={caption}
      tableClassName="trade-blotter-table"
      wrapClassName="trade-blotter-table-wrap"
      minWidth={960}
    />
  )
}
