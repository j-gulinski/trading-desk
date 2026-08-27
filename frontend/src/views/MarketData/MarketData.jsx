import { useEffect, useState } from 'react'
import { useMarketFeedContext } from '../../providers/feedContext.js'
import { useElapsedTime } from '../../hooks/useElapsedTime.js'
import { usePolling } from '../../hooks/usePolling.js'
import { useTableState } from '../../hooks/useTableState.js'
import { useWatchlist } from '../../hooks/useWatchlist.js'
import { apiGet } from '../../services/apiClient.js'
import { endpoints } from '../../services/endpoints.js'
import {
  DEFAULT_MARKET_COLUMNS,
  DEFAULT_MARKET_SORT,
  MARKET_COLUMNS,
  MARKET_FALLBACK_SORT,
  PROVIDERS_POLL_INTERVAL_MS,
} from '../../config/marketData.js'
import {
  boardInstruments,
  instrumentId,
  marketRowsOf,
  providerStrategiesOf,
  summarizeFeed,
} from '../../domain/marketData.js'
import { formatMarketSymbol, marketLabelOf } from '../../domain/marketFormat.js'
import { countOptions } from '../../domain/filters.js'
import { formatElapsedTime, formatNumber } from '../../domain/formatting.js'
import StatCard from '../../components/cards/StatCard.jsx'
import StreamHeader from '../../components/status/StreamHeader.jsx'
import FilterBar from '../../components/filters/FilterBar.jsx'
import { STORAGE_KEYS } from '../../config/storage.js'
import EmptyState from '../../components/EmptyState.jsx'
import LoadingSkeleton from '../../components/LoadingSkeleton.jsx'
import ColumnPicker from '../../components/tables/ColumnPicker.jsx'
import MarketTable from '../../components/marketdata/MarketTable.jsx'
import WatchlistSearch from '../../components/marketdata/WatchlistSearch.jsx'
import ProviderStrategyStrip from '../../components/marketdata/ProviderStrategyStrip.jsx'
import MarketBenchmark from '../../components/marketdata/MarketBenchmark.jsx'
import OfficialRates from '../../components/marketdata/OfficialRates.jsx'
import CurveSection from '../../components/marketdata/CurveSection.jsx'
import QuoteHistoryPanel from '../../components/marketdata/QuoteHistoryPanel.jsx'
import { providerLabel } from '../../config/providers.js'
import { assetClassLabel } from '../../config/tradeActions.js'
import { usePanelCoordinator } from '../../layout/panelContext.js'

function matchesSearch(row, search) {
  if (!search) return true
  return (
    row.instrument.symbol.toLowerCase().includes(search) ||
    formatMarketSymbol(row.instrument).toLowerCase().includes(search) ||
    row.instrument.name?.toLowerCase().includes(search)
  )
}

function groupSortValue(group, column) {
  const first = group[0]?.instrument
  if (column === 'name') return first?.name ?? null
  if (column === 'assetClass') return first?.assetClass ?? null
  if (column === 'market') {
    const observed = group.find((row) => row.instrument.market)?.instrument ?? first
    const market = observed ? marketLabelOf(observed) : null
    return market === '—' ? null : market
  }
  return first?.symbol ?? null
}

