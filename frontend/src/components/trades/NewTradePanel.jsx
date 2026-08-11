import { useEffect, useState } from 'react'
import SidePanel from '../panel/SidePanel.jsx'
import { useMarketFeedContext } from '../../providers/feedContext.js'
import { apiGet, apiPost } from '../../services/apiClient.js'
import { endpoints } from '../../services/endpoints.js'
import {
  buildOpenTradeIntent,
  derivedSymbolOf,
  instrumentCatalogOf,
  newOpenTradeRequestId,
  termErrorsOf,
  termSchemaOf,
  termsFromValues,
  tradeFormErrorsOf,
  tradeableInstrumentsOf,
} from '../../domain/tradeActions.js'
import { bookSummariesOf } from '../../domain/books.js'
import { describeApiError } from '../../domain/apiErrors.js'
import {
  formatAmount,
  formatNumber,
  formatShortId,
  formatUnitPrice,
} from '../../domain/formatting.js'

function FieldError({ id, message }) {
  if (!message) return null
  return (
    <span id={id} className="panel-form__error" role="alert">
      {message}
    </span>
  )
}

function normalizedQuote(data) {
  return {
    ...data,
    price: Number(data?.price),
    multiplier: Number(data?.multiplier),
  }
}

function formatRate(rate) {
  const value = Number(rate)
  return Number.isFinite(value) ? `${(value * 100).toFixed(2)}%` : '—'
}

function choiceLabel(field, choice) {
  return field.labels?.[choice] ?? String(choice).replaceAll('_', ' ')
}

function SwapTerms({ instrument }) {
  if (instrument?.assetClass !== 'IRS') return null

  const payFixed = instrument.direction === 'PAY_FIXED_RECEIVE_FLOAT'
  const payments = Number(instrument.payments_per_year)
  const maturity = Number(instrument.maturity_years)
  const paymentLabel = payments === 1
    ? 'Annual'
    : Number.isFinite(payments) && payments > 0
      ? `${formatNumber(payments)} per year`
      : '—'
  const countLabel = Number.isFinite(payments) && Number.isFinite(maturity)
    ? `${formatNumber(Math.ceil(payments * maturity))} payments`
    : null

  return (
    <div className="panel-form__info" aria-label="Selected interest-rate swap terms">
      <div className="panel-form__info-row">
        <span className="panel-form__info-label">FIXED LEG</span>
        <span className="panel-form__info-value">
          {payFixed ? 'Pay' : 'Receive'} {formatRate(instrument.fixed_rate)} / year
        </span>
      </div>
      <div className="panel-form__info-row">
        <span className="panel-form__info-label">FLOATING LEG</span>
        <span className="panel-form__info-value">
          {payFixed ? 'Receive' : 'Pay'} USD_GOV floating rate
        </span>
      </div>
      <div className="panel-form__info-row">
        <span className="panel-form__info-label">NOTIONAL</span>
        <span className="panel-form__info-value">
          USD {formatAmount(Number(instrument.notional), 0)} · not exchanged
        </span>
      </div>
      <div className="panel-form__info-row">
        <span className="panel-form__info-label">TERM</span>
        <span className="panel-form__info-value">
          {formatNumber(maturity)} years · {paymentLabel}{countLabel != null && ` · ${countLabel}`}
        </span>
      </div>
    </div>
  )
}

function TermField({ field, value, error, onChange }) {
  const inputId = `new-trade-term-${field.name}`
  const errorId = `${inputId}-error`

  if (field.type === 'choice' && field.choices.length === 2) {
    return (
      <div className="panel-form__field panel-form__field--span">
        <span className="panel-form__label" id={`${inputId}-label`}>{field.label}</span>
        <div className="panel-form__side panel-form__side--stretch" role="group" aria-labelledby={`${inputId}-label`}>
          {field.choices.map((choice) => (
            <button
              key={choice}
              type="button"
              className="panel-form__side-button"
              aria-pressed={value === choice}
              onClick={() => onChange(field.name, choice)}
            >
              {choiceLabel(field, choice)}
            </button>
          ))}
        </div>
        <FieldError id={errorId} message={error} />
      </div>
    )
  }

  return (
    <div className="panel-form__field">
      <label className="panel-form__label" htmlFor={inputId}>{field.label}</label>
      {field.type === 'choice' ? (
        <select
          id={inputId}
          className="panel-form__select"
          value={value ?? ''}
          aria-invalid={error != null}
          aria-describedby={error ? errorId : undefined}
          onChange={(event) => onChange(field.name, event.target.value)}
        >
          <option value="">Select…</option>
          {field.choices.map((choice) => (
            <option key={choice} value={choice}>{choiceLabel(field, choice)}</option>
          ))}
        </select>
      ) : (
        <input
          id={inputId}
          className="panel-form__input"
          type="number"
          inputMode="decimal"
          step={field.type === 'integer' ? 1 : 'any'}
          value={value ?? ''}
          aria-invalid={error != null}
          aria-describedby={error ? errorId : undefined}
          onChange={(event) => onChange(field.name, event.target.value)}
        />
      )}
      <FieldError id={errorId} message={error} />
    </div>
  )
}

