import { useState } from 'react'
import { useMarketFeedContext } from '../../providers/feedContext.js'
import { useElapsedTime } from '../../hooks/useElapsedTime.js'
import { useTableState } from '../../hooks/useTableState.js'
import {
  CURVE_COLUMNS,
  DEFAULT_CURVE_SORT,
  DEFAULT_MARKET_SORT,
  MARKET_COLUMNS,
  MARKET_FALLBACK_SORT,
  SORT_REQUIRES_CLASS_HINT,
} from '../../config/marketData.js'
import {
  captureMarketSnapshot,
  marketRowsOf,
  sortMarketRows,
  summarizeFeed,
} from '../../domain/marketData.js'
import { formatMarketSymbol } from '../../domain/marketFormat.js'
import { countOptions } from '../../domain/filters.js'
import { formatClockTime, formatNumber } from '../../domain/formatting.js'
import StatCard from '../../components/cards/StatCard.jsx'
import StreamHeader from '../../components/status/StreamHeader.jsx'
import FilterBar from '../../components/filters/FilterBar.jsx'
import { STORAGE_KEYS } from '../../config/storage.js'
import EmptyState from '../../components/EmptyState.jsx'
import ColumnPicker from '../../components/tables/ColumnPicker.jsx'
import SortCaptureStatus from '../../components/tables/SortCaptureStatus.jsx'
import MarketTable from '../../components/marketdata/MarketTable.jsx'

const marketColumnById = new Map(MARKET_COLUMNS.map((column) => [column.id, column]))

function matchesSearch(row, search) {
  if (!search) return true
  return (
    row.instrument.symbol.toLowerCase().includes(search) ||
    formatMarketSymbol(row.instrument).toLowerCase().includes(search)
  )
}

