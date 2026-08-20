import { useEffect, useMemo, useState } from 'react'
import { useMarketFeedContext, useValuationFeedContext } from '../../providers/feedContext.js'
import { useElapsedTime } from '../../hooks/useElapsedTime.js'
import { STORAGE_KEYS } from '../../config/storage.js'
import { usePolling } from '../../hooks/usePolling.js'
import { useTableState } from '../../hooks/useTableState.js'
import { apiGet } from '../../services/apiClient.js'
import { endpoints } from '../../services/endpoints.js'
import {
  BLOTTER_POLL_INTERVAL_MS,
  DEFAULT_TRADE_COLUMNS,
  DEFAULT_TRADE_SORT,
  TRADE_COLUMNS,
  TRADE_FALLBACK_SORT,
  TRADE_HISTORY_FETCH_LIMIT,
  TRADE_PAGE_SIZE,
} from '../../config/trades.js'
import {
  bookNamesOf,
  booksFromSummary,
  captureTradeSnapshot,
  closedTradeCountOf,
  matchesTradeFilters,
  sortTradeRows,
  summarizeTradeRows,
  tradeBookOptionsOf,
  tradeRowsOf,
  tradesFromSnapshot,
} from '../../domain/trades.js'
import { countOptions } from '../../domain/filters.js'
import { formatClockTime, formatNumber } from '../../domain/formatting.js'
import StreamHeader from '../../components/status/StreamHeader.jsx'
import FilterChipGroup from '../../components/filters/FilterChipGroup.jsx'
import ColumnPicker from '../../components/tables/ColumnPicker.jsx'
import SortCaptureStatus from '../../components/tables/SortCaptureStatus.jsx'
import EmptyState from '../../components/EmptyState.jsx'
import TradeStatusTabs from '../../components/trades/TradeStatusTabs.jsx'
import TradeTable from '../../components/trades/TradeTable.jsx'
import TradeDetail from './TradeDetail.jsx'
import { PANEL_ID, usePanelCoordinator } from '../../layout/panelContext.js'

const INITIAL_FILTERS = { lifecycle: 'BOTH', book: null, assetClass: null, query: '' }

const CLEARED_BY = {
  lifecycle: { assetClass: null },
  book: { assetClass: null },
  assetClass: { book: null },
}

function emptyTableMessage({ snapshot, rows, lifecycleRows, lifecycle }) {
  if (snapshot.loading && snapshot.data == null) return 'Loading the operational blotter…'
  if (snapshot.error && snapshot.data == null) return 'Blotter service unavailable — retrying.'
  if (rows.length === 0) return 'No trades have been recorded yet.'
  if (lifecycle === 'BOTH') return `No open or closed trades.`
  if (lifecycleRows.length === 0) return `No ${lifecycle.toLowerCase()} trades.`
  return 'No trades match these filters.'
}

