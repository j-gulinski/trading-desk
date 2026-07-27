import DataTable from '../tables/DataTable.jsx'
import MarketCell from './MarketCell.jsx'

const LAST_TICK_TITLE = 'Latest accepted value compared with the previous accepted value'

function rowKey(row) {
  return `${row.instrument.id}:${row.instrument.updateSeq}`
}

function rowClassName(row) {
  const flashing =
    row.live &&
    (row.instrument.lastDirection === 'pos' || row.instrument.lastDirection === 'neg')
  return [
    !row.live && 'market-row--stale',
    flashing && `market-row--tick-${row.instrument.lastDirection}`,
  ]
    .filter(Boolean)
    .join(' ')
}

function cellClassName(column, row) {
  if (column.id === 'observedChange') {
    return `market-delta market-delta--${row.observedDirection}`
  }
  if (column.id === 'lastTickChange') {
    return `market-delta market-delta--${row.lastTickDirection}`
  }
  return null
}

function cellTitle(column, row) {
  if (column.id === 'observedChange') {
    const { observations } = row.observedChange
    return `Since loaded · ${observations} observed ${observations === 1 ? 'value' : 'values'}`
  }
  if (column.id === 'lastTickChange') return LAST_TICK_TITLE
  return undefined
}

export default function MarketTable({ table, rows, caption, sortDisabledReason }) {
  return (
    <DataTable
      columns={table.columns}
      rows={rows}
      rowKey={rowKey}
      renderCell={(column, row) => <MarketCell column={column} row={row} />}
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
