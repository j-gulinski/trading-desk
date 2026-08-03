import { useState } from 'react'
import { useValuationFeedContext } from '../../providers/feedContext.js'
import { useElapsedTime } from '../../hooks/useElapsedTime.js'
import { useTableState } from '../../hooks/useTableState.js'
import {
  DEFAULT_VALUATION_SORT,
  MAX_RENDERED_ROWS,
  VALUATION_COLUMNS,
  VALUATION_COLUMNS_STORAGE_KEY,
  VALUATION_FALLBACK_SORT,
} from '../../config/valuations.js'
import {
  bookOptionsOf,
  bookRisksOf,
  captureValuationSnapshot,
  sortValuationRows,
  summarizeValuations,
  valuationRowsOf,
} from '../../domain/valuations.js'
import { countOptions } from '../../domain/filters.js'
import { formatClockTime, formatNumber, formatSignedAmount } from '../../domain/formatting.js'
import StatCard from '../../components/cards/StatCard.jsx'
import StreamHeader from '../../components/status/StreamHeader.jsx'
import FilterBar from '../../components/filters/FilterBar.jsx'
import EmptyState from '../../components/EmptyState.jsx'
import ColumnPicker from '../../components/tables/ColumnPicker.jsx'
import SortCaptureStatus from '../../components/tables/SortCaptureStatus.jsx'
import ValuationTable from '../../components/valuations/ValuationTable.jsx'
import BookRiskCard from '../../components/valuations/BookRiskCard.jsx'

function matchesSearch(row, search) {
  if (!search) return true
  const { valuation } = row
  return [valuation.tradeRef, valuation.bookName, valuation.symbol].some((field) =>
    field?.toLowerCase().includes(search),
  )
}

export default function Valuations() {
  const { valuations, status, seedStatus } = useValuationFeedContext()
  const { now } = useElapsedTime()

  const [activeClass, setActiveClass] = useState(null)
  const [activeBook, setActiveBook] = useState(null)
  const [query, setQuery] = useState('')

  const openRows = valuationRowsOf(Object.values(valuations), now).filter(
    (row) => !row.valuation.closed,
  )
  const summary = summarizeValuations(openRows)

  const table = useTableState({
    columns: VALUATION_COLUMNS,
    storageKey: VALUATION_COLUMNS_STORAGE_KEY,
    defaultSort: DEFAULT_VALUATION_SORT,
    fallbackSort: VALUATION_FALLBACK_SORT,
    captureSnapshot: (column) => captureValuationSnapshot(openRows, column),
    hasRows: openRows.length > 0,
  })

  function selectClass(value) {
    setActiveClass(value)
    setActiveBook(null)
  }

  function selectBook(value) {
    setActiveBook(value)
    setActiveClass(null)
  }

  const search = query.trim().toLowerCase()
  const matchingRows = sortValuationRows(
    openRows.filter(
      (row) =>
        (!activeClass || row.valuation.assetClass === activeClass) &&
        (!activeBook || row.valuation.bookId === activeBook) &&
        matchesSearch(row, search),
    ),
    table.sort,
  )
  const visibleRows = matchingRows.slice(0, MAX_RENDERED_ROWS)
  const hiddenRowCount = matchingRows.length - visibleRows.length

  const books = bookRisksOf(openRows)
  const bookOptions = bookOptionsOf(openRows)
  const currency = summary.currency ?? 'MIXED'

  let tableContent
  if (visibleRows.length > 0) {
    tableContent = (
      <ValuationTable
        table={table}
        rows={visibleRows}
        caption="Open positions ranked by return and unrealized PnL, capped at the top 100"
      />
    )
  } else if (openRows.length > 0) {
    tableContent = <EmptyState message="No valuations match these filters." />
  } else if (seedStatus === 'error') {
    tableContent = <EmptyState message="Could not load current valuations — retrying on reconnect." />
  } else if (seedStatus === 'loading' || status === 'CONNECTING') {
    tableContent = <EmptyState message="Connecting to the valuation stream…" />
  } else if (status === 'RECONNECTING') {
    tableContent = <EmptyState message="Valuation stream unavailable — retrying." />
  } else {
    tableContent = <EmptyState message="No open positions are being valued right now." />
  }

  return (
    <section className="page">
      <StreamHeader
        title="LIVE VALUATIONS"
        note={`${formatNumber(summary.open)} open positions · as of ${formatClockTime(summary.lastUpdateMs)}`}
        status={status}
        stream="PRICING"
      />

      <div className="valuation-summary">
        <StatCard
          label={`UNREALIZED PNL · ${currency}`}
          value={formatSignedAmount(summary.unrealized)}
          sub={`${summary.open} open positions · ${summary.books} books`}
          tone={summary.unrealized >= 0 ? 'pos' : 'neg'}
        />
        <StatCard label="LIVE" value={summary.live} sub="valued now" tone="info" />
        <StatCard
          label="STALE"
          value={summary.stale}
          sub="> 10s threshold"
          tone={summary.stale > 0 ? 'warn' : 'default'}
        />
      </div>

      <section className="valuation-section" aria-labelledby="book-risk-title">
        <div className="valuation-section__head">
          <div>
            <h2 id="book-risk-title">Alpha / beta by book</h2>
            <p>Book risk against the MARKET_INDEX benchmark</p>
          </div>
          <span>{books.length} books</span>
        </div>
        {books.length > 0 ? (
          <div className="book-grid">
            {books.map((book) => (
              <BookRiskCard key={book.id} book={book} />
            ))}
          </div>
        ) : (
          <EmptyState message="No book has a valuation yet." />
        )}
      </section>

      <section className="valuation-section" aria-labelledby="valuation-table-title">
        <div className="valuation-section__head">
          <div hidden={matchingRows.length === 0}>
            <h2 id="valuation-table-title">Top 100 open positions</h2>
            <p>Ranked by return or unrealized PnL — current signal for spotting alpha</p>
          </div>
          <span>
            {hiddenRowCount > 0 ? `${visibleRows.length} of ${matchingRows.length}` : visibleRows.length} rows
          </span>
        </div>

        <FilterBar
          label="CLASS"
          ariaLabel="Filter valuations by asset class"
          options={countOptions(openRows, (row) => row.valuation.assetClass)}
          value={activeClass}
          onChange={selectClass}
          search={{
            label: 'TRADE',
            value: query,
            onChange: setQuery,
            placeholder: 'Search trade, book or symbol…',
          }}
        >
          <label className="filter-bar__select-field">
            <span className="filter-bar__label">BOOK</span>
            <select
              className="filter-bar__select"
              aria-label="Filter valuations by book"
              value={activeBook ?? ''}
              onChange={(event) => selectBook(event.target.value || null)}
            >
              <option value="">All books</option>
              {bookOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label} ({option.count})
                </option>
              ))}
            </select>
          </label>

          <ColumnPicker
            ariaLabel="Valuation columns"
            columns={VALUATION_COLUMNS}
            visibleColumns={table.visibleColumns}
            onToggle={table.toggleColumn}
            onReorder={table.reorderColumn}
            onReset={table.resetColumns}
          />
        </FilterBar>

        <SortCaptureStatus sort={table.sort} />
        {hiddenRowCount > 0 && (
          <div className="table-sort-status" role="status">
            Showing the top {MAX_RENDERED_ROWS} by this sort · {hiddenRowCount} more match — filter
            or re-sort to change what is included
          </div>
        )}
        {tableContent}
      </section>
    </section>
  )
}