function sortGroupedRows(rows, sort) {
  const groups = new Map()
  for (const row of rows) {
    const group = groups.get(row.instrument.symbol) ?? []
    group.push(row)
    groups.set(row.instrument.symbol, group)
  }
  for (const group of groups.values()) {
    group.sort((left, right) =>
      left.instrument.provider.localeCompare(right.instrument.provider) ||
      left.instrument.id.localeCompare(right.instrument.id),
    )
  }
  const direction = sort.direction === 'desc' ? -1 : 1
  return [...groups.values()]
    .sort((left, right) => {
      const a = groupSortValue(left, sort.column)
      const b = groupSortValue(right, sort.column)
      if (a == null || b == null) {
        if (a == null && b == null) return left[0].instrument.symbol.localeCompare(right[0].instrument.symbol)
        return a == null ? 1 : -1
      }
      const compared = String(a).localeCompare(String(b))
      if (compared !== 0) return compared * direction
      return left[0].instrument.symbol.localeCompare(right[0].instrument.symbol)
    })
    .flat()
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
  const { instruments, curves, tickCount, status, seedStatus, dropRows } = useMarketFeedContext()
  const watchlist = useWatchlist()
  const { now } = useElapsedTime()
  const { activePanel } = usePanelCoordinator()
  const providersPoll = usePolling(
    ({ signal }) => apiGet(endpoints.marketData.providers, { signal }),
    { intervalMs: PROVIDERS_POLL_INTERVAL_MS },
  )
  const strategies = providerStrategiesOf(providersPoll.data)

  const [activeClass, setActiveClass] = useState(null)
  const [activeProvider, setActiveProvider] = useState(null)
  const [query, setQuery] = useState('')
  const [selectedId, setSelectedId] = useState(null)
  async function handleRemove(symbol, provider) {
    const removal = await watchlist.remove(symbol, provider)
    if (!removal) return
    const stillPolled = new Set(removal.still_polled ?? [])
    const gone = (removal.removed_providers ?? []).filter((name) => !stillPolled.has(name))
    if (gone.length > 0) {
      const ids = gone.map((name) => instrumentId(name, symbol))
      dropRows(ids)
      if (selectedId && ids.includes(selectedId)) setSelectedId(null)
    }
  }

  const board = boardInstruments(
    Object.values(instruments),
    watchlist.items,
    !watchlist.loading,
  )
  const rows = marketRowsOf(board, now)
  const benchmarkRow = rows.find((row) => row.instrument.benchmark) ?? null
  const referenceRows = rows
    .filter((row) => row.instrument.reference)
    .sort((left, right) =>
      left.instrument.symbol.localeCompare(right.instrument.symbol) ||
      left.instrument.provider.localeCompare(right.instrument.provider),
    )
  const quoteRows = rows.filter(
    (row) => !row.instrument.benchmark && !row.instrument.reference,
  )
  const selectedRow =
    [...quoteRows, ...referenceRows].find((row) => row.instrument.id === selectedId) ?? null

  useEffect(() => {
    if (selectedId && selectedRow == null) setSelectedId(null)
  }, [selectedId, selectedRow])

  useEffect(() => {
    if (activePanel != null && selectedId != null) setSelectedId(null)
  }, [activePanel, selectedId])

  const marketTable = useTableState({
    columns: MARKET_COLUMNS,
    storageKey: STORAGE_KEYS.marketColumns,
    defaultVisibleColumns: DEFAULT_MARKET_COLUMNS,
    defaultSort: DEFAULT_MARKET_SORT,
    fallbackSort: MARKET_FALLBACK_SORT,
  })

  const search = query.trim().toLowerCase()
  const visibleRows = sortGroupedRows(
    quoteRows.filter(
      (row) =>
        (!activeClass || row.instrument.assetClass === activeClass) &&
        (!activeProvider || row.instrument.provider === activeProvider) &&
        matchesSearch(row, search),
    ),
    marketTable.sort,
  )
  const visibleSymbols = new Set(visibleRows.map((row) => row.instrument.symbol)).size

  const summary = summarizeFeed(quoteRows.map((row) => row.instrument), now)
  const symbolRows = Array.from(
    new Map(quoteRows.map((row) => [row.instrument.symbol, row])).values(),
  )
  const providerOptions = countOptions(quoteRows, (row) => row.instrument.provider)
    .map((option) => ({ ...option, label: providerLabel(option.value) }))
  const boardLoading =
    quoteRows.length === 0 && (seedStatus === 'loading' || status === 'CONNECTING')

  function boardEmptyMessage() {
    if (quoteRows.length > 0) return 'No board rows match these filters.'
    if (seedStatus === 'error') {
      return 'Could not load the market snapshot — retrying on reconnect.'
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
        <StatCard
          label="EOD"
          value={summary.eod + summary.closed}
          sub="latest accepted close"
        />
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

      <div className="market-context">
        <MarketBenchmark row={benchmarkRow} />
        <OfficialRates
          rows={referenceRows}
          selectedId={selectedId}
          onSelect={(row) => setSelectedId(row.instrument.id)}
        />
      </div>

      <FilterBar
        label="CLASS"
        ariaLabel="Filter market instruments by asset class"
        options={countOptions(symbolRows, (row) => row.instrument.assetClass, assetClassLabel)}
        value={activeClass}
        onChange={setActiveClass}
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
        <div className="market-column-picker">
          <ColumnPicker
            ariaLabel="Watchlist board columns"
            columns={MARKET_COLUMNS}
            visibleColumns={marketTable.visibleColumns}
            onToggle={marketTable.toggleColumn}
            onReorder={marketTable.reorderColumn}
            onReset={marketTable.resetColumns}
          />
        </div>
        <span
          className="market-compact-mode"
          title="Compact quote columns with row actions retained"
        >
          Compact trading view
        </span>
      </FilterBar>

      <section className="market-section" aria-labelledby="market-board-title">
        <div className="market-section__head">
          <div>
            <h2 id="market-board-title">Market quotes</h2>
            <p>Instrument identity first, provider observations second</p>
          </div>
          <div className="market-section__actions">
            <span>Select a row for observed history</span>
            <span>{visibleSymbols} symbols · {visibleRows.length} feeds</span>
          </div>
        </div>
        <ProviderStrategyStrip
          providers={providersPoll.data}
          now={now}
          snapshotAtMs={providersPoll.lastUpdated}
        />
        <WatchlistSearch
          watchedProviders={watchedProvidersOf(watchlist.items)}
          onAdd={watchlist.add}
          busyKey={watchlist.busyKey}
          addError={watchlist.addError}
          onDismissAddError={watchlist.clearAddError}
        />
        {watchlist.removeError && (
          <p className="watchlist-search__error" role="alert">
            Could not remove the feed: {watchlist.removeError}
            <button type="button" onClick={watchlist.clearRemoveError}>
              dismiss
            </button>
          </p>
        )}
        {watchlist.refreshError && (
          <p className="watchlist-search__error" role="alert">
            Could not refresh {watchlist.refreshError.symbol} on{' '}
            {providerLabel(watchlist.refreshError.provider)}: {watchlist.refreshError.message}
            <button type="button" onClick={watchlist.clearRefreshError}>
              dismiss
            </button>
          </p>
        )}
        {boardLoading ? (
          <LoadingSkeleton variant="table" rows={8} label="Connecting to market data" />
        ) : visibleRows.length > 0 ? (
          <MarketTable
            table={marketTable}
            rows={visibleRows}
            strategies={strategies}
            onRemove={handleRemove}
            onRefresh={watchlist.refresh}
            busyKey={watchlist.busyKey}
            refreshingKey={watchlist.refreshingKey}
            selectedId={selectedId}
            onSelect={(row) => setSelectedId(row.instrument.id)}
            caption="Watchlist instruments grouped by symbol, with name, class and listing venue followed by provider-level mark, day move, tick move, status and quote age. Select a provider row for observed change history."
          />
        ) : (
          <EmptyState message={boardEmptyMessage()} />
        )}
      </section>

      <CurveSection curves={curves} seedStatus={seedStatus} />

      {selectedRow && (
        <QuoteHistoryPanel row={selectedRow} onClose={() => setSelectedId(null)} />
      )}
    </section>
  )
}
