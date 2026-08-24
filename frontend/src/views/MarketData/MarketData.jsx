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
import { formatMarketSymbol } from '../../domain/marketFormat.js'
import { countOptions } from '../../domain/filters.js'
import { formatElapsedTime, formatNumber } from '../../domain/formatting.js'
import StatCard from '../../components/cards/StatCard.jsx'
import StreamHeader from '../../components/status/StreamHeader.jsx'
import FilterBar from '../../components/filters/FilterBar.jsx'
import { STORAGE_KEYS } from '../../config/storage.js'
import EmptyState from '../../components/EmptyState.jsx'
import ColumnPicker from '../../components/tables/ColumnPicker.jsx'
import MarketTable from '../../components/marketdata/MarketTable.jsx'
import WatchlistSearch from '../../components/marketdata/WatchlistSearch.jsx'
import ProviderStrategyStrip from '../../components/marketdata/ProviderStrategyStrip.jsx'
import MarketBenchmark from '../../components/marketdata/MarketBenchmark.jsx'
import OfficialRates from '../../components/marketdata/OfficialRates.jsx'
import CurveSection from '../../components/marketdata/CurveSection.jsx'
import QuoteHistoryPanel from '../../components/marketdata/QuoteHistoryPanel.jsx'
import { providerLabel } from '../../config/providers.js'

function matchesSearch(row, search) {
  if (!search) return true
  return (
    row.instrument.symbol.toLowerCase().includes(search) ||
    formatMarketSymbol(row.instrument).toLowerCase().includes(search)
  )
}

function sortGroupedRows(rows, direction) {
  const symbolDirection = direction === 'desc' ? -1 : 1
  return [...rows].sort((left, right) => {
    const symbol = left.instrument.symbol.localeCompare(right.instrument.symbol)
    if (symbol !== 0) return symbol * symbolDirection
    const provider = left.instrument.provider.localeCompare(right.instrument.provider)
    return provider || left.instrument.id.localeCompare(right.instrument.id)
  })
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
    marketTable.sort.direction,
  )
  const visibleSymbols = new Set(visibleRows.map((row) => row.instrument.symbol)).size

  const summary = summarizeFeed(quoteRows.map((row) => row.instrument), now)
  const symbolRows = Array.from(
    new Map(quoteRows.map((row) => [row.instrument.symbol, row])).values(),
  )
  const providerOptions = countOptions(quoteRows, (row) => row.instrument.provider)
    .map((option) => ({ ...option, label: providerLabel(option.value) }))

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
        options={countOptions(symbolRows, (row) => row.instrument.assetClass)}
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
            <p>Provider feeds grouped by symbol</p>
          </div>
          <div className="market-section__actions">
            <span>Select a row for observed history</span>
            <span>{visibleSymbols} symbols · {visibleRows.length} feeds</span>
          </div>
        </div>
        <ProviderStrategyStrip providers={providersPoll.data} />
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
        {visibleRows.length > 0 ? (
          <MarketTable
            table={marketTable}
            rows={visibleRows}
            strategies={strategies}
            onRemove={handleRemove}
            busyKey={watchlist.busyKey}
            selectedId={selectedId}
            onSelect={(row) => setSelectedId(row.instrument.id)}
            caption="Watchlist symbols with provider subrows for normalized mark, last-tick move, daily move, freshness, and quote time. Select a provider row for observed change history."
          />
        ) : (
          <EmptyState message={boardEmptyMessage()} />
        )}
      </section>

      <CurveSection curves={curves} />

      {selectedRow && (
        <QuoteHistoryPanel row={selectedRow} onClose={() => setSelectedId(null)} />
      )}
    </section>
  )
}