export default function MarketData() {
  const { instruments, tickCount, status, seedStatus } = useMarketFeedContext()
  const { now } = useElapsedTime()

  const [activeClass, setActiveClass] = useState(null)
  const [query, setQuery] = useState('')

  const rows = marketRowsOf(Object.values(instruments), now)
  const marketRows = rows.filter((row) => row.instrument.assetClass !== 'RATE')
  const curveRows = rows.filter((row) => row.instrument.assetClass === 'RATE')

  function sortDisabledReason(column) {
    return column?.requiresClass && !activeClass ? SORT_REQUIRES_CLASS_HINT : null
  }

  const marketTable = useTableState({
    columns: MARKET_COLUMNS,
    storageKey: STORAGE_KEYS.marketColumns,
    defaultSort: DEFAULT_MARKET_SORT,
    fallbackSort: MARKET_FALLBACK_SORT,
    captureSnapshot: (column, capturedAt) =>
      captureMarketSnapshot(marketRows, column, capturedAt),
    isSortable: (column) => Boolean(column?.sortable) && !sortDisabledReason(column),
  })

  const curveTable = useTableState({
    columns: CURVE_COLUMNS,
    storageKey: STORAGE_KEYS.curveColumns,
    defaultSort: DEFAULT_CURVE_SORT,
    captureSnapshot: (column, capturedAt) =>
      captureMarketSnapshot(curveRows, column, capturedAt),
  })

  function handleClassChange(nextClass) {
    setActiveClass(nextClass)
    const sortedColumn = marketColumnById.get(marketTable.sort.column)
    if (!sortedColumn?.requiresClass) return
    if (!nextClass) marketTable.applyDefaultSort()
    else if (sortedColumn.snapshot) {
      marketTable.applySort(marketTable.sort.column, marketTable.sort.direction)
    }
  }

  const search = query.trim().toLowerCase()
  const visibleMarketRows = sortMarketRows(
    marketRows.filter(
      (row) =>
        (!activeClass || row.instrument.assetClass === activeClass) &&
        matchesSearch(row, search),
    ),
    marketTable.sort,
  )
  const visibleCurveRows = sortMarketRows(
    curveRows.filter((row) => matchesSearch(row, search)),
    curveTable.sort,
  )

  const summary = summarizeFeed(Object.values(instruments), now)

  let content
  if (rows.length === 0) {
    if (seedStatus === 'error') {
      content = <EmptyState message="Could not load the market snapshot — retrying on reconnect." />
    } else if (seedStatus === 'loading' || status === 'CONNECTING') {
      content = <EmptyState message="Connecting to market data…" />
    } else if (status === 'RECONNECTING') {
      content = <EmptyState message="Market data stream unavailable — retrying." />
    } else {
      content = <EmptyState message="No instruments published yet." />
    }
  } else {
    content = (
      <div className="market-sections">
        <section className="market-section" aria-labelledby="market-instruments-title">
          <div className="market-section__head">
            <div>
              <h2 id="market-instruments-title">Market instruments</h2>
              <p>Spot and listed prices</p>
            </div>
            <span>{visibleMarketRows.length} rows</span>
          </div>
          <SortCaptureStatus sort={marketTable.sort} />
          {visibleMarketRows.length > 0 ? (
            <MarketTable
              table={marketTable}
              rows={visibleMarketRows}
              sortDisabledReason={sortDisabledReason}
              caption="Live instruments with observed and last-tick change, price history, feed status, and sortable columns"
            />
          ) : (
            <EmptyState message="No market instruments match these filters." />
          )}
        </section>

        <section className="market-section" aria-labelledby="market-curve-title">
          <div className="market-section__head">
            <div>
              <h2 id="market-curve-title">USD government yield curve</h2>
              <p>Observed-period and last-tick movement</p>
            </div>
            <div className="market-section__actions">
              <span>{visibleCurveRows.length} tenors</span>
              <ColumnPicker
                ariaLabel="Yield curve columns"
                columns={CURVE_COLUMNS}
                visibleColumns={curveTable.visibleColumns}
                onToggle={curveTable.toggleColumn}
                onReorder={curveTable.reorderColumn}
                onReset={curveTable.resetColumns}
              />
            </div>
          </div>
          <SortCaptureStatus sort={curveTable.sort} />
          {visibleCurveRows.length > 0 ? (
            <MarketTable
              table={curveTable}
              rows={visibleCurveRows}
              caption="USD government yield-curve tenors with observed and last-tick change, trend, and feed status"
            />
          ) : (
            <EmptyState
              message={
                curveRows.length > 0
                  ? 'No curve tenors match this search.'
                  : 'No curve data published yet.'
              }
            />
          )}
        </section>
      </div>
    )
  }

  return (
    <section className="page">
      <StreamHeader
        title="LIVE MARKET FEED"
        note={`${formatNumber(tickCount)} ticks received · this tab session`}
        status={status}
        stream="MARKET"
      />

      <div className="market-summary">
        <StatCard label="LIVE" value={summary.live} sub="feeding now" tone="info" />
        <StatCard
          label="STALE"
          value={summary.stale}
          sub="> 5s threshold"
          tone={summary.stale > 0 ? 'warn' : 'default'}
        />
        <StatCard
          label="LAST UPDATE"
          value={formatClockTime(summary.lastUpdateMs)}
          sub="newest tick received"
        />
      </div>

      <FilterBar
        label="CLASS"
        ariaLabel="Filter market instruments by asset class"
        options={countOptions(marketRows, (row) => row.instrument.assetClass)}
        value={activeClass}
        onChange={handleClassChange}
        search={{
          label: 'SYMBOL',
          value: query,
          onChange: setQuery,
          placeholder: 'Search symbol…',
        }}
      >
        <ColumnPicker
          ariaLabel="Market instrument columns"
          columns={MARKET_COLUMNS}
          visibleColumns={marketTable.visibleColumns}
          onToggle={marketTable.toggleColumn}
          onReorder={marketTable.reorderColumn}
          onReset={marketTable.resetColumns}
        />
      </FilterBar>

      {content}
    </section>
  )
}
