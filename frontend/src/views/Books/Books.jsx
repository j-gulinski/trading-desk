import { useEffect, useState } from 'react'
import { usePolling } from '../../hooks/usePolling.js'
import { useElapsedTime } from '../../hooks/useElapsedTime.js'
import { apiDelete, apiGet } from '../../services/apiClient.js'
import { endpoints } from '../../services/endpoints.js'
import { BOOK_SUMMARY_POLL_INTERVAL_MS } from '../../config/books.js'
import {
  bookPositionsOf,
  bookSummariesOf,
  moveTargetsOf,
  summarizeBooks,
} from '../../domain/books.js'
import { describeApiError } from '../../domain/apiErrors.js'
import { countOptions } from '../../domain/filters.js'
import { formatNumber } from '../../domain/formatting.js'
import EmptyState from '../../components/EmptyState.jsx'
import ConfirmPanel from '../../components/panel/ConfirmPanel.jsx'
import FilterBar from '../../components/filters/FilterBar.jsx'
import BookCard from '../../components/books/BookCard.jsx'
import BookFormPanel from '../../components/books/BookFormPanel.jsx'
import MoveTradesPanel from '../../components/books/MoveTradesPanel.jsx'
import FxReport from '../../components/fx/FxReport.jsx'
import { useFxRates } from '../../hooks/useFxRates.js'
import { useReportingCurrency } from '../../hooks/useReportingCurrency.js'
import { currencySubtotalsOf } from '../../domain/fx.js'

const FX_COLUMNS = [
  { id: 'unrealized', label: 'UNREALIZED', signed: true },
  { id: 'realized', label: 'REALIZED', signed: true },
]
import { PANEL_ID, usePanelCoordinator } from '../../layout/panelContext.js'

function describeDeleteError(error) {
  if (error?.status === 409) {
    const open = Number(error.body?.active_trades)
    return Number.isFinite(open)
      ? `Refused — this book still has ${formatNumber(open)} open ${
          open === 1 ? 'position' : 'positions'
        }.`
      : 'Refused — this book still has open positions.'
  }
  if (error?.status === 503 && error.body?.error === 'open trades could not be verified') {
    return 'Blotter service unavailable — open positions could not be checked, so nothing was deleted.'
  }
  return describeApiError(error, {
    service: 'Books service',
    outcome: 'the book was not deleted.',
  })
}

