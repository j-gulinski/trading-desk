import { useState } from 'react'
import { usePolling } from '../../hooks/usePolling.js'
import { useElapsedTime } from '../../hooks/useElapsedTime.js'
import { useValuationFeedContext } from '../../providers/feedContext.js'
import { apiGet } from '../../services/apiClient.js'
import { endpoints } from '../../services/endpoints.js'
import { BOOK_SUMMARY_POLL_INTERVAL_MS } from '../../config/books.js'
import { bookPositionsOf, bookSummariesOf, summarizeBooks } from '../../domain/books.js'
import { positionsOf, valuationRowsOf } from '../../domain/valuations.js'
import { countOptions } from '../../domain/filters.js'
import { formatNumber } from '../../domain/formatting.js'
import EmptyState from '../../components/EmptyState.jsx'
import FilterBar from '../../components/filters/FilterBar.jsx'
import BookCard from '../../components/books/BookCard.jsx'
import BookFormDialog from '../../components/books/BookFormDialog.jsx'

export default function Books() {
  const summary = usePolling(
    ({ signal }) => apiGet(endpoints.blotter.booksSummary, { signal }),
    { intervalMs: BOOK_SUMMARY_POLL_INTERVAL_MS },
  )
  const { valuations } = useValuationFeedContext()
  const { now } = useElapsedTime()

  const [expandedId, setExpandedId] = useState(null)
  const [dialog, setDialog] = useState(null)
  const [activeClass, setActiveClass] = useState(null)
  const [query, setQuery] = useState('')

  const allBooks = bookSummariesOf(summary.data)
  const totals = summarizeBooks(allBooks)
  const search = query.trim().toLowerCase()
  const books = allBooks.filter(
    (book) =>
      (!activeClass || book.assetClass === activeClass) &&
      (!search || book.name.toLowerCase().includes(search)),
  )
  const positions =
    expandedId == null
      ? []
      : bookPositionsOf(
          positionsOf(valuationRowsOf(Object.values(valuations), now)),
          expandedId,
        )

  const unavailable = summary.error != null && summary.data == null

  let content
  if (summary.loading) {
    content = <EmptyState message="Loading books…" />
  } else if (unavailable) {
    content = (
      <EmptyState message="Blotter service unavailable — retrying." />
    )
  } else if (allBooks.length === 0) {
    content = <EmptyState message="No books yet — create the first one." />
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
            positions={expandedId === book.id ? positions : []}
            onToggleExpand={() =>
              setExpandedId((current) => (current === book.id ? null : book.id))
            }
            onEdit={() => setDialog({ type: 'edit', bookId: book.id })}
          />
        ))}
      </div>
    )
  }

  return (
    <section className="page">
      <div className="books-header">
        <span className="books-header__meta">
          {formatNumber(totals.books)} books · {formatNumber(totals.openPositions)} open
          positions
        </span>
        <button
          type="button"
          className="books-button books-button--accent"
          onClick={() => setDialog({ type: 'create' })}
        >
          + Create book
        </button>
      </div>

      <FilterBar
        label="CLASS"
        ariaLabel="Filter books by asset class"
        options={countOptions(allBooks, (book) => book.assetClass)}
        value={activeClass}
        onChange={setActiveClass}
        search={{
          label: 'BOOK',
          value: query,
          onChange: setQuery,
          placeholder: 'Search book name…',
        }}
      />

      {summary.error != null && summary.data != null && (
        <div className="blotter-notice" role="status">
          Book list refresh failed — showing the last available data.
        </div>
      )}

      {content}

      {(dialog?.type === 'create' || dialog?.type === 'edit') && (
        <BookFormDialog
          bookId={dialog.type === 'edit' ? dialog.bookId : null}
          onSaved={summary.refetch}
          onClose={() => setDialog(null)}
        />
      )}

    </section>
  )
}
