import { useState } from 'react'
import { useMarketFeedContext } from '../../providers/feedContext.js'
import { useElapsedTime } from '../../hooks/useElapsedTime.js'
import { useTableState } from '../../hooks/useTableState.js'
import { useWatchlist } from '../../hooks/useWatchlist.js'
import {
  DEFAULT_MARKET_COLUMNS,
  DEFAULT_MARKET_SORT,
  MARKET_COLUMNS,
  MARKET_FALLBACK_SORT,
  SORT_REQUIRES_CLASS_HINT,
} from '../../config/marketData.js'
import {
  boardInstruments,
  captureMarketSnapshot,
  instrumentId,
  marketRowsOf,
  sortMarketRows,
  summarizeFeed,
} from '../../domain/marketData.js'
import { formatMarketSymbol } from '../../domain/marketFormat.js'
import { countOptions } from '../../domain/filters.js'
import { formatElapsedTime, formatNumber } from '../../domain/formatting.js'
import StatCard from '../../components/cards/StatCard.jsx'
import StreamHeader from '../../components/status/StreamHeader.jsx'
import FilterBar from '../../components/filters/FilterBar.jsx'
import { STORAGE_KEYS } from '../../config/storage.js'
import EmptyState from '../../components/EmptyState.jsx'
import ColumnPicker from '../../components/tables/ColumnPicker.jsx'
import SortCaptureStatus from '../../components/tables/SortCaptureStatus.jsx'
import MarketTable from '../../components/marketdata/MarketTable.jsx'
import WatchlistSearch from '../../components/marketdata/WatchlistSearch.jsx'
import ProviderStrategyStrip from '../../components/marketdata/ProviderStrategyStrip.jsx'
import MarketBenchmark from '../../components/marketdata/MarketBenchmark.jsx'
import MarketTrendPanel from '../../components/marketdata/MarketTrendPanel.jsx'
import { providerLabel } from '../../config/providers.js'

const marketColumnById = new Map(MARKET_COLUMNS.map((column) => [column.id, column]))

function matchesSearch(row, search) {
  if (!search) return true
  return (
    row.instrument.symbol.toLowerCase().includes(search) ||
    row.instrument.provider?.toLowerCase().includes(search) ||
    formatMarketSymbol(row.instrument).toLowerCase().includes(search)
  )
}

function watchedProvidersOf(items) {
  return new Map(
    items.map((item) => [
      item.symbol,
      new Set(
        Object.entries(item.providers ?? {})
          .filter(([, chosen]) => chosen)
          .map(([provider]) => provider),
      ),
    ]),
  )
}