export default function Trades() {
  const { valuations, status, seedStatus } = useValuationFeedContext()
  const { instruments } = useMarketFeedContext()
  const { activePanel, openPanel, closePanel } = usePanelCoordinator()
  const { now } = useElapsedTime()
  const snapshot = usePolling(
    async ({ signal }) => {
      return apiGet(
        endpoints.blotter.tradesOverview({ limit: TRADE_HISTORY_FETCH_LIMIT }),
        { signal },
      )
    },
    { intervalMs: BLOTTER_POLL_INTERVAL_MS },
  )

  const [filters, setFilters] = useState(INITIAL_FILTERS)
  const [selectedTradeId, setSelectedTradeId] = useState(null)
  const [page, setPage] = useState(0)
  const { lifecycle, query } = filters

  useEffect(() => {
    if (selectedTradeId != null && activePanel !== PANEL_ID.tradeDetail) setSelectedTradeId(null)
  }, [activePanel, selectedTradeId])

  function selectTrade(tradeId) {
    setSelectedTradeId(tradeId)
    openPanel(PANEL_ID.tradeDetail)
  }

  function closeTradeDetail() {
    setSelectedTradeId(null)
    closePanel(PANEL_ID.tradeDetail)
  }

  function updateFilters(patch) {
    const [changed] = Object.keys(patch)
    setFilters((current) => ({ ...current, ...CLEARED_BY[changed], ...patch }))
    setPage(0)
  }

  const books = useMemo(
    () => booksFromSummary(snapshot.data?.books),
    [snapshot.data?.books],
  )
  const bookNames = useMemo(() => bookNamesOf(books), [books])
  const trades = useMemo(
    () => tradesFromSnapshot(snapshot.data?.trades, bookNames),
    [snapshot.data?.trades, bookNames],
  )
  const rows = tradeRowsOf(trades, valuations, now, instruments)
  const summary = summarizeTradeRows(rows)
  const isBothLifecycles = lifecycle === 'BOTH'
  const lifecycleRows = isBothLifecycles ? rows : rows.filter((row) => row.lifecycle === lifecycle)
  const lifecycleLabel = isBothLifecycles ? 'all' : lifecycle.toLowerCase()

  const table = useTableState({
    columns: TRADE_COLUMNS,
    storageKey: STORAGE_KEYS.tradeColumns,
    defaultVisibleColumns: DEFAULT_TRADE_COLUMNS,
    defaultSort: DEFAULT_TRADE_SORT,
    fallbackSort: TRADE_FALLBACK_SORT,
    captureSnapshot: (column) => captureTradeSnapshot(rows, column),
    hasRows: rows.length > 0,
  })

  const search = query.trim().toLowerCase()
  const matchingRows = sortTradeRows(
    lifecycleRows.filter((row) =>
      matchesTradeFilters(row, { book: filters.book, assetClass: filters.assetClass, search }),
    ),
    table.sort,
  )
  const pageCount = Math.max(1, Math.ceil(matchingRows.length / TRADE_PAGE_SIZE))
  const currentPage = Math.min(page, pageCount - 1)
  const pageStart = currentPage * TRADE_PAGE_SIZE
  const visibleRows = matchingRows.slice(pageStart, pageStart + TRADE_PAGE_SIZE)
  const selectedRow = rows.find((row) => row.trade.id === selectedTradeId) ?? null
  const bookOptions = tradeBookOptionsOf(lifecycleRows)
  const classOptions = countOptions(lifecycleRows, (row) => row.trade.assetClass)
  const closedTotal = Math.max(closedTradeCountOf(books), summary.closed)
  const closedWindowed = summary.closed < closedTotal

  const bothCount = formatNumber(summary.open + closedTotal)

  const tableContent =
    visibleRows.length > 0 ? (
      <TradeTable
        table={table}
        rows={visibleRows}
        selectedTradeId={selectedTradeId}
        onSelect={selectTrade}
        caption={`${lifecycleLabel} trades with live valuation and PnL`}
      />
    ) : (
      <EmptyState message={emptyTableMessage({ snapshot, rows, lifecycleRows, lifecycle })} />
    )

  const streamNote =
    snapshot.lastUpdated == null
      ? 'loading blotter snapshot'
      : `${formatNumber(summary.open)} open · ${formatNumber(closedTotal)} closed · snapshot ${formatClockTime(snapshot.lastUpdated)}`

  return (
    <section className="page">
      <StreamHeader
        title="BLOTTER · LIVE VALUATIONS"
        note={streamNote}
        status={status}
        stream="PRICING"
      />

      {snapshot.error && snapshot.data != null && (
        <div className="blotter-notice" role="status">
          Blotter refresh failed — showing the last successful snapshot while retrying.
        </div>
      )}
      {seedStatus === 'error' && (
        <div className="blotter-notice" role="status">
          Pricing seed unavailable — Blotter values remain visible and the live stream is retrying.
        </div>
      )}

      <div className="blotter-toolbar">
        <label className="blotter-toolbar__select-field">
          <select
            className="filter-bar__select blotter-toolbar__select"
            aria-label="Filter trades by book"
            value={filters.book ?? ''}
            onChange={(event) => updateFilters({ book: event.target.value || null })}
          >
            <option value="">All books</option>
            {bookOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label} ({option.count})
              </option>
            ))}
          </select>
        </label>

        <TradeStatusTabs
          value={lifecycle}
          openCount={formatNumber(summary.open)}
          closedCount={formatNumber(closedTotal)}
          totalCount={bothCount}
          onChange={(value) => updateFilters({ lifecycle: value })}
        />

        <span className="blotter-toolbar__divider" aria-hidden="true" />

        <FilterChipGroup
          className="blotter-toolbar__classes"
          ariaLabel={`Filter ${lifecycleLabel} trades by asset class`}
          options={classOptions}
          value={filters.assetClass}
          onChange={(value) => updateFilters({ assetClass: value })}
        />

        <label className="blotter-toolbar__search-field">
          <input
            className="filter-bar__search blotter-toolbar__search"
            type="search"
            aria-label="Search trades"
            placeholder="Search trade, book or symbol…"
            value={query}
            onChange={(event) => updateFilters({ query: event.target.value })}
          />
        </label>
      </div>

      <div className="blotter-meta">
        <span>
          {formatNumber(matchingRows.length)} {matchingRows.length === 1 ? 'trade' : 'trades'}
          {lifecycle === 'CLOSED' && closedWindowed && (
            <> · newest {formatNumber(summary.closed)} of {formatNumber(closedTotal)} loaded</>
          )}
        </span>
        <span>select a row for valuation history &amp; audit</span>
      </div>

        <section className="blotter-table-panel" aria-labelledby="blotter-table-title">
          <header className="blotter-table-panel__head">
          <span id="blotter-table-title">{lifecycleLabel.toUpperCase()} TRADES</span>
          <ColumnPicker
            ariaLabel="Trade columns"
            columns={TRADE_COLUMNS}
            visibleColumns={table.visibleColumns}
            onToggle={table.toggleColumn}
            onReorder={table.reorderColumn}
            onReset={table.resetColumns}
          />
        </header>

        <div className="blotter-table-panel__sort">
          <SortCaptureStatus sort={table.sort} />
          {pageCount > 1 && (
            <div className="blotter-pager" role="navigation" aria-label="Trade pages">
              <button
                type="button"
                className="blotter-pager__button"
                onClick={() => setPage(currentPage - 1)}
                disabled={currentPage === 0}
              >
                Prev
              </button>
              <span className="blotter-pager__status">
                Page {currentPage + 1} of {pageCount}
              </span>
              <button
                type="button"
                className="blotter-pager__button"
                onClick={() => setPage(currentPage + 1)}
                disabled={currentPage >= pageCount - 1}
              >
                Next
              </button>
            </div>
          )}
        </div>
        {tableContent}
      </section>

      {activePanel === PANEL_ID.tradeDetail && selectedRow && (
        <TradeDetail
          key={selectedRow.trade.id}
          row={selectedRow}
          bookNames={bookNames}
          onClose={closeTradeDetail}
        />
      )}
    </section>
  )
}