export default function Books() {
  const summary = usePolling(
    ({ signal }) => apiGet(endpoints.blotter.booksSummary, { signal }),
    { intervalMs: BOOK_SUMMARY_POLL_INTERVAL_MS },
  )
  const { now } = useElapsedTime()
  const { activePanel, openPanel, closePanel: closeActivePanel } = usePanelCoordinator()

  const [expandedId, setExpandedId] = useState(null)
  const [panel, setPanel] = useState(null)
  const [notice, setNotice] = useState(null)
  const [activeClass, setActiveClass] = useState(null)
  const [query, setQuery] = useState('')
  const [includeDeactivated, setIncludeDeactivated] = useState(false)

  const allBooks = bookSummariesOf(summary.data)
  const roster = allBooks.filter((book) => book.isActive || includeDeactivated)
  const totals = summarizeBooks(roster)
  const [reportingCurrency, setReportingCurrency] = useReportingCurrency()
  const fx = useFxRates(reportingCurrency)
  const currencySubtotals = currencySubtotalsOf(
    roster.filter((book) => book.currency != null),
    (book) => book.currency,
    (book) => ({
      unrealized: book.unrealizedPnl ?? 0,
      realized: book.realizedPnl ?? 0,
    }),
  )
  const deactivatedCount = allBooks.filter((book) => !book.isActive).length
  const search = query.trim().toLowerCase()
  const books = roster.filter(
    (book) =>
      (!activeClass || book.assetClass === activeClass) &&
      (!search || book.name.toLowerCase().includes(search)),
  )
  const target = panel?.bookId ? allBooks.find((book) => book.id === panel.bookId) : null
  const unavailable = summary.error != null && summary.data == null

  function openAction(type, book) {
    setNotice(null)
    setPanel({ type, bookId: book.id })
    openPanel(PANEL_ID.books)
  }

  function closeBooksPanel() {
    setPanel(null)
    closeActivePanel(PANEL_ID.books)
  }

  useEffect(() => {
    if (panel != null && activePanel !== PANEL_ID.books) setPanel(null)
  }, [activePanel, panel])

  function acknowledge(message) {
    setNotice(message)
    summary.refetch()
  }

  let content
  if (summary.loading) {
    content = <EmptyState message="Loading books…" />
  } else if (unavailable) {
    content = (
      <EmptyState message="Blotter service unavailable — retrying." />
    )
  } else if (allBooks.length === 0) {
    content = <EmptyState message="No books yet — create the first one." />
  } else if (roster.length === 0) {
    content = (
      <EmptyState message="Every book is deactivated — tick “Include deactivated” to see them." />
    )
  } else if (books.length === 0) {
    content = <EmptyState message="No books match these filters." />
  } else {
    content = (
      <div className="books-grid">
        {books.map((book) => (
          <BookCard
            key={book.id}
            book={book}
            expanded={expandedId === book.id}
            positions={expandedId === book.id ? bookPositionsOf(book, now) : []}
            onToggleExpand={() =>
              setExpandedId((current) => (current === book.id ? null : book.id))
            }
            onEdit={() => openAction('edit', book)}
            onMove={() => openAction('move', book)}
            onDelete={() => openAction('delete', book)}
          />
        ))}
      </div>
    )
  }

  return (
    <section className="page">
      <div className="books-header">
        <span className="books-header__meta">
          {formatNumber(totals.books)} books 
          {deactivatedCount > 0 && !includeDeactivated
            ? ` · ${formatNumber(deactivatedCount)} deactivated hidden`
            : ''} · {formatNumber(totals.openPositions)} open positions
        </span>
        <button
          type="button"
          className="books-button books-button--accent"
          data-panel-trigger
          onClick={() => {
            setNotice(null)
            setPanel({ type: 'create' })
            openPanel(PANEL_ID.books)
          }}
        >
          + Create book
        </button>
      </div>

      <FilterBar
        label="CLASS"
        ariaLabel="Filter books by asset class"
        options={countOptions(roster, (book) => book.assetClass)}
        value={activeClass}
        onChange={setActiveClass}
        search={{
          label: 'BOOK',
          value: query,
          onChange: setQuery,
          placeholder: 'Search book name…',
        }}
      >
        <label className="filter-bar__check">
          <input
            type="checkbox"
            checked={includeDeactivated}
            onChange={(event) => setIncludeDeactivated(event.target.checked)}
          />
          Include deactivated
        </label>
      </FilterBar>

      {currencySubtotals.length > 0 && (
        <FxReport
          columns={FX_COLUMNS}
          subtotals={currencySubtotals}
          reportingCurrency={reportingCurrency}
          onReportingCurrencyChange={setReportingCurrency}
          fx={fx}
        />
      )}

      {summary.error != null && summary.data != null && (
        <div className="blotter-notice" role="status">
          Book list refresh failed — showing the last available data.
        </div>
      )}

      {notice && (
        <div className="blotter-notice blotter-notice--ok" role="status">
          {notice}
        </div>
      )}

      {content}

      {activePanel === PANEL_ID.books && (panel?.type === 'create' || panel?.type === 'edit') && (
        <BookFormPanel
          key={`${panel.type}:${panel.bookId ?? 'new'}`}
          bookId={panel.type === 'edit' ? panel.bookId : null}
          onSaved={summary.refetch}
          onClose={closeBooksPanel}
        />
      )}

      {activePanel === PANEL_ID.books && panel?.type === 'move' && target != null && (
        <MoveTradesPanel
          book={target}
          targets={moveTargetsOf(allBooks, target)}
          onAccepted={acknowledge}
          onClose={closeBooksPanel}
        />
      )}

      {activePanel === PANEL_ID.books && panel?.type === 'delete' && target != null && (
        <ConfirmPanel
          eyebrow="BOOKS"
          title="Delete book"
          subtitle={target.name}
          message={
            target.closedTrades > 0
              ? `Deactivates the book. ${formatNumber(target.closedTrades)} closed ${
                  target.closedTrades === 1 ? 'trade' : 'trades'
                } and audit history are retained.`
              : 'Deactivates the book. No further trades can be booked to it.'
          }
          confirmLabel="Delete book"
          onConfirm={async () => {
            await apiDelete(endpoints.books.book(target.id))
            acknowledge(`${target.name} deleted.`)
          }}
          describeError={describeDeleteError}
          onClose={closeBooksPanel}
        />
      )}
    </section>
  )
}