export default function MarketData() {
  const { instruments, tickCount, status, seedStatus, dropRows } = useMarketFeedContext()
  const watchlist = useWatchlist()
  const { now } = useElapsedTime()

  const [activeClass, setActiveClass] = useState(null)
  const [activeProvider, setActiveProvider] = useState(null)
  const [query, setQuery] = useState('')
  const [inspectedId, setInspectedId] = useState(null)

  async function handleRemove(symbol, provider) {
    const removal = await watchlist.remove(symbol, provider)
    if (!removal) return
    const stillPolled = new Set(removal.still_polled ?? [])
    const gone = (removal.removed_providers ?? []).filter((name) => !stillPolled.has(name))
    if (gone.length > 0) dropRows(gone.map((name) => instrumentId(name, symbol)))
  }

  const board = boardInstruments(
    Object.values(instruments),
    watchlist.items,
    !watchlist.loading,
  )
  const rows = marketRowsOf(board, now)
  const benchmarkRow = rows.find((row) => row.instrument.benchmark) ?? null
  const quoteRows = rows.filter((row) => !row.instrument.benchmark)

  function sortDisabledReason(column) {
    return column?.requiresClass && !activeClass ? SORT_REQUIRES_CLASS_HINT : null
  }

  const marketTable = useTableState({
    columns: MARKET_COLUMNS,
    storageKey: STORAGE_KEYS.marketColumns,
    defaultVisibleColumns: DEFAULT_MARKET_COLUMNS,
    defaultSort: DEFAULT_MARKET_SORT,
    fallbackSort: MARKET_FALLBACK_SORT,
    captureSnapshot: (column, capturedAt) =>
      captureMarketSnapshot(quoteRows, column, capturedAt),
    isSortable: (column) => Boolean(column?.sortable) && !sortDisabledReason(column),
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
  const visibleRows = sortMarketRows(
    quoteRows.filter(
      (row) =>
        (!activeClass || row.instrument.assetClass === activeClass) &&
        (!activeProvider || row.instrument.provider === activeProvider) &&
        matchesSearch(row, search),
    ),
    marketTable.sort,
  )

  const summary = summarizeFeed(quoteRows.map((row) => row.instrument), now)
  const historyLabel = 'today'
  const providerOptions = countOptions(quoteRows, (row) => row.instrument.provider)
    .map((option) => ({ ...option, label: providerLabel(option.value) }))
  const inspectedRow = rows.find((row) => row.instrument.id === inspectedId) ?? null

  function boardEmptyMessage() {
    if (quoteRows.length > 0) return 'No board rows match these filters.'
    if (seedStatus === 'error') {
      return 'Could not load the market snapshot — retrying on reconnect.'
    }
    if (seedStatus === 'loading' || status === 'CONNECTING') {
      return 'Connecting to market data…'
    }
    if (status === 'RECONNECTING') return 'Market data stream unavailable — retrying.'
    return 'The watchlist is empty — search for a symbol above to start the board.'
  }

  return (
    <section className="page">
      <StreamHeader
        title="LIVE MARKET FEED"
        note={`${formatNumber(tickCount)} updates received · this session`}
        status={status}
        stream="MARKET"
      />

      <div className="market-summary">
        <StatCard
          label="SYMBOLS"
          value={summary.symbols}
          sub={`${summary.rows} provider ${summary.rows === 1 ? 'quote' : 'quotes'}`}
        />
        <StatCard label="LIVE" value={summary.live} sub="inside freshness budget" tone="info" />
        <StatCard label="CLOSED" value={summary.closed} sub="latest session quote" />
        <StatCard
          label="STALE"
          value={summary.stale}
          sub="past freshness budget"
          tone={summary.stale > 0 ? 'warn' : 'default'}
        />
        <StatCard
          label="LAST UPDATE"
          value={formatElapsedTime(summary.lastUpdateMs == null ? null : now - summary.lastUpdateMs)}
          sub={summary.missing > 0 ? `${summary.missing} awaiting first quote` : 'all feeds reporting'}
          tone={summary.missing > 0 ? 'warn' : 'default'}
        />
      </div>

      <MarketBenchmark row={benchmarkRow} onInspect={(row) => setInspectedId(row.instrument.id)} />

      <FilterBar
        label="CLASS"
        ariaLabel="Filter market instruments by asset class"
        options={countOptions(quoteRows, (row) => row.instrument.assetClass)}
        value={activeClass}
        onChange={handleClassChange}
        search={{
          label: 'SYMBOL',
          value: query,
          onChange: setQuery,
          placeholder: 'Filter board…',
        }}
      >
        <label className="filter-bar__select-field">
          <span className="filter-bar__label">PROVIDER</span>
          <select
            className="filter-bar__select"
            aria-label="Filter watchlist by provider"
            value={activeProvider ?? ''}
            onChange={(event) => setActiveProvider(event.target.value || null)}
          >
            <option value="">All providers</option>
            {providerOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label} ({option.count})
              </option>
            ))}
          </select>
        </label>
        <ColumnPicker
          ariaLabel="Watchlist board columns"
          columns={MARKET_COLUMNS}
          visibleColumns={marketTable.visibleColumns}
          onToggle={marketTable.toggleColumn}
          onReorder={marketTable.reorderColumn}
          onReset={marketTable.resetColumns}
        />
      </FilterBar>

      <section className="market-section" aria-labelledby="market-board-title">
        <div className="market-section__head">
          <div>
            <h2 id="market-board-title">Market quotes</h2>
            <p>Watchlist by symbol and provider</p>
          </div>
          <div className="market-section__actions">
            <span>{visibleRows.length} rows</span>
          </div>
        </div>
        <ProviderStrategyStrip />
        <WatchlistSearch
          watchedProviders={watchedProvidersOf(watchlist.items)}
          onAdd={watchlist.add}
          busyKey={watchlist.busyKey}
          addError={watchlist.addError}
          onDismissAddError={watchlist.clearAddError}
        />
        {watchlist.removeError && (
          <p className="watchlist-search__error" role="alert">
            {watchlist.removeError}
            <button type="button" onClick={watchlist.clearRemoveError}>
              dismiss
            </button>
          </p>
        )}
        <SortCaptureStatus sort={marketTable.sort} />
        {visibleRows.length > 0 ? (
          <MarketTable
            table={marketTable}
            rows={visibleRows}
            historyLabel={historyLabel}
            sortDisabledReason={sortDisabledReason}
            onInspect={(row) => setInspectedId(row.instrument.id)}
            onRemove={handleRemove}
            busyKey={watchlist.busyKey}
            caption="Watchlist quotes by provider with last price, daily change, intraday history, freshness, and quote time"
          />
        ) : (
          <EmptyState message={boardEmptyMessage()} />
        )}
      </section>

      {inspectedRow && (
        <MarketTrendPanel row={inspectedRow} onClose={() => setInspectedId(null)} />
      )}
    </section>
  )
}
