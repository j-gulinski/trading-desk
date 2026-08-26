import { useState } from 'react'
import DataTable from '../tables/DataTable.jsx'
import MarketCell from './MarketCell.jsx'

const TODAY_TITLE = 'Latest accepted value compared with the previous session close'
const TICK_TITLE = 'Latest accepted value compared with the previous accepted provider quote'
const IDENTITY_CELL_CLASSES = {
  symbol: 'market-symbol-cell market-group-cell',
  name: 'market-name-cell market-identity-cell market-group-cell',
  assetClass: 'market-identity-cell market-group-cell',
  market: 'market-identity-cell market-group-cell',
}

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
    const market = group.find((row) => row.instrument.market)?.instrument.market ?? null
    group.forEach((row, index) => {
      metadata.set(row.instrument.id, {
        first: index === 0,
        last: index === group.length - 1,
        rowSpan: group.length,
        symbol: row.instrument.symbol,
        market,
      })
    })
  }
  return metadata
}

function rowClassName(row, selectedId, selectedSymbol, hoveredSymbol, group) {
  const muted = row.state === 'STALE' || row.state === 'MISSING'
  return [
    'market-provider-row',
    group?.first ? 'market-provider-row--first' : '',
    group?.last ? 'market-provider-row--last' : '',
    group?.symbol === hoveredSymbol ? 'market-provider-row--group-hover' : '',
    group?.symbol === selectedSymbol ? 'market-provider-row--group-selected' : '',
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
  onRefresh,
  busyKey,
  refreshingKey,
  selectedId,
  onSelect,
}) {
  const [hoveredSymbol, setHoveredSymbol] = useState(null)
  const groupedRows = groupedRowsOf(rows)
  const selectedSymbol = groupedRows.get(selectedId)?.symbol ?? null
  const minWidth = Math.max(520, 420 + (table.columns.length - 2) * 64)

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
          onRefresh={onRefresh}
          busyKey={busyKey}
          refreshingKey={refreshingKey}
          market={groupedRows.get(row.instrument.id)?.market}
        />
      )}
      sort={table.sort}
      onSort={table.toggleSort}
      rowClassName={(row) => rowClassName(
        row,
        selectedId,
        selectedSymbol,
        hoveredSymbol,
        groupedRows.get(row.instrument.id),
      )}
      cellClassName={cellClassName}
      cellTitle={cellTitle}
      cellProps={(column, row) => {
        const className = IDENTITY_CELL_CLASSES[column.id]
        if (!className) return null
        const group = groupedRows.get(row.instrument.id)
        if (!group?.first) return { skip: true }
        return { rowSpan: group.rowSpan, className }
      }}
      caption={caption}
      onRowClick={onSelect}
      onRowMouseEnter={(row) => setHoveredSymbol(row.instrument.symbol)}
      onRowMouseLeave={() => setHoveredSymbol(null)}
      tableClassName="market-quotes-table"
      wrapClassName="market-quotes-table-wrap"
      minWidth={minWidth}
    />
  )
}
