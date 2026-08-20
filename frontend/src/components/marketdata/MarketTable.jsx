import DataTable from '../tables/DataTable.jsx'
import MarketCell from './MarketCell.jsx'

const TODAY_TITLE = 'Latest accepted value compared with the previous session close'
const TICK_TITLE = 'Latest accepted value compared with the previous accepted provider quote'

function rowKey(row) {
  return row.instrument.id
}

function rowClassName(row) {
  const muted = row.state === 'STALE' || row.state === 'MISSING'
  return muted ? 'data-table__row--muted' : ''
}

function cellClassName(column, row) {
  if (column.id === 'todayChange') return `delta delta--${row.todayDirection}`
  if (column.id === 'tickChange') return `delta delta--${row.tickDirection}`
  return null
}

function cellTitle(column) {
  if (column.id === 'todayChange') return TODAY_TITLE
  if (column.id === 'tickChange') return TICK_TITLE
  return undefined
}

export default function MarketTable({
  table,
  rows,
  caption,
  sortDisabledReason,
  onRemove,
  busyKey,
}) {
  return (
    <DataTable
      columns={table.columns}
      rows={rows}
      rowKey={rowKey}
      renderCell={(column, row) => (
        <MarketCell
          column={column}
          row={row}
          onRemove={onRemove}
          busyKey={busyKey}
        />
      )}
      sort={table.sort}
      onSort={table.toggleSort}
      sortDisabledReason={sortDisabledReason}
      rowClassName={rowClassName}
      cellClassName={cellClassName}
      cellTitle={cellTitle}
      caption={caption}
    />
  )
}
