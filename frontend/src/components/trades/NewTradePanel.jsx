import { useEffect, useRef, useState } from 'react'
import SidePanel from '../panel/SidePanel.jsx'
import ProviderQuoteOption from './ProviderQuoteOption.jsx'
import TermFields from './TermFields.jsx'
import { useMarketFeedContext } from '../../providers/feedContext.js'
import { useElapsedTime } from '../../hooks/useElapsedTime.js'
import { usePolling } from '../../hooks/usePolling.js'
import { apiGet, apiPost } from '../../services/apiClient.js'
import { endpoints } from '../../services/endpoints.js'
import {
  buildCurveTradeIntent,
  buildOpenTradeIntent,
  derivedTermSymbol,
  instrumentCatalogOf,
  isCurvePriced,
  newOpenTradeRequestId,
  providerQuotesOf,
  termCurrencyOf,
  termFormComplete,
  termSchemasOf,
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
  formatSignedAmount,
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

const PREVIEW_DEBOUNCE_MS = 500

export default function NewTradePanel({ onClose }) {
  const { instruments } = useMarketFeedContext()
  const { now } = useElapsedTime()
  const [bookId, setBookId] = useState('')
  const [symbol, setSymbol] = useState('')
  const [customSymbol, setCustomSymbol] = useState('')
  const [symbolEdited, setSymbolEdited] = useState(false)
  const [side, setSide] = useState('BUY')
  const [providerChoice, setProviderChoice] = useState('')
  const [quantityText, setQuantityText] = useState('')
  const [termValues, setTermValues] = useState({})
  const [preview, setPreview] = useState(null)
  const [previewPending, setPreviewPending] = useState(false)
  const [errors, setErrors] = useState({})
  const [pending, setPending] = useState(false)
  const [submitError, setSubmitError] = useState(null)
  const [ack, setAck] = useState(null)
  const [requestId, setRequestId] = useState(newOpenTradeRequestId)
  const previewSeq = useRef(0)
  const booksRequest = usePolling(
    ({ signal }) => apiGet(endpoints.blotter.booksSummary, { signal }),
    { intervalMs: TICKET_OPTIONS_POLL_INTERVAL_MS },
  )
  const catalogRequest = usePolling(
    ({ signal }) => apiGet(endpoints.tradeAction.instruments, { signal }),
    { intervalMs: TICKET_OPTIONS_POLL_INTERVAL_MS },
  )
  const termSchemasRequest = usePolling(
    ({ signal }) => apiGet(endpoints.tradeAction.termSchemas, { signal }),
    { intervalMs: TICKET_OPTIONS_POLL_INTERVAL_MS },
  )
  const books = booksRequest.data == null ? null : bookSummariesOf(booksRequest.data)
  const catalog = catalogRequest.data == null ? null : instrumentCatalogOf(catalogRequest.data)
  const { schemas, curves } = termSchemasOf(termSchemasRequest.data)

  const bookList = (books ?? []).filter((book) => book.isActive)
  const selectedBook = bookList.find((book) => book.id === bookId) ?? null
  const assetClass = selectedBook?.assetClass
  const curvePriced = isCurvePriced(assetClass)
  const schema = curvePriced ? schemas[assetClass] ?? null : null
  const options = curvePriced ? [] : tradeableInstrumentsOf(catalog, assetClass)
  const instrument = options.find((option) => option.symbol === symbol) ?? null

  const termCurrency = curvePriced ? termCurrencyOf(assetClass, termValues, catalog) : null
  const isOption = assetClass === 'EUROPEAN_OPTION'
  const irs = assetClass === 'IRS'
  const underlying = isOption
    ? (catalog ?? []).find((entry) => entry.symbol === termValues.underlying_symbol) ?? null
    : null

  const quotes = providerQuotesOf({
    instrument: curvePriced ? underlying : instrument,
    feed: instruments,
    side,
    now,
  })
  const priced = quotes.filter((option) => Number.isFinite(option.price))
  const provider = providerChoice || (priced.length === 1 ? priced[0].provider : '')
  const quote = quotes.find((option) => option.provider === provider) ?? null

  const derivedSymbol = curvePriced ? derivedTermSymbol(assetClass, termValues) : ''
  const symbolValue = curvePriced
    ? (symbolEdited ? customSymbol : derivedSymbol)
    : symbol

  const wholeUnits = assetClass === 'EQUITY'
  const unitLabel = symbol && !curvePriced ? unitLabelOf({ symbol, assetClass }) : null
  const trimmed = quantityText.trim()
  const quantity = curvePriced && irs ? 1 : trimmed === '' ? null : Number(trimmed)
  const previewPrice = Number.isFinite(preview?.price) ? preview.price : null
  const estimatedPositionValue = curvePriced
    ? previewPrice != null && Number.isFinite(quantity)
      ? previewPrice * quantity
      : null
    : Number.isFinite(quantity) && quote?.price != null
      ? quantity * quote.price
      : null

  const termsComplete = termFormComplete(schema, termValues)
  const previewReady = termsComplete && (!isOption || provider !== '')

  useEffect(() => {
    if (!curvePriced || !previewReady) {
      setPreview(null)
      setPreviewPending(false)
      return undefined
    }
    const sequence = previewSeq.current + 1
    previewSeq.current = sequence
    const controller = new AbortController()
    const timer = setTimeout(async () => {
      setPreviewPending(true)
      try {
        const body = {
          asset_class: assetClass,
          symbol: symbolValue || derivedSymbol || assetClass,
          terms: termValues,
          market_data_provider: provider || undefined,
        }
        const response = await apiPost(endpoints.pricing.price, body, {
          signal: controller.signal,
        })
        if (previewSeq.current === sequence) {
          const price = Number(response?.price)
          setPreview(Number.isFinite(price) ? { price, atMs: Date.now() } : null)
        }
      } catch (err) {
        if (previewSeq.current === sequence && !controller.signal.aborted) {
          setPreview({
            error: describeApiError(err, {
              service: 'Pricing service',
              outcome: 'no model value yet.',
            }),
          })
        }
      } finally {
        if (previewSeq.current === sequence) setPreviewPending(false)
      }
    }, PREVIEW_DEBOUNCE_MS)
    return () => {
      clearTimeout(timer)
      controller.abort()
    }
    // stringified terms: re-preview exactly when a term value changes
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [curvePriced, previewReady, assetClass, provider, JSON.stringify(termValues)])

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
    setTermValues({})
    setPreview(null)
    setCustomSymbol('')
    setSymbolEdited(false)
    setSide('BUY')
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

  function setTerm(name, value) {
    setTermValues((current) => ({ ...current, [name]: value }))
    clearError('terms')
  }

  function formErrorsOf() {
    if (!curvePriced) {
      return tradeFormErrorsOf({ bookId, symbol, quantity, quote, assetClass })
    }
    const next = {}
    if (!bookId) next.book = 'Pick a book.'
    if (schema == null) next.terms = 'Term schema unavailable — retrying.'
    else if (!termsComplete) next.terms = 'Fill in every term.'
    if (!symbolValue) next.instrument = 'Name the instrument.'
    if (isOption && provider === '') next.provider = 'Pick a market data provider for the underlying.'
    if (!irs && (!Number.isFinite(quantity) || quantity <= 0)) {
      next.quantity = 'Quantity must be a positive number.'
    }
    if (previewPrice == null) next.preview = preview?.error ?? 'Waiting for a model value.'
    return next
  }

  async function handleSubmit(event) {
    event.preventDefault()
    const nextErrors = formErrorsOf()
    setErrors(nextErrors)
    if (Object.keys(nextErrors).length > 0) return

    setPending(true)
    setSubmitError(null)
    try {
      const intent = curvePriced
        ? buildCurveTradeIntent({
            clientRequestId: requestId,
            bookId,
            assetClass,
            symbol: symbolValue,
            side: irs ? 'BUY' : side,
            quantity,
            terms: termValues,
            currency: termCurrency,
            provider: isOption ? provider : null,
            previewPrice,
          })
        : buildOpenTradeIntent({
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
        side: intent.side,
        quantity,
        symbol: intent.symbol,
        price: curvePriced ? previewPrice : quote.price,
        provider: curvePriced ? provider || null : quote.provider,
        model: curvePriced,
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
    !curvePriced && quote != null && !quote.tradeable ? currentFormErrors.provider : null
  )
  const submitLabel = !valid
    ? 'Submit trade intent'
    : curvePriced
      ? `${irs ? 'OPEN' : side} ${symbolValue} at model value ${formatSignedAmount(previewPrice)} ${termCurrency ?? ''}`
      : `${side} ${formatNumber(quantity)} ${symbol} at ${formatUnitPrice(quote.price, assetClass)}`

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
            {ack.side} {formatNumber(ack.quantity)} × {ack.symbol}
            {ack.provider != null && <> via {providerLabel(ack.provider)}</>}
            {ack.model && ' · model-priced'}
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
            {curvePriced ? (
              <input
                id="new-trade-instrument"
                className="panel-form__input"
                type="text"
                value={symbolValue}
                aria-invalid={errors.instrument != null}
                aria-describedby={errors.instrument ? 'new-trade-instrument-error' : undefined}
                onChange={(event) => {
                  setCustomSymbol(event.target.value.toUpperCase())
                  setSymbolEdited(true)
                  clearError('instrument')
                }}
              />
            ) : (
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
            )}
            <FieldError id="new-trade-instrument-error" message={errors.instrument} />
          </div>
        </div>

        {curvePriced && schema == null && (
          <p className="panel-form__note" role="status">
            {termSchemasRequest.error
              ? 'Term schemas unavailable — retrying.'
              : 'Loading term schema…'}
          </p>
        )}

        {curvePriced && schema != null && (
          <>
            <TermFields
              schema={schema}
              values={termValues}
              curves={curves}
              currency={termCurrency}
              onChange={setTerm}
            />
            <FieldError id="new-trade-terms-error" message={errors.terms} />
          </>
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

        {!irs && (
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
        )}

        {(curvePriced ? isOption && underlying != null : symbol !== '') && (
          <div className="panel-form__field">
            <span className="panel-form__label" id="new-trade-provider-label">
              {curvePriced ? 'UNDERLYING MARKET DATA PROVIDER' : 'MARKET DATA PROVIDER'}
            </span>
            <ul className="quote-options" aria-labelledby="new-trade-provider-label">
              {quotes.map((option) => (
                <ProviderQuoteOption
                  key={option.provider}
                  quote={option}
                  assetClass={curvePriced ? underlying?.assetClass : assetClass}
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

        {!irs && (
          <div className="panel-form__field">
            <label className="panel-form__label" htmlFor="new-trade-quantity">
              {wholeUnits || curvePriced ? 'QUANTITY' : 'NOTIONAL'}
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
        )}

        <div className="panel-form__info">
          <div className="panel-form__info-row">
            <span className="panel-form__info-label">
              {curvePriced ? 'MODEL VALUE' : 'ESTIMATED PRICE'}
            </span>
            <span className="panel-form__info-value">
              {curvePriced
                ? previewPending
                  ? 'Computing…'
                  : previewPrice != null
                    ? `${formatSignedAmount(previewPrice)} ${termCurrency ?? ''}`
                    : '—'
                : quote?.price != null
                  ? `${formatUnitPrice(quote.price, assetClass)} ${unitLabel ?? quote.currency ?? ''}`
                  : '—'}
            </span>
          </div>
          <div className="panel-form__info-row">
            <span className="panel-form__info-label">
              {curvePriced ? 'MODEL TIME' : 'QUOTE TIME'}
            </span>
            <span className="panel-form__info-value">
              {curvePriced
                ? preview?.atMs != null ? formatDateTime(preview.atMs) : '—'
                : quote?.atMs != null ? formatDateTime(quote.atMs) : '—'}
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

        {curvePriced && preview?.error && (
          <p className="panel-form__note" role="alert">{preview.error}</p>
        )}

        {submitError && <div className="panel-form__submit-error" role="alert">{submitError}</div>}

        <button type="submit" className="panel-form__submit" disabled={pending || !valid}>
          {pending ? 'Submitting…' : submitLabel}
        </button>
      </form>
    </SidePanel>
  )
}
