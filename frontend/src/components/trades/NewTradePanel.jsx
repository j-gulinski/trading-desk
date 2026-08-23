import { useState } from 'react'
import SidePanel from '../panel/SidePanel.jsx'
import ProviderQuoteOption from './ProviderQuoteOption.jsx'
import { useMarketFeedContext } from '../../providers/feedContext.js'
import { useElapsedTime } from '../../hooks/useElapsedTime.js'
import { usePolling } from '../../hooks/usePolling.js'
import { apiGet, apiPost } from '../../services/apiClient.js'
import { endpoints } from '../../services/endpoints.js'
import {
  buildOpenTradeIntent,
  instrumentCatalogOf,
  isCurvePriced,
  newOpenTradeRequestId,
  providerQuotesOf,
  tradeFormErrorsOf,
  tradeableInstrumentsOf,
} from '../../domain/tradeActions.js'
import { providerLabel } from '../../config/providers.js'
import { bookSummariesOf } from '../../domain/books.js'
import { describeApiError } from '../../domain/apiErrors.js'
import { TICKET_OPTIONS_POLL_INTERVAL_MS } from '../../config/tradeActions.js'
import {
  formatAmount,
  formatDateTime,
  formatNumber,
  formatShortId,
  formatUnitPrice,
} from '../../domain/formatting.js'
import { unitLabelOf } from '../../domain/marketFormat.js'

function FieldError({ id, message }) {
  if (!message) return null
  return (
    <span id={id} className="panel-form__error" role="alert">
      {message}
    </span>
  )
}

