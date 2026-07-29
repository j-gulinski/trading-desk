import DataTable from '../tables/DataTable.jsx'
import ValuationCell from './ValuationCell.jsx'
import { directionOf } from '../../domain/formatting.js'

function rowKey(row) {
  return row.valuation.id
}

function rowClassName(row) {
  return row.status !== 'LIVE' ? 'data-table__row--muted' : null
}

const TONE_SOURCE = {
  unrealized: (valuation) => (valuation.closed ? null : valuation.unrealizedPnl),
  return: (valuation) => (valuation.closed ? null : valuation.returnPercent),
  realized: (valuation) => valuation.realizedPnl,
}

function cellClassName(column, row) {
  const toneOf = TONE_SOURCE[column.id]
  return toneOf ? `delta delta--${directionOf(toneOf(row.valuation))}` : null
}

export default function ValuationTable({ table, rows, caption }) {
  return (
    <DataTable
      columns={table.columns}
      rows={rows}
      rowKey={rowKey}
      renderCell={(column, row) => <ValuationCell column={column} row={row} />}
      sort={table.sort}
      onSort={table.toggleSort}
      rowClassName={rowClassName}
      cellClassName={cellClassName}
      caption={caption}
    />
  )
}
