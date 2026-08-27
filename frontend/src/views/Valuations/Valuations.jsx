import { useState } from 'react'
import { useMarketFeedContext, useValuationFeedContext } from '../../providers/feedContext.js'
import { useElapsedTime } from '../../hooks/useElapsedTime.js'
import { usePolling } from '../../hooks/usePolling.js'
import { useTableState } from '../../hooks/useTableState.js'
import { STORAGE_KEYS } from '../../config/storage.js'
import {
  DEFAULT_VALUATION_SORT,
  MAX_RENDERED_ROWS,
  VALUATION_COLUMNS,
  VALUATION_CURRENCY_SORT_COLUMNS,
  VALUATION_FALLBACK_SORT,
} from '../../config/valuations.js'
import { DEFAULT_SORT_CURRENCY } from '../../config/marketData.js'
import {
  benchmarkDayChangeOf,
  benchmarkOf,
  bookOptionsOf,
  bookRisksOf,
  captureValuationSnapshot,
  sortValuationRows,
  summarizeValuations,
  valuationRowsOf,
} from '../../domain/valuations.js'
import { assetClassLabel } from '../../config/tradeActions.js'
import { BOOK_SUMMARY_POLL_INTERVAL_MS } from '../../config/books.js'
import { apiGet } from '../../services/apiClient.js'
import { endpoints } from '../../services/endpoints.js'
import { bookSummariesOf } from '../../domain/books.js'
import {
  reportedPortfolioSummaryOf,
} from '../../domain/portfolio.js'
import { countOptions } from '../../domain/filters.js'
import {
  formatAmount,
  formatClockTime,
  formatNumber,
  formatPercent,
  formatSignedAmount,
} from '../../domain/formatting.js'
import StatCard from '../../components/cards/StatCard.jsx'
import StreamHeader from '../../components/status/StreamHeader.jsx'
import FilterBar from '../../components/filters/FilterBar.jsx'
import EmptyState from '../../components/EmptyState.jsx'
import LoadingSkeleton from '../../components/LoadingSkeleton.jsx'
import ColumnPicker from '../../components/tables/ColumnPicker.jsx'
import SortCaptureStatus from '../../components/tables/SortCaptureStatus.jsx'
import ValuationTable from '../../components/valuations/ValuationTable.jsx'
import BookRiskCard from '../../components/valuations/BookRiskCard.jsx'
import FxReport from '../../components/fx/FxReport.jsx'
import { useFxRates } from '../../hooks/useFxRates.js'
import { useReportingCurrency } from '../../hooks/useReportingCurrency.js'
import { reportedTotalsOf } from '../../domain/fx.js'

const FX_COLUMNS = [
  { id: 'grossEntry', label: 'GROSS ENTRY', signed: false },
  { id: 'unrealized', label: 'UNREALIZED PNL', signed: true },
  { id: 'realized', label: 'REALIZED PNL', signed: true },
  { id: 'total', label: 'TOTAL PNL', signed: true },
]

function matchesSearch(row, search) {
  if (!search) return true
  const { valuation } = row
  return [valuation.tradeRef, valuation.bookName, valuation.symbol].some((field) =>
    field?.toLowerCase().includes(search),
  )
}

