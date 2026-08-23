import DataTable from '../tables/DataTable.jsx'
import MarketCell from './MarketCell.jsx'

const TODAY_TITLE = 'Latest accepted value compared with the previous session close'
const TICK_TITLE = 'Latest accepted value compared with the previous accepted provider quote'

function rowKey(row) {
  return row.instrument.id
}

function groupedRowsOf(rows) {
  const groups = new Map()
  for (const row of rows) {
    const symbol = row.instrument.symbol
    const group = groups.get(symbol) ?? []
    group.push(row)
    groups.set(symbol, group)
  }

  const metadata = new Map()
  for (const group of groups.values()) {
    group.forEach((row, index) => {
      metadata.set(row.instrument.id, {
        first: index === 0,
        last: index === group.length - 1,
        rowSpan: group.length,
      })
    })
  }
  return metadata
}

function rowClassName(row, selectedId, group) {
  const muted = row.state === 'STALE' || row.state === 'MISSING'
  return [
    'market-provider-row',
    group?.first ? 'market-provider-row--first' : '',
    group?.last ? 'market-provider-row--last' : '',
    muted ? 'data-table__row--muted' : '',
    row.instrument.id === selectedId ? 'data-table__row--selected' : '',
  ].filter(Boolean).join(' ')
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
  strategies,
  onRemove,
  busyKey,
  selectedId,
  onSelect,
}) {
  const groupedRows = groupedRowsOf(rows)

  return (
    <DataTable
      columns={table.columns}
      rows={rows}
      rowKey={rowKey}
      renderCell={(column, row) => (
        <MarketCell
          column={column}
          row={row}
          strategies={strategies}
          onRemove={onRemove}
          busyKey={busyKey}
        />
      )}
      sort={table.sort}
      onSort={table.toggleSort}
      rowClassName={(row) => rowClassName(row, selectedId, groupedRows.get(row.instrument.id))}
      cellClassName={cellClassName}
      cellTitle={cellTitle}
      cellProps={(column, row) => {
        if (column.id !== 'symbol') return null
        const group = groupedRows.get(row.instrument.id)
        if (!group?.first) return { skip: true }
        return { rowSpan: group.rowSpan, className: 'market-symbol-cell' }
      }}
      caption={caption}
      onRowClick={onSelect}
    />
  )
}
