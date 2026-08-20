import DataTable from '../tables/DataTable.jsx'
import MarketCell from './MarketCell.jsx'

const TODAY_TITLE = 'Latest accepted value compared with the previous session close'

function rowKey(row) {
  return row.instrument.id
}

function rowClassName(row) {
  const { lastDirection } = row.instrument
  const flashing = row.live && lastDirection !== 'flat'
  const muted = row.state === 'STALE' || row.state === 'MISSING'
  return [
    muted && 'data-table__row--muted',
    flashing && `data-table__row--tick-${lastDirection}`,
  ]
    .filter(Boolean)
    .join(' ')
}

function cellClassName(column, row) {
  if (column.id === 'todayChange') return `delta delta--${row.todayDirection}`
  return null
}

function cellTitle(column) {
  if (column.id === 'todayChange') return TODAY_TITLE
  return undefined
}

export default function MarketTable({
  table,
  rows,
  caption,
  historyLabel,
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
          historyLabel={historyLabel}
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