export default function NewTradePanel({ onClose }) {
  const { instruments } = useMarketFeedContext()
  const { now } = useElapsedTime()
  const [bookId, setBookId] = useState('')
  const [symbol, setSymbol] = useState('')
  const [side, setSide] = useState('BUY')
  const [providerChoice, setProviderChoice] = useState('')
  const [quantityText, setQuantityText] = useState('')
  const [errors, setErrors] = useState({})
  const [pending, setPending] = useState(false)
  const [submitError, setSubmitError] = useState(null)
  const [ack, setAck] = useState(null)
  const [requestId, setRequestId] = useState(newOpenTradeRequestId)
  const booksRequest = usePolling(
    ({ signal }) => apiGet(endpoints.blotter.booksSummary, { signal }),
    { intervalMs: TICKET_OPTIONS_POLL_INTERVAL_MS },
  )
  const catalogRequest = usePolling(
    ({ signal }) => apiGet(endpoints.tradeAction.instruments, { signal }),
    { intervalMs: TICKET_OPTIONS_POLL_INTERVAL_MS },
  )
  const books = booksRequest.data == null ? null : bookSummariesOf(booksRequest.data)
  const catalog = catalogRequest.data == null ? null : instrumentCatalogOf(catalogRequest.data)

  const bookList = (books ?? []).filter((book) => book.isActive)
  const selectedBook = bookList.find((book) => book.id === bookId) ?? null
  const assetClass = selectedBook?.assetClass
  const curvePriced = isCurvePriced(assetClass)
  const options = curvePriced ? [] : tradeableInstrumentsOf(catalog, assetClass)
  const instrument = options.find((option) => option.symbol === symbol) ?? null

  const quotes = providerQuotesOf({ instrument, feed: instruments, side, now })
  const priced = quotes.filter((option) => Number.isFinite(option.price))
  const provider = providerChoice || (priced.length === 1 ? priced[0].provider : '')
  const quote = quotes.find((option) => option.provider === provider) ?? null

  const wholeUnits = assetClass === 'EQUITY'
  const unitLabel = symbol ? unitLabelOf({ symbol, assetClass }) : null
  const trimmed = quantityText.trim()
  const quantity = trimmed === '' ? null : Number(trimmed)
  const estimatedPositionValue =
    Number.isFinite(quantity) && quote?.price != null ? quantity * quote.price : null

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
    setProviderChoice('')
    setErrors({})
    const nextBook = bookList.find((book) => book.id === nextBookId) ?? null
    const nextOptions = isCurvePriced(nextBook?.assetClass)
      ? []
      : tradeableInstrumentsOf(catalog, nextBook?.assetClass)
    setSymbol(nextOptions.length === 1 ? nextOptions[0].symbol : '')
  }

  function selectProvider(nextProvider) {
    setProviderChoice(nextProvider)
    clearError('provider')
  }

  function formErrorsOf() {
    return tradeFormErrorsOf({ bookId, symbol, quantity, quote, assetClass })
  }

  async function handleSubmit(event) {
    event.preventDefault()
    const nextErrors = formErrorsOf()
    setErrors(nextErrors)
    if (Object.keys(nextErrors).length > 0) return

    setPending(true)
    setSubmitError(null)
    try {
      const intent = buildOpenTradeIntent({
        clientRequestId: requestId,
        bookId,
        assetClass,
        symbol,
        side,
        quantity,
        quote,
      })
      const accepted = await apiPost(endpoints.tradeAction.submit, intent)
      setAck({
        tradeId: accepted?.trade_id ?? null,
        side,
        quantity,
        symbol,
        price: quote.price,
        provider: quote.provider,
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

  const currentFormErrors = formErrorsOf()
  const valid = Object.keys(currentFormErrors).length === 0
  const providerError = errors.provider ?? (
    quote != null && !quote.tradeable ? currentFormErrors.provider : null
  )
  const submitLabel = valid
    ? `${side} ${formatNumber(quantity)} ${symbol} at ${formatUnitPrice(quote.price, assetClass)}`
    : 'Submit trade intent'

  if (ack) {
    return (
      <SidePanel
        eyebrow="TRADE ACTION"
        title="Trade submitted"
        subtitle="The order was accepted for processing"
        dismissOnOutsideClick={false}
        onClose={onClose}
      >
        <div className="panel-form__ack" role="status">
          <span>
            {ack.side} {formatNumber(ack.quantity)} × {ack.symbol} via{' '}
            {providerLabel(ack.provider)}
            {ack.tradeId != null && ` · trade ${formatShortId(ack.tradeId)}`}
          </span>
        </div>
        <div className="panel-form__actions">
          <button
            type="button"
            className="panel-form__cancel"
            onClick={() => {
              setAck(null)
              setQuantityText('')
              setSubmitError(null)
              setErrors({})
            }}
          >
            New trade
          </button>
          <button
            type="button"
            className="panel-form__submit"
            onClick={() => {
              window.location.hash = '/trades'
              onClose()
            }}
          >
            View in Trades
          </button>
        </div>
      </SidePanel>
    )
  }

  return (
    <SidePanel
      eyebrow="TRADE ACTION"
      title="New trade"
      subtitle="Compare quotes and choose a provider"
      dismissOnOutsideClick={false}
      onClose={onClose}
    >
      <form className="panel-form__form" onSubmit={handleSubmit} noValidate>
        <div className="panel-form__row">
          <div className="panel-form__field">
            <label className="panel-form__label" htmlFor="new-trade-book">BOOK</label>
            <select
              id="new-trade-book"
              className="panel-form__select"
              value={bookId}
              aria-invalid={errors.book != null}
              aria-describedby={errors.book ? 'new-trade-book-error' : undefined}
              onChange={(event) => selectBook(event.target.value)}
            >
              <option value="">{books == null ? 'Loading books…' : 'Select book…'}</option>
              {bookList.map((book) => (
                <option key={book.id} value={book.id}>{book.name} · {book.assetClass}</option>
              ))}
            </select>
            <FieldError
              id="new-trade-book-error"
              message={booksRequest.error ? 'Books service unavailable — could not load books.' : errors.book}
            />
          </div>

          <div className="panel-form__field">
            <label className="panel-form__label" htmlFor="new-trade-instrument">INSTRUMENT</label>
            <select
              id="new-trade-instrument"
              className="panel-form__select"
              value={symbol}
              disabled={options.length === 0}
              aria-invalid={errors.instrument != null}
              aria-describedby={errors.instrument ? 'new-trade-instrument-error' : undefined}
              onChange={(event) => {
                setSymbol(event.target.value)
                setProviderChoice('')
                clearError('instrument')
                clearError('provider')
              }}
            >
              <option value="">{options.length === 0 ? 'No instrument' : 'Select instrument…'}</option>
              {options.map((option) => (
                <option key={option.symbol} value={option.symbol}>{option.symbol}</option>
              ))}
            </select>
            <FieldError id="new-trade-instrument-error" message={errors.instrument} />
          </div>
        </div>

        {curvePriced && (
          <p className="panel-form__note" role="status">
            New {assetClass} trades are not available.
          </p>
        )}

        {selectedBook != null && !curvePriced && options.length === 0 && (
          <p className="panel-form__note" role="status">
            {catalog == null
              ? 'Loading tradeable instruments…'
              : catalogRequest.error
                ? 'Instrument list unavailable — retrying.'
                : `No ${selectedBook.assetClass} symbol is on the watchlist — add one in Market data.`}
          </p>
        )}

        <div className="panel-form__field">
          <span className="panel-form__label" id="new-trade-side-label">SIDE</span>
          <div className="panel-form__side" role="group" aria-labelledby="new-trade-side-label">
            {['BUY', 'SELL'].map((option) => (
              <button
                key={option}
                type="button"
                className="panel-form__side-button"
                aria-pressed={side === option}
                onClick={() => setSide(option)}
              >
                {option === 'BUY' ? 'Buy' : 'Sell'}
              </button>
            ))}
          </div>
        </div>

        {symbol !== '' && (
          <div className="panel-form__field">
            <span className="panel-form__label" id="new-trade-provider-label">
              MARKET DATA PROVIDER
            </span>
            <ul className="quote-options" aria-labelledby="new-trade-provider-label">
              {quotes.map((option) => (
                <ProviderQuoteOption
                  key={option.provider}
                  quote={option}
                  assetClass={assetClass}
                  unit={unitLabel}
                  side={side}
                  selected={provider === option.provider}
                  now={now}
                  onSelect={selectProvider}
                />
              ))}
            </ul>
            <FieldError id="new-trade-provider-error" message={providerError} />
          </div>
        )}

        <div className="panel-form__field">
          <label className="panel-form__label" htmlFor="new-trade-quantity">
            {wholeUnits ? 'QUANTITY' : 'NOTIONAL'}
          </label>
          <input
            id="new-trade-quantity"
            className="panel-form__input"
            type="number"
            inputMode="decimal"
            min={1}
            step={wholeUnits ? 1 : 'any'}
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

        <div className="panel-form__info">
          <div className="panel-form__info-row">
            <span className="panel-form__info-label">ESTIMATED PRICE</span>
            <span className="panel-form__info-value">
              {quote?.price != null
                ? `${formatUnitPrice(quote.price, assetClass)} ${unitLabel ?? quote.currency ?? ''}`
                : '—'}
            </span>
          </div>
          <div className="panel-form__info-row">
            <span className="panel-form__info-label">QUOTE TIME</span>
            <span className="panel-form__info-value">
              {quote?.atMs != null ? formatDateTime(quote.atMs) : '—'}
            </span>
          </div>
          <div className="panel-form__info-row">
            <span className="panel-form__info-label">EST. POSITION VALUE</span>
            <span className="panel-form__info-value">{formatAmount(estimatedPositionValue)}</span>
          </div>
          <div className="panel-form__info-row">
            <span className="panel-form__info-label">ASSET CLASS</span>
            <span className="panel-form__info-value">
              {selectedBook != null ? (
                <span className="class-tag"><span className="class-tag__dot" />{selectedBook.assetClass}</span>
              ) : '—'}
            </span>
          </div>
        </div>

        {submitError && <div className="panel-form__submit-error" role="alert">{submitError}</div>}

        <button type="submit" className="panel-form__submit" disabled={pending || !valid}>
          {pending ? 'Submitting…' : valid ? submitLabel : 'Submit trade'}
        </button>
      </form>
    </SidePanel>
  )
}
