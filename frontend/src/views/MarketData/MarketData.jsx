import { useMemo, useState } from 'react'
import { useMarketFeedContext } from '../../providers/marketFeedContext.js'
import { useElapsedTime } from '../../hooks/useElapsedTime.js'
import { useTableState } from '../../hooks/useTableState.js'
import {
  CURVE_COLUMNS,
  DEFAULT_CURVE_SORT,
  DEFAULT_MARKET_SORT,
  MARKET_COLUMNS,
  MARKET_FALLBACK_SORT,
  MARKET_STATUS_LEVEL,
  SORT_REQUIRES_CLASS_HINT,
} from '../../config/marketData.js'
import {
  captureMarketSnapshot,
  marketRowsOf,
  sortMarketRows,
  summarizeFeed,
} from '../../domain/marketData.js'
import { formatMarketSymbol, formatStreamTime } from '../../domain/marketFormat.js'
import { formatNumber } from '../../domain/formatting.js'
import StatCard from '../../components/cards/StatCard.jsx'
import StatusPill from '../../components/status/StatusPill.jsx'
import FilterChipGroup from '../../components/filters/FilterChipGroup.jsx'
import EmptyState from '../../components/EmptyState.jsx'
import ColumnPicker from '../../components/tables/ColumnPicker.jsx'
import MarketTable from '../../components/marketdata/MarketTable.jsx'
import MarketIndexCard from '../../components/marketdata/MarketIndexCard.jsx'

const MARKET_COLUMNS_STORAGE_KEY = 'market-data.visible-columns'
const CURVE_COLUMNS_STORAGE_KEY = 'market-data.curve-visible-columns'
const BENCHMARK_ID = 'MARKET_INDEX'

const marketColumnById = new Map(MARKET_COLUMNS.map((column) => [column.id, column]))

function matchesSearch(row, search) {
  if (!search) return true
  return (
    row.instrument.symbol.toLowerCase().includes(search) ||
    formatMarketSymbol(row.instrument).toLowerCase().includes(search)
  )
}

function assetClassOptions(rows) {
  const counts = new Map()
  for (const row of rows) {
    const assetClass = row.instrument.assetClass
    counts.set(assetClass, (counts.get(assetClass) ?? 0) + 1)
  }
  return Array.from(counts, ([assetClass, count]) => ({
    value: assetClass,
    label: assetClass,
    count,
  })).sort((a, b) => a.value.localeCompare(b.value))
}

function SortCaptureStatus({ sort }) {
  if (sort.capturedAt == null) return null
  return (
    <div className="table-sort-status" role="status">
      Order captured {formatStreamTime(sort.capturedAt).slice(0, 5)} · values live
    </div>
  )
}

export default function MarketData() {
  const { instruments, tickCount, status, snapshotSettled } = useMarketFeedContext()
  const { now } = useElapsedTime()

  const [activeClass, setActiveClass] = useState(null)
  const [query, setQuery] = useState('')

  const rows = useMemo(
    () => marketRowsOf(Object.values(instruments), now),
    [instruments, now],
  )
  const marketRows = useMemo(
    () =>
      rows.filter(
        (row) => row.instrument.assetClass !== 'RATE' && row.instrument.id !== BENCHMARK_ID,
      ),
    [rows],
  )
  const curveRows = useMemo(
    () => rows.filter((row) => row.instrument.assetClass === 'RATE'),
    [rows],
  )

  function sortDisabledReason(column) {
    return column?.requiresClass && !activeClass ? SORT_REQUIRES_CLASS_HINT : null
  }

  const marketTable = useTableState({
    columns: MARKET_COLUMNS,
    storageKey: MARKET_COLUMNS_STORAGE_KEY,
    defaultSort: DEFAULT_MARKET_SORT,
    fallbackSort: MARKET_FALLBACK_SORT,
    captureSnapshot: (column, capturedAt) =>
      captureMarketSnapshot(marketRows, column, capturedAt),
    isSortable: (column) => Boolean(column?.sortable) && !sortDisabledReason(column),
  })

  const curveTable = useTableState({
    columns: CURVE_COLUMNS,
    storageKey: CURVE_COLUMNS_STORAGE_KEY,
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
  const benchmark = instruments[BENCHMARK_ID]

  let content
  if (rows.length === 0) {
    if (!snapshotSettled || status === 'CONNECTING') {
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
      <div className="market-head">
        <span className="market-head__title">LIVE MARKET FEED</span>
        <div className="market-head__meta">
          <span className="market-head__ticks">
            {formatNumber(tickCount)} ticks received · this tab session
          </span>
          <StatusPill level={MARKET_STATUS_LEVEL[status] ?? 'unknown'} label={status} />
        </div>
      </div>

      <div className="market-summary">
        <MarketIndexCard instrument={benchmark} now={now} />
        <StatCard label="LIVE" value={summary.live} sub="feeding now" tone="info" />
        <StatCard
          label="STALE"
          value={summary.stale}
          sub="> 5s threshold"
          tone={summary.stale > 0 ? 'warn' : 'default'}
        />
        <StatCard
          label="LAST UPDATE"
          value={formatStreamTime(summary.lastUpdateMs)}
          sub="market data"
        />
      </div>

      <div className="market-controls">
        <span className="market-controls__label">CLASS</span>
        <FilterChipGroup
          className="market-classes"
          ariaLabel="Filter market instruments by asset class"
          options={assetClassOptions(marketRows)}
          value={activeClass}
          onChange={handleClassChange}
        />
        <div className="market-controls__tools">
          <label className="market-search-field">
            <span className="market-controls__label">SYMBOL</span>
            <input
              className="market-search"
              type="search"
              placeholder="Search symbol…"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
          </label>
          <ColumnPicker
            ariaLabel="Market instrument columns"
            columns={MARKET_COLUMNS}
            visibleColumns={marketTable.visibleColumns}
            onToggle={marketTable.toggleColumn}
            onReorder={marketTable.reorderColumn}
            onReset={marketTable.resetColumns}
          />
        </div>
      </div>

      {content}
    </section>
  )
}
