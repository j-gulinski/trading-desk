import { useEffect, useRef, useState } from 'react'
import StatusPill from '../status/StatusPill.jsx'
import { useMarketFeedContext } from '../../providers/feedContext.js'
import { useElapsedTime } from '../../hooks/useElapsedTime.js'
import { apiGet, apiPost } from '../../services/apiClient.js'
import { endpoints } from '../../services/endpoints.js'
import {
  buildOpenTradeIntent,
  newOpenTradeRequestId,
  tradeFormErrorsOf,
  tradeableInstrumentsOf,
} from '../../domain/tradeActions.js'
import { bookSummariesOf } from '../../domain/books.js'
import { describeApiError } from '../../domain/apiErrors.js'
import { isStale } from '../../domain/marketData.js'
import {
  formatAmount,
  formatNumber,
  formatShortId,
  formatUnitPrice,
} from '../../domain/formatting.js'

function FieldError({ id, message }) {
  if (!message) return null
  return (
    <span id={id} className="form-dialog__error" role="alert">
      {message}
    </span>
  )
}

export default function NewTradeDialog({ onClose }) {
  const dialogRef = useRef(null)
  const { instruments, seedStatus } = useMarketFeedContext()
  const { now } = useElapsedTime()

  const [books, setBooks] = useState(null)
  const [booksError, setBooksError] = useState(null)
  const [bookId, setBookId] = useState('')
  const [symbol, setSymbol] = useState('')
  const [side, setSide] = useState('BUY')
  const [quantityText, setQuantityText] = useState('')
  const [errors, setErrors] = useState({})
  const [pending, setPending] = useState(false)
  const [submitError, setSubmitError] = useState(null)
  const [ack, setAck] = useState(null)
  const [requestId, setRequestId] = useState(newOpenTradeRequestId)

  useEffect(() => {
    const dialog = dialogRef.current
    if (dialog && !dialog.open) dialog.showModal()
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    apiGet(endpoints.blotter.booksSummary, { signal: controller.signal })
      .then((data) => setBooks(bookSummariesOf(data)))
      .catch((err) => {
        if (controller.signal.aborted) return
        setBooks([])
        setBooksError(err?.message ?? 'Could not load books')
      })
    return () => controller.abort()
  }, [])

  const bookList = books ?? []
  const feedEmpty = Object.keys(instruments).length === 0
  const selectedBook = bookList.find((book) => book.id === bookId) ?? null
  const options = tradeableInstrumentsOf(instruments, selectedBook?.assetClass)
  const instrument = options.find((option) => option.symbol === symbol) ?? null
  const price = instrument?.value ?? null

  const trimmed = quantityText.trim()
  const quantity = trimmed === '' ? null : Number(trimmed)
  const estimatedNotional =
    Number.isFinite(quantity) && Number.isFinite(price) ? quantity * price : null

  function clearError(field) {
    setErrors((current) => {
      if (!current[field]) return current
      const next = { ...current }
      delete next[field]
      return next
    })
  }

  function selectBook(nextBookId) {
    setBookId(nextBookId)
    clearError('book')
    clearError('instrument')
    const nextBook = bookList.find((book) => book.id === nextBookId) ?? null
    const nextOptions = tradeableInstrumentsOf(instruments, nextBook?.assetClass)
    setSymbol(nextOptions.length === 1 ? nextOptions[0].symbol : '')
  }

  async function handleSubmit(event) {
    event.preventDefault()
    const nextErrors = tradeFormErrorsOf({ bookId, symbol, quantity, price })
    setErrors(nextErrors)
    if (Object.keys(nextErrors).length > 0) return

    setPending(true)
    setSubmitError(null)
    try {
      const intent = buildOpenTradeIntent({
        clientRequestId: requestId,
        bookId,
        assetClass: selectedBook.assetClass,
        symbol,
        side,
        quantity,
        price,
        currency: instrument.currency,
      })
      const accepted = await apiPost(endpoints.tradeAction.submit, intent)
      setAck({
        tradeId: accepted?.trade_id ?? null,
        side,
        quantity,
        symbol,
      })
      setRequestId(newOpenTradeRequestId())
    } catch (err) {
      setSubmitError(
        describeApiError(err, {
          service: 'Trade action service',
          outcome: 'the trade was not submitted.',
        }),
      )
    } finally {
      setPending(false)
    }
  }

  const valid = Object.keys(tradeFormErrorsOf({ bookId, symbol, quantity, price })).length === 0
  const submitLabel = valid
    ? `Submit ${side} ${formatNumber(quantity)} ${symbol}`
    : 'Submit trade intent'

  return (
    <dialog
      ref={dialogRef}
      className="form-dialog"
      aria-labelledby="new-trade-title"
      onClose={onClose}
      onClick={(event) => {
        if (event.target === event.currentTarget) event.currentTarget.close()
      }}
    >
      <article className="form-dialog__surface">
        <header className="form-dialog__head">
          <div>
            <span className="form-dialog__eyebrow">TRADE ACTION</span>
            <h2 id="new-trade-title">New trade</h2>
            <p>intent at displayed snapshot price</p>
          </div>
          <button
            type="button"
            className="form-dialog__close"
            aria-label="Close new trade form"
            autoFocus
            onClick={() => dialogRef.current?.close()}
          >
            ×
          </button>
        </header>

        <div className="form-dialog__body">
          <form className="form-dialog__form" onSubmit={handleSubmit} noValidate>
            <div className="form-dialog__row">
              <div className="form-dialog__field">
                <label className="form-dialog__label" htmlFor="new-trade-book">
                  BOOK
                </label>
                <select
                  id="new-trade-book"
                  className="form-dialog__select"
                  value={bookId}
                  aria-invalid={errors.book != null}
                  aria-describedby={errors.book ? 'new-trade-book-error' : undefined}
                  onChange={(event) => selectBook(event.target.value)}
                >
                  <option value="">
                    {books == null ? 'Loading books…' : 'Select book…'}
                  </option>
                  {bookList.map((book) => (
                    <option key={book.id} value={book.id}>
                      {book.name} · {book.assetClass}
                    </option>
                  ))}
                </select>
                <FieldError
                  id="new-trade-book-error"
                  message={booksError ? 'Books service unavailable — could not load books.' : errors.book}
                />
              </div>

              <div className="form-dialog__field">
                <label className="form-dialog__label" htmlFor="new-trade-instrument">
                  INSTRUMENT
                </label>
                <select
                  id="new-trade-instrument"
                  className="form-dialog__select"
                  value={symbol}
                  disabled={options.length === 0}
                  aria-invalid={errors.instrument != null}
                  aria-describedby={
                    errors.instrument ? 'new-trade-instrument-error' : undefined
                  }
                  onChange={(event) => {
                    setSymbol(event.target.value)
                    clearError('instrument')
                    clearError('price')
                  }}
                >
                  <option value="">
                    {options.length === 0 ? 'No instrument' : 'Select instrument…'}
                  </option>
                  {options.map((option) => (
                    <option key={option.id} value={option.symbol}>
                      {option.symbol}
                    </option>
                  ))}
                </select>
                <FieldError id="new-trade-instrument-error" message={errors.instrument} />
              </div>
            </div>

            {selectedBook != null && options.length === 0 && (
              <p className="form-dialog__note" role="status">
                {feedEmpty
                  ? seedStatus === 'error'
                    ? 'Market data unavailable — retrying.'
                    : 'Loading instruments…'
                  : `No ${selectedBook.assetClass} instrument has a live price to trade at.`}
              </p>
            )}

            <div className="form-dialog__field">
              <span className="form-dialog__label" id="new-trade-side-label">
                SIDE
              </span>
              <div
                className="form-dialog__side"
                role="group"
                aria-labelledby="new-trade-side-label"
              >
                {['BUY', 'SELL'].map((option) => (
                  <button
                    key={option}
                    type="button"
                    className="form-dialog__side-button"
                    aria-pressed={side === option}
                    onClick={() => setSide(option)}
                  >
                    {option === 'BUY' ? 'Buy' : 'Sell'}
                  </button>
                ))}
              </div>
            </div>

            <div className="form-dialog__field">
              <label className="form-dialog__label" htmlFor="new-trade-quantity">
                QUANTITY
              </label>
              <input
                id="new-trade-quantity"
                className="form-dialog__input"
                type="number"
                inputMode="numeric"
                min={1}
                step={1}
                value={quantityText}
                aria-invalid={errors.quantity != null}
                aria-describedby={errors.quantity ? 'new-trade-quantity-error' : undefined}
                onChange={(event) => {
                  setQuantityText(event.target.value)
                  clearError('quantity')
                }}
              />
              <FieldError id="new-trade-quantity-error" message={errors.quantity} />
            </div>

            <div className="form-dialog__info">
              <div className="form-dialog__info-row">
                <span className="form-dialog__info-label">LAST PRICE</span>
                <span className="form-dialog__info-value">
                  {formatUnitPrice(price, instrument?.assetClass)}
                  {instrument != null && (
                    <StatusPill
                      level={isStale(instrument, now) ? 'stale' : 'info'}
                      label={isStale(instrument, now) ? 'STALE' : 'LIVE'}
                      compact
                    />
                  )}
                </span>
              </div>
              <div className="form-dialog__info-row">
                <span className="form-dialog__info-label">
                  EST. NOTIONAL · QTY × LAST PRICE
                </span>
                <span className="form-dialog__info-value">
                  {formatAmount(estimatedNotional)}
                </span>
              </div>
              <div className="form-dialog__info-row">
                <span className="form-dialog__info-label">ASSET CLASS</span>
                <span className="form-dialog__info-value">
                  {selectedBook != null ? (
                    <span className="class-tag">
                      <span className="class-tag__dot" />
                      {selectedBook.assetClass}
                    </span>
                  ) : (
                    '—'
                  )}
                </span>
              </div>
            </div>
            <FieldError id="new-trade-price-error" message={errors.price} />

            <div className="form-dialog__summary" aria-live="polite">
              <span
                className={`form-dialog__summary-side form-dialog__summary-side--${side.toLowerCase()}`}
              >
                ● {side}
              </span>
              <span>
                {Number.isFinite(quantity) ? formatNumber(quantity) : '—'} ×{' '}
                {symbol || '—'}
              </span>
            </div>

            {submitError && (
              <div className="form-dialog__submit-error" role="alert">
                {submitError}
              </div>
            )}

            {ack && (
              <div className="form-dialog__ack" role="status">
                Accepted — {ack.side} {formatNumber(ack.quantity)} × {ack.symbol}
                {ack.tradeId != null && ` as trade ${formatShortId(ack.tradeId)}`}. It appears in
                Trades within a few seconds.
              </div>
            )}

            <button type="submit" className="form-dialog__submit" disabled={pending}>
              {pending ? 'Submitting…' : submitLabel}
            </button>
          </form>
        </div>
      </article>
    </dialog>
  )
}