export default function NewTradePanel({ onClose }) {
  const { instruments } = useMarketFeedContext()
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
  const [catalog, setCatalog] = useState(null)
  const [catalogError, setCatalogError] = useState(null)
  const [preview, setPreview] = useState(null)
  const [termSchemas, setTermSchemas] = useState(null)
  const [termValues, setTermValues] = useState({})

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

  useEffect(() => {
    const controller = new AbortController()
    apiGet(endpoints.tradeAction.instruments, { signal: controller.signal })
      .then((data) => setCatalog(instrumentCatalogOf(data)))
      .catch((err) => {
        if (controller.signal.aborted) return
        setCatalog([])
        setCatalogError(err?.message ?? 'Could not load instruments')
      })
    apiGet(endpoints.tradeAction.termSchemas, { signal: controller.signal })
      .then(setTermSchemas)
      .catch(() => {
        if (controller.signal.aborted) return
      })
    return () => controller.abort()
  }, [])

  const bookList = (books ?? []).filter((book) => book.isActive)
  const selectedBook = bookList.find((book) => book.id === bookId) ?? null
  const assetClass = selectedBook?.assetClass
  const options = tradeableInstrumentsOf(catalog, assetClass)
  const instrument = options.find((option) => option.symbol === symbol) ?? null

  const schema = termSchemaOf(termSchemas, assetClass)
  const customMode = schema != null
  const fields = customMode ? schema.fields : []
  const termErrors = customMode ? termErrorsOf(fields, termValues) : {}
  const termsComplete = customMode && Object.keys(termErrors).length === 0
  const customTerms = termsComplete ? termsFromValues(fields, termValues) : null
  const customTermsKey = customTerms == null ? '' : JSON.stringify(customTerms)
  const effectiveSymbol = customMode
    ? (customTerms == null ? '' : derivedSymbolOf(assetClass, customTerms))
    : symbol

  const price = preview?.price ?? null
  const curveName = instrument?.curve ?? 'USD_GOV'
  const curveRevision = Object.values(instruments).find(
    (marketInstrument) =>
      marketInstrument.assetClass === 'RATE' && marketInstrument.id.startsWith(`${curveName}@`),
  )?.sourceEventId ?? ''
  const activeUnderlying = customMode
    ? termValues.underlying_symbol ?? ''
    : instrument?.underlying_symbol ?? symbol
  const spotRevision = instruments[activeUnderlying]?.sourceEventId ?? ''
  const quoteRevision = assetClass === 'IRS' || assetClass === 'BOND'
    ? curveRevision
    : assetClass === 'EUROPEAN_OPTION'
      ? `${spotRevision}:${curveRevision}`
      : spotRevision

  useEffect(() => {
    if (customMode ? customTerms == null : !symbol) {
      setPreview(null)
      return undefined
    }
    const controller = new AbortController()
    const body = customMode
      ? { asset_class: assetClass, terms: customTerms }
      : { symbol }
    apiPost(endpoints.pricing.price, body, { signal: controller.signal })
      .then((data) => {
        setPreview(normalizedQuote(data))
      })
      .catch(() => {
        if (controller.signal.aborted) return
      })
    return () => controller.abort()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbol, customMode, customTermsKey, quoteRevision])

  const trimmed = quantityText.trim()
  const quantity = trimmed === '' ? null : Number(trimmed)
  const estimatedPositionValue =
    Number.isFinite(quantity) && Number.isFinite(price)
      ? quantity * price * (preview?.multiplier ?? 1)
      : null

  function clearError(field) {
    setErrors((current) => {
      if (!current[field]) return current
      const next = { ...current }
      delete next[field]
      return next
    })
  }

  function resetInstrumentState() {
    setPreview(null)
    setTermValues({})
    setErrors({})
  }

  function selectBook(nextBookId) {
    setBookId(nextBookId)
    resetInstrumentState()
    const nextBook = bookList.find((book) => book.id === nextBookId) ?? null
    const nextOptions = tradeableInstrumentsOf(catalog, nextBook?.assetClass)
    setSymbol(nextOptions.length === 1 ? nextOptions[0].symbol : '')
  }

  function setTermValue(name, value) {
    setTermValues((current) => ({ ...current, [name]: value }))
    clearError(name)
    clearError('price')
  }

  function formErrorsOf() {
    const base = tradeFormErrorsOf({ bookId, symbol: effectiveSymbol, quantity, price, assetClass })
    if (!customMode) return base
    const combined = { ...base, ...termErrorsOf(fields, termValues) }
    delete combined.instrument
    return combined
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
        symbol: effectiveSymbol,
        side,
        quantity,
        price,
        currency: customMode ? 'USD' : instrument.currency,
        terms: customMode ? customTerms : undefined,
      })
      const accepted = await apiPost(endpoints.tradeAction.submit, intent)
      setAck({
        tradeId: accepted?.trade_id ?? null,
        side,
        quantity,
        symbol: effectiveSymbol,
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

  const valid = Object.keys(formErrorsOf()).length === 0
  const submitLabel = valid
    ? `Submit ${side} ${formatNumber(quantity)} ${effectiveSymbol}`
    : 'Submit trade intent'
  const termsInstrument = customMode
    ? (termsComplete ? { assetClass, ...customTerms } : null)
    : instrument

  return (
    <SidePanel
      eyebrow="TRADE ACTION"
      title="New trade"
      subtitle="intent at displayed snapshot price"
      dismissOnOutsideClick={false}
      onClose={onClose}
    >
      <form className="panel-form__form" onSubmit={handleSubmit} noValidate>
        <div className="panel-form__row">
          <div className={customMode ? 'panel-form__field panel-form__field--span' : 'panel-form__field'}>
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
              message={booksError ? 'Books service unavailable — could not load books.' : errors.book}
            />
          </div>

          {!customMode && (
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
                  clearError('instrument')
                  clearError('price')
                  setPreview(null)
                }}
              >
                <option value="">{options.length === 0 ? 'No instrument' : 'Select instrument…'}</option>
                {options.map((option) => (
                  <option key={option.symbol} value={option.symbol}>{option.symbol}</option>
                ))}
              </select>
              <FieldError id="new-trade-instrument-error" message={errors.instrument} />
            </div>
          )}
        </div>

        {customMode && (
          <div className="panel-form__row">
            {fields.map((field) => (
              <TermField
                key={field.name}
                field={field}
                value={termValues[field.name]}
                error={errors[field.name]}
                onChange={setTermValue}
              />
            ))}
          </div>
        )}

        {selectedBook != null && !customMode && options.length === 0 && (
          <p className="panel-form__note" role="status">
            {catalog == null
              ? 'Loading supported instruments…'
              : catalogError
                ? 'Instrument catalog unavailable — reopen this panel to retry.'
                : `No ${selectedBook.assetClass} instrument is configured.`}
          </p>
        )}

        <SwapTerms instrument={termsInstrument} />

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

        <div className="panel-form__field">
          <label className="panel-form__label" htmlFor="new-trade-quantity">QUANTITY</label>
          <input
            id="new-trade-quantity"
            className="panel-form__input"
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

        <div className="panel-form__info">
          {customMode && (
            <div className="panel-form__info-row">
              <span className="panel-form__info-label">SYMBOL</span>
              <span className="panel-form__info-value">{effectiveSymbol || '—'}</span>
            </div>
          )}
          <div className="panel-form__info-row">
            <span className="panel-form__info-label">BACKEND MARK</span>
            <span className="panel-form__info-value">
              {formatUnitPrice(price, assetClass)}
            </span>
          </div>
          <div className="panel-form__info-row">
            <span className="panel-form__info-label">
              EST. POSITION VALUE
            </span>
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
        <FieldError id="new-trade-price-error" message={errors.price} />

        <div className="panel-form__summary" aria-live="polite">
          <span className={`panel-form__summary-side panel-form__summary-side--${side.toLowerCase()}`}>
            ● {side}
          </span>
          <span>{Number.isFinite(quantity) ? formatNumber(quantity) : '—'} × {effectiveSymbol || '—'}</span>
        </div>

        {submitError && <div className="panel-form__submit-error" role="alert">{submitError}</div>}

        {ack && (
          <div className="panel-form__ack" role="status">
            <span>
              Accepted — {ack.side} {formatNumber(ack.quantity)} × {ack.symbol}
              {ack.tradeId != null && ` as trade ${formatShortId(ack.tradeId)}`}.
            </span>
            <a className="panel-form__ack-link" href="#/trades" onClick={onClose}>View in Trades</a>
          </div>
        )}

        <button type="submit" className="panel-form__submit" disabled={pending}>
          {pending ? 'Submitting…' : submitLabel}
        </button>
      </form>
    </SidePanel>
  )
}