export default function Valuations() {
  const { valuations, bookRisk, status, seedStatus } = useValuationFeedContext()
  const { instruments, curves } = useMarketFeedContext()
  const { now } = useElapsedTime()
  const booksRequest = usePolling(
    ({ signal }) => apiGet(endpoints.blotter.booksSummary, { signal }),
    { intervalMs: BOOK_SUMMARY_POLL_INTERVAL_MS },
  )

  const [activeClass, setActiveClass] = useState(null)
  const [activeBook, setActiveBook] = useState(null)
  const [query, setQuery] = useState('')

  const openRows = valuationRowsOf(Object.values(valuations), now, instruments, curves).filter(
    (row) => !row.valuation.closed,
  )
  const summary = summarizeValuations(openRows)
  const [reportingCurrency, setReportingCurrency] = useReportingCurrency()
  const fx = useFxRates(reportingCurrency)
  const separateSortFx = useFxRates(
    reportingCurrency === DEFAULT_SORT_CURRENCY ? null : DEFAULT_SORT_CURRENCY,
  )
  const sortRates = reportingCurrency === DEFAULT_SORT_CURRENCY
    ? fx.rates
    : separateSortFx.rates
  const portfolio = reportedPortfolioSummaryOf(
    bookSummariesOf(booksRequest.data),
    fx.rates,
    reportingCurrency,
  )
  const currencySubtotals = portfolio.subtotals

  function reportedTotals(source) {
    return reportedTotalsOf(source, fx.rates, reportingCurrency, ['unrealized'])
  }

  const headline = portfolio.reported
  const currency = headline.currency
  const headlineTitle = headline.title
  const capitalHeadline = headline.values?.grossEntry ?? null
  const unrealizedHeadline = headline.values?.unrealized ?? null
  const realizedHeadline = headline.values?.realized ?? null
  const totalHeadline = headline.values?.total ?? null

  const portfolioMetric = bookRisk.PORTFOLIO
  const portfolioBook = portfolioMetric
    ? {
        name: 'PORTFOLIO',
        assetClass: 'ALL BOOKS',
        unrealizedReported: unrealizedHeadline,
        unrealizedCurrency: currency,
        unrealizedNote: headlineTitle,
        open: booksRequest.data == null ? summary.open : portfolio.openCount,
        live: summary.live,
        alpha: portfolioMetric.alpha,
        alphaWindowReturn: portfolioMetric.alphaWindowReturn,
        alphaWindowPnl: portfolioMetric.alphaWindowPnl,
        bookWindowReturn: portfolioMetric.bookWindowReturn,
        bookWindowPnl: portfolioMetric.bookWindowPnl,
        benchmarkWindowReturn: portfolioMetric.benchmarkWindowReturn,
        beta: portfolioMetric.beta,
        dollarBeta: portfolioMetric.dollarBeta,
        rSquared: portfolioMetric.rSquared,
        capitalBase: portfolioMetric.capitalBase,
        benchmark: portfolioMetric.benchmark,
        riskStatus: portfolioMetric.status,
        riskObservations: portfolioMetric.observations,
        riskMinimumObservations: portfolioMetric.minimumObservations,
        riskWindow: portfolioMetric.window,
      }
    : null

  const benchmark = benchmarkOf(bookRisk)
  const benchmarkDayChange = benchmarkDayChangeOf(instruments, benchmark)
  const benchmarkWindow =
    benchmark && Number.isFinite(benchmark.windowReturn)
      ? `${formatPercent(benchmark.windowReturn * 100, 2)} over ${benchmark.observations} observations`
      : null
  const benchmarkNote = benchmark
    ? [
        `Benchmark: ${benchmark.symbol}`,
        Number.isFinite(benchmark.level) ? formatAmount(benchmark.level, 2) : null,
        Number.isFinite(benchmarkDayChange)
          ? `${formatPercent(benchmarkDayChange, 2)} vs previous close`
          : benchmarkWindow,
      ]
        .filter(Boolean)
        .join(' · ')
    : 'Benchmark: —'
  const benchmarkTitle =
    Number.isFinite(benchmarkDayChange) && benchmarkWindow
      ? `α/β window: ${benchmarkWindow}`
      : undefined

  const table = useTableState({
    columns: VALUATION_COLUMNS,
    storageKey: STORAGE_KEYS.valuationColumns,
    defaultSort: DEFAULT_VALUATION_SORT,
    fallbackSort: VALUATION_FALLBACK_SORT,
    captureSnapshot: (column) => captureValuationSnapshot(
      openRows,
      column,
      sortRates,
      VALUATION_CURRENCY_SORT_COLUMNS.has(column) ? DEFAULT_SORT_CURRENCY : null,
    ),
    hasRows: openRows.length > 0 && sortRates != null,
    isSortable: (column) => Boolean(column?.sortable) && (
      !VALUATION_CURRENCY_SORT_COLUMNS.has(column.id) || sortRates != null
    ),
  })
  const approximateSortCurrency = (
    VALUATION_CURRENCY_SORT_COLUMNS.has(table.sort.column) &&
    openRows.some((row) => row.valuation.currency !== DEFAULT_SORT_CURRENCY)
  ) ? DEFAULT_SORT_CURRENCY : null

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

  const books = bookRisksOf(openRows, bookRisk).map((book) => {
    const reported = reportedTotals({
      subtotals: book.subtotals, currency: book.currency, values: book,
    })
    return {
      ...book,
      unrealizedReported: reported.values?.unrealized ?? null,
      unrealizedCurrency: reported.currency,
      unrealizedNote: reported.title,
    }
  })
  const bookOptions = bookOptionsOf(openRows)

  let tableContent
  if (visibleRows.length > 0) {
    tableContent = (
      <ValuationTable
        table={table}
        rows={visibleRows}
        caption="Open valuations sorted by the selected column, capped at 100 rows"
        comparisonCurrency={approximateSortCurrency}
        sortDisabledReason={(column) => (
          VALUATION_CURRENCY_SORT_COLUMNS.has(column.id) && sortRates == null
            ? 'USD comparison rates are loading'
            : null
        )}
      />
    )
  } else if (openRows.length > 0) {
    tableContent = <EmptyState message="No valuations match these filters." />
  } else if (seedStatus === 'error') {
    tableContent = <EmptyState message="Could not load current valuations — retrying on reconnect." />
  } else if (seedStatus === 'loading' || status === 'CONNECTING') {
    tableContent = (
      <LoadingSkeleton variant="table" rows={8} label="Connecting to the valuation stream" />
    )
  } else if (status === 'RECONNECTING') {
    tableContent = <EmptyState message="Valuation stream unavailable — retrying." />
  } else {
    tableContent = <EmptyState message="No valued open positions are available right now." />
  }

  return (
    <section className="page">
      <StreamHeader
        title="LIVE VALUATIONS"
        note={`${formatNumber(summary.open)} valued open positions · as of ${formatClockTime(summary.lastUpdateMs)}`}
        status={status}
        stream="PRICING"
      />

      <div className="valuation-summary">
        <StatCard
          label={`OPEN GROSS ENTRY VALUE · ${currency}`}
          value={capitalHeadline == null ? '—' : formatAmount(capitalHeadline)}
          sub={`${portfolio.openCount} open positions`}
          title={headlineTitle}
        />
        {portfolio.closedCount > 0 && (
          <StatCard
            label={`REALIZED PNL · ${currency}`}
            value={realizedHeadline == null ? '—' : formatSignedAmount(realizedHeadline)}
            sub={`${portfolio.closedCount} closed positions`}
            tone={
              realizedHeadline == null
                ? 'default'
                : realizedHeadline >= 0 ? 'pos' : 'neg'
            }
            title={headlineTitle}
          />
        )}
        <StatCard
          label={`TOTAL PNL · ${currency}`}
          value={totalHeadline == null ? '—' : formatSignedAmount(totalHeadline)}
          sub="realized + unrealized"
          tone={
            totalHeadline == null
              ? 'default'
              : totalHeadline >= 0 ? 'pos' : 'neg'
          }
          title={headlineTitle}
        />
        <StatCard
          label={`UNREALIZED PNL · ${currency}`}
          value={unrealizedHeadline == null ? '—' : formatSignedAmount(unrealizedHeadline)}
          sub={`${summary.open} valued open positions · ${summary.books} books`}
          tone={
            unrealizedHeadline == null
              ? 'default'
              : unrealizedHeadline >= 0 ? 'pos' : 'neg'
          }
          title={headlineTitle}
        />
        <StatCard label="LIVE" value={summary.live} sub="valued now" tone="info" />
        {summary.marketClosed > 0 && (
          <StatCard
            label="MKT CLOSED"
            value={summary.marketClosed}
            sub="marked at the close"
          />
        )}
        <StatCard
          label="STALE"
          value={summary.stale}
          sub="past the feed window"
          tone={summary.stale > 0 ? 'warn' : 'default'}
        />
      </div>

      {currencySubtotals.length > 0 && (
        <section className="valuation-section" aria-labelledby="fx-report-title">
          <div className="valuation-section__head">
            <div>
              <h2 id="fx-report-title">Portfolio by currency</h2>
              <p>Subtotals by settlement currency</p>
            </div>
            <span>{currencySubtotals.length} settlement {currencySubtotals.length === 1 ? 'currency' : 'currencies'}</span>
          </div>
          <FxReport
            columns={portfolio.closedCount > 0
              ? FX_COLUMNS
              : FX_COLUMNS.filter((column) => ['grossEntry', 'unrealized'].includes(column.id))}
            subtotals={currencySubtotals}
            reportingCurrency={reportingCurrency}
            onReportingCurrencyChange={setReportingCurrency}
            fx={fx}
          />
        </section>
      )}

      <section className="valuation-section" aria-labelledby="book-risk-title">
        <div className="valuation-section__head">
          <div>
            <h2 id="book-risk-title">Alpha / beta by book</h2>
            <p title={benchmarkTitle}>{benchmarkNote}</p>
          </div>
          <span>{books.length} books with open valuations</span>
        </div>
        {books.length > 0 ? (
          <div className="book-grid">
            {portfolioBook && <BookRiskCard key="portfolio" book={portfolioBook} />}
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
            <h2 id="valuation-table-title">Open positions</h2>
            <p>Sorted by the selected column · showing up to 100 rows</p>
          </div>
          <span>
            {hiddenRowCount > 0 ? `${visibleRows.length} of ${matchingRows.length}` : visibleRows.length} rows
          </span>
        </div>

        <FilterBar
          label="CLASS"
          ariaLabel="Filter valuations by asset class"
          options={countOptions(openRows, (row) => row.valuation.assetClass, assetClassLabel)}
          value={activeClass}
          onChange={selectClass}
          search={{
            label: 'TRADE',
            value: query,
            onChange: setQuery,
            placeholder: 'Search trade, book or instrument…',
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

        <SortCaptureStatus
          sort={table.sort}
          approximateCurrency={approximateSortCurrency}
        />
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
