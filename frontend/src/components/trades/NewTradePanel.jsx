import { useEffect, useMemo, useState } from 'react'
import SidePanel from '../panel/SidePanel.jsx'
import LoadingSkeleton from '../LoadingSkeleton.jsx'
import PriceSourcePicker from './PriceSourcePicker.jsx'
import TermFields from './TermFields.jsx'
import TicketValue from './TicketValue.jsx'
import TradeSubmitted from './TradeSubmitted.jsx'
import NumberField from './NumberField.jsx'
import { useMarketFeedContext } from '../../providers/feedContext.js'
import { useElapsedTime } from '../../hooks/useElapsedTime.js'
import { useModelPreview } from '../../hooks/useModelPreview.js'
import { usePolling } from '../../hooks/usePolling.js'
import { apiGet, apiPost } from '../../services/apiClient.js'
import { endpoints } from '../../services/endpoints.js'
import { onWatchlistChange } from '../../services/watchlistEvents.js'
import {
  buildCurveTradeIntent,
  buildOpenTradeIntent,
  curveChoicesFor,
  newOpenTradeRequestId,
  preferredQuoteProviderOf,
  providerQuotesOf,
  termCurrencyOf,
  termFormComplete,
  ticketOptionsOf,
  tradeableInstrumentsOf,
} from '../../domain/tradeActions.js'
import {
  ackSummaryOf,
  hasTermField,
  quantityLabelOf,
  submitActionOf,
  ticketErrorsOf,
  ticketValueOf,
} from '../../domain/ticket.js'
import { bookSummariesOf } from '../../domain/books.js'
import { describeApiError } from '../../domain/apiErrors.js'
import { assetClassLabel } from '../../domain/catalogue.js'
import { formatAmount } from '../../domain/formatting.js'
import { quantityUnitLabelOf, unitLabelOf } from '../../domain/marketFormat.js'

const CURVE_TERM_FIELDS = ['discount_curve', 'projection_curve']

function TicketNote({ children }) {
  return (
    <p className="panel-form__note" role="status">
      {children}
    </p>
  )
}

function ticketSchemaNote(assetClass, requestError, schemas) {
  return requestError
    ? 'Ticket configuration unavailable.'
    : `No ticket configuration for ${assetClassLabel(assetClass, schemas)}.`
}

function watchlistNote(assetClass, requestError, catalog, schemas) {
  if (requestError || catalog == null) return 'Instrument list unavailable.'
  return `No ${assetClassLabel(assetClass, schemas)} symbol is on the watchlist — add one in Market data.`
}

function FieldError({ id, message }) {
  if (!message) return null
  return (
    <span id={id} className="panel-form__error" role="alert">
      {message}
    </span>
  )
}

function ExecutionFields({
  schema,
  assetClass,
  side,
  quantityText,
  quantityError,
  onSideChange,
  onQuantityChange,
}) {
  const sides = schema.allowed_sides ?? ['BUY', 'SELL']
  const showSide = sides.length > 1
  const showQuantity = schema.fixed_quantity == null
  if (!showSide && !showQuantity) return null
  return (
    <div className="panel-form__execution-row">
      {showSide && (
        <div className="panel-form__field">
          <span className="panel-form__label" id="new-trade-side-label">SIDE</span>
          <div className="panel-form__side" role="group" aria-labelledby="new-trade-side-label">
            {sides.map((option) => (
              <button
                key={option}
                type="button"
                className="panel-form__side-button"
                aria-pressed={side === option}
                onClick={() => onSideChange(option)}
              >
                {option === 'BUY' ? 'Buy' : 'Sell'}
              </button>
            ))}
          </div>
        </div>
      )}
      {showQuantity && (
        <div className="panel-form__field">
          <label className="panel-form__label" htmlFor="new-trade-quantity">
            {quantityLabelOf(schema, assetClass)}
          </label>
          <NumberField
            id="new-trade-quantity"
            value={quantityText}
            aria-invalid={quantityError != null}
            aria-describedby={quantityError ? 'new-trade-quantity-error' : undefined}
            onChange={onQuantityChange}
          />
          <FieldError id="new-trade-quantity-error" message={quantityError} />
        </div>
      )}
    </div>
  )
}

function without(errors, fields) {
  if (!fields.some((field) => errors[field] != null)) return errors
  const next = { ...errors }
  fields.forEach((field) => delete next[field])
  return next
}

function resolveCurveFields(next, curves, currency, assetClass) {
  CURVE_TERM_FIELDS.forEach((field) => {
    const eligible = currency
      ? curveChoicesFor(curves, currency, field, next.floating_rate_index_tenor, assetClass)
      : []
    if (eligible.some((curve) => curve.curve_name === next[field])) return
    if (eligible.length === 1) next[field] = eligible[0].curve_name
    else delete next[field]
  })
}

export default function NewTradePanel({ onClose }) {
  const { instruments, curves: feedCurves } = useMarketFeedContext()
  const { now } = useElapsedTime()
  const [bookId, setBookId] = useState('')
  const [symbol, setSymbol] = useState('')
  const [side, setSide] = useState('BUY')
  const [providerChoice, setProviderChoice] = useState('')
  const [quantityText, setQuantityText] = useState('')
  const [termValues, setTermValues] = useState({})
  const [staleCurveAcknowledged, setStaleCurveAcknowledged] = useState(false)
  const [errors, setErrors] = useState({})
  const [pending, setPending] = useState(false)
  const [submitError, setSubmitError] = useState(null)
  const [ack, setAck] = useState(null)
  const [requestId, setRequestId] = useState(newOpenTradeRequestId)
  const booksRequest = usePolling(
    ({ signal }) => apiGet(endpoints.books.list, { signal }),
    { intervalMs: null },
  )
  const optionsRequest = usePolling(
    ({ signal }) => apiGet(endpoints.tradeAction.termSchemas, { signal }),
    { intervalMs: null },
  )
  const refetchOptions = optionsRequest.refetch

  useEffect(
    () => onWatchlistChange(() => refetchOptions()),
    [refetchOptions],
  )

  const books = booksRequest.data == null ? null : bookSummariesOf(booksRequest.data)
  const optionsPayload = optionsRequest.data == null ? null : ticketOptionsOf(optionsRequest.data)
  const catalog = optionsPayload?.instruments ?? null
  const schemas = optionsPayload?.schemas ?? {}
  const curves = optionsPayload?.curves ?? []

  const bookList = (books ?? []).filter((book) => book.isActive)
  const selectedBook = bookList.find((book) => book.id === bookId) ?? null
  const assetClass = selectedBook?.assetClass
  const schema = assetClass ? schemas[assetClass] ?? null : null
  const modelPriced = schema?.needs_curve === true
  const needsQuote = schema?.needs_quote === true
  const underlyingField = schema?.underlying_field ?? null
  const options = useMemo(
    () => (schema == null || modelPriced ? [] : tradeableInstrumentsOf(catalog, assetClass)),
    [assetClass, catalog, modelPriced, schema],
  )
  const instrument = options.find((option) => option.symbol === symbol) ?? null
  const currentUnderlying = underlyingField ? termValues[underlyingField] ?? null : null
  const underlying = currentUnderlying
    ? (catalog ?? []).find((entry) => entry.symbol === currentUnderlying) ?? null
    : null
  const quoteInstrument = modelPriced ? underlying : instrument
  const termCurrency = modelPriced ? termCurrencyOf(schema, termValues, catalog) : null
  const sides = schema?.allowed_sides ?? ['BUY', 'SELL']
  const effectiveSide = sides.includes(side) ? side : sides[0]
  const fixedQuantity = schema?.fixed_quantity ?? null
  const selectedCurve = curves.find((curve) => curve.curve_name === termValues.discount_curve) ?? null
  const selectedStaleCurves = CURVE_TERM_FIELDS
    .map((field) => curves.find((curve) => curve.curve_name === termValues[field]))
    .filter((curve) => curve?.stale === true)

  useEffect(() => {
    if (selectedBook == null || schema == null || modelPriced || catalog == null) return
    if (options.some((option) => option.symbol === symbol)) return
    setSymbol(options.length === 1 ? options[0].symbol : '')
    setProviderChoice('')
    setErrors((current) => without(current, ['instrument', 'provider']))
  }, [catalog, modelPriced, options, schema, selectedBook, symbol])

  const underlyingChoices = useMemo(
    () => (underlyingField
      ? schema?.fields.find((field) => field.name === underlyingField)?.choices ?? []
      : []),
    [schema, underlyingField],
  )
  useEffect(() => {
    if (!currentUnderlying || schema == null || underlyingChoices.includes(currentUnderlying)) return
    setTermValues((current) => {
      if (current[underlyingField] !== currentUnderlying) return current
      const next = { ...current }
      delete next[underlyingField]
      delete next.settlement_currency
      CURVE_TERM_FIELDS.forEach((field) => delete next[field])
      return next
    })
    setProviderChoice('')
    setErrors((current) => without(current, ['provider', 'preview']))
  }, [currentUnderlying, schema, underlyingChoices, underlyingField])

  const quotes = providerQuotesOf({
    instrument: quoteInstrument,
    feed: instruments,
    side: modelPriced ? null : effectiveSide,
    now,
  })
  const provider = providerChoice || preferredQuoteProviderOf(quotes) || ''
  const quote = quotes.find((option) => option.provider === provider) ?? null

  const unitLabel = symbol && !modelPriced ? unitLabelOf({ symbol, assetClass }) : null
  const trimmed = quantityText.trim()
  const quantity = fixedQuantity ?? (trimmed === '' ? null : Number(trimmed))
  const termsComplete = termFormComplete(schema, termValues)
  const previewReady = modelPriced && termsComplete && (!needsQuote || quote?.tradeable === true)
  const expectedMarketRevisions = {
    spot: needsQuote && quote != null ? {
      provider: quote.provider,
      symbol: currentUnderlying,
      provider_timestamp: quote.providerTimestamp,
      received_at: quote.receivedAt,
    } : null,
    ...Object.fromEntries(CURVE_TERM_FIELDS.map((field) => {
      const chosen = feedCurves?.[termValues[field]]
      return [field, chosen == null ? null : {
        curve_name: chosen.name,
        as_of_date: chosen.asOfDate,
        received_at: chosen.receivedAt,
      }]
    })),
  }
  const previewRequestKey = JSON.stringify({
    assetClass,
    provider,
    termValues,
    underlyingQuotePrice: needsQuote ? quote?.price ?? null : null,
    expectedMarketRevisions,
  })
  const { preview, previewError, previewLoading } = useModelPreview({
    enabled: previewReady,
    requestKey: previewRequestKey,
    buildBody: () => ({
      asset_class: assetClass,
      symbol: assetClass,
      terms: termValues,
      market_data_provider: provider || undefined,
      expected_market_revisions: expectedMarketRevisions,
    }),
  })
  const previewPrice = preview?.price ?? null
  const valueCurrency = modelPriced ? termCurrency : quote?.currency ?? null

  function clearErrors(fields) {
    setErrors((current) => without(current, fields))
  }

  function selectBook(nextBookId) {
    setBookId(nextBookId)
    setProviderChoice('')
    setQuantityText('')
    setErrors({})
    setTermValues({})
    setStaleCurveAcknowledged(false)
    setSubmitError(null)
    setSide('BUY')
    const nextBook = bookList.find((book) => book.id === nextBookId) ?? null
    const nextSchema = nextBook ? schemas[nextBook.assetClass] ?? null : null
    const nextOptions = nextSchema == null || nextSchema.needs_curve
      ? []
      : tradeableInstrumentsOf(catalog, nextBook.assetClass)
    setSymbol(nextOptions.length === 1 ? nextOptions[0].symbol : '')
  }

  function selectProvider(nextProvider) {
    setProviderChoice(nextProvider)
    clearErrors(['provider'])
  }

  function resetTicket() {
    setBookId('')
    setSymbol('')
    setSide('BUY')
    setProviderChoice('')
    setQuantityText('')
    setTermValues({})
    setStaleCurveAcknowledged(false)
    setErrors({})
    setSubmitError(null)
    setAck(null)
    setRequestId(newOpenTradeRequestId())
  }

  function setTerm(name, value) {
    setStaleCurveAcknowledged(false)
    setTermValues((current) => {
      const next = { ...current, [name]: value }
      if (!underlyingField && CURVE_TERM_FIELDS.includes(name) && !next.settlement_currency) {
        const chosen = curves.find((curve) => curve.curve_name === value)
        if (chosen != null) next.settlement_currency = chosen.currency
      }
      if (underlyingField && name === underlyingField) {
        delete next.settlement_currency
        const entry = (catalog ?? []).find((item) => item.symbol === value)
        resolveCurveFields(next, curves, entry?.currency ?? null, assetClass)
      }
      if (name === 'settlement_currency') {
        resolveCurveFields(next, curves, value, assetClass)
      }
      if (name === 'floating_rate_index_tenor' && next.projection_curve) {
        const chosen = curves.find((curve) => curve.curve_name === next.projection_curve)
        if (chosen?.index_tenor && chosen.index_tenor !== value) delete next.projection_curve
      }
      return next
    })
    if (underlyingField && name === underlyingField) setProviderChoice('')
    clearErrors(['terms', 'preview'])
  }

  const currentFormErrors = ticketErrorsOf({
    bookId,
    schema,
    schemaError: optionsRequest.error,
    symbol,
    termsComplete,
    staleCurves: selectedStaleCurves,
    staleAcknowledged: staleCurveAcknowledged,
    hasQuoteInstrument: quoteInstrument != null,
    quote,
    quantity,
    previewPrice,
    previewError,
  })
  const valid = Object.keys(currentFormErrors).length === 0

  async function handleSubmit(event) {
    event.preventDefault()
    setErrors(currentFormErrors)
    if (!valid) return

    setPending(true)
    setSubmitError(null)
    try {
      const intent = modelPriced
        ? buildCurveTradeIntent({
            clientRequestId: requestId,
            bookId,
            assetClass,
            side: effectiveSide,
            quantity,
            terms: termValues,
            currency: termCurrency,
            provider: needsQuote ? provider : null,
            previewPrice,
            staleCurveAcknowledged,
          })
        : buildOpenTradeIntent({
            clientRequestId: requestId,
            bookId,
            assetClass,
            symbol,
            side: effectiveSide,
            quantity,
            quote,
          })
      const accepted = await apiPost(endpoints.tradeAction.submit, intent)
      setAck({
        tradeId: accepted?.trade_id ?? null,
        summary: ackSummaryOf({
          schema,
          side: intent.side,
          quantity,
          symbol: intent.symbol ?? null,
          terms: termValues,
          currency: termCurrency,
        }),
        provider: modelPriced ? (needsQuote ? provider || null : null) : quote.provider,
        modelPriced,
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

  const providerError = errors.provider ?? (
    quote != null && !quote.tradeable ? currentFormErrors.provider : null
  )
  const submitLabel = submitActionOf({ side: effectiveSide, valid })
  const showTicket = selectedBook != null && schema != null
  const ticketValue = showTicket
    ? ticketValueOf({
        assetClass,
        schema,
        terms: termValues,
        side: effectiveSide,
        quantity,
        quote,
        preview,
        curve: selectedCurve,
        currency: valueCurrency,
        unitLabel,
        quantityUnit: quantityUnitLabelOf({ symbol, assetClass, currency: valueCurrency }),
        volatility: schema.defaults?.volatility ?? 0,
        now,
      })
    : null
  const valuePlaceholder = modelPriced
    ? termsComplete
      ? needsQuote && quote?.tradeable !== true
        ? 'Waiting for a usable underlying quote'
        : 'Waiting for the model value'
      : 'Complete the contract terms to see the model value'
    : symbol === ''
      ? 'Pick an instrument to see the execution price'
      : quotes.length === 0
        ? 'No price source is available for this instrument'
        : 'Pick a price source'
  const ticketLoading = booksRequest.loading || optionsRequest.loading
  const executionFields = schema != null && selectedBook != null ? (
    <ExecutionFields
      schema={schema}
      assetClass={assetClass}
      side={effectiveSide}
      quantityText={quantityText}
      quantityError={errors.quantity}
      onSideChange={setSide}
      onQuantityChange={(next) => {
        setQuantityText(next)
        clearErrors(['quantity'])
      }}
    />
  ) : null

  if (ack) {
    return (
      <TradeSubmitted
        summary={ack.summary}
        provider={ack.provider}
        modelPriced={ack.modelPriced}
        tradeId={ack.tradeId}
        onNewTrade={resetTicket}
        onClose={onClose}
      />
    )
  }

  return (
    <SidePanel
      wide
      compact
      eyebrow="TRADE ACTION"
      title="New trade"
      subtitle={selectedBook?.name ?? 'Select a book to continue'}
      bodyClassName="new-trade-panel"
      dismissOnOutsideClick={false}
      onClose={onClose}
      footer={showTicket ? (
        <div className="new-trade-footer">
          <button
            type="submit"
            form="new-trade-form"
            className="panel-form__submit"
            disabled={pending || !valid}
          >
            {pending ? 'Submitting…' : submitLabel}
          </button>
        </div>
      ) : null}
    >
      {ticketLoading ? (
        <LoadingSkeleton variant="panel" rows={8} label="Loading new trade inputs" />
      ) : <form id="new-trade-form" className="panel-form__form" onSubmit={handleSubmit} noValidate>
        <div className="panel-form__book-row">
          <div className="panel-form__field panel-form__field--wide">
            <label className="panel-form__label" htmlFor="new-trade-book">BOOK</label>
            <select
              id="new-trade-book"
              className="panel-form__select"
              value={bookId}
              aria-invalid={errors.book != null}
              aria-describedby={errors.book ? 'new-trade-book-error' : undefined}
              onChange={(event) => selectBook(event.target.value)}
            >
              <option value="">{books == null ? 'Books unavailable' : 'Select book…'}</option>
              {bookList.map((book) => (
                <option key={book.id} value={book.id}>
                  {book.name} · {assetClassLabel(book.assetClass, schemas)}
                </option>
              ))}
            </select>
            <FieldError
              id="new-trade-book-error"
              message={booksRequest.error ? 'Books service unavailable — could not load books.' : errors.book}
            />
          </div>
        </div>

        {selectedBook != null && schema == null && (
          <TicketNote>
            {ticketSchemaNote(assetClass, optionsRequest.error, schemas)}
          </TicketNote>
        )}

        {showTicket && !modelPriced && (
          <div className="panel-form__spot-layout">
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
                  clearErrors(['instrument', 'provider'])
                }}
              >
                <option value="">{options.length === 0 ? 'No instrument' : 'Select instrument…'}</option>
                {options.map((option) => (
                  <option key={option.symbol} value={option.symbol}>{option.symbol}</option>
                ))}
              </select>
              <FieldError id="new-trade-instrument-error" message={errors.instrument} />
            </div>
            {executionFields}
          </div>
        )}

        {showTicket && modelPriced && (
          <>
            <TermFields
              schema={schema}
              values={termValues}
              curves={curves}
              marketCurves={feedCurves}
              currency={termCurrency}
              assetClass={assetClass}
              onChange={setTerm}
              executionFields={executionFields}
            />
            {selectedStaleCurves.length > 0 && (
              <label className="panel-form__check">
                <input
                  type="checkbox"
                  checked={staleCurveAcknowledged}
                  onChange={(event) => {
                    setStaleCurveAcknowledged(event.target.checked)
                    clearErrors(['terms'])
                  }}
                />
                {`Use ${selectedStaleCurves
                  .map((curve) => curve.curve_name)
                  .join(', ')} despite stale source dates`}
              </label>
            )}
            <FieldError id="new-trade-terms-error" message={errors.terms} />
          </>
        )}

        {showTicket && !modelPriced && options.length === 0 && (
          <TicketNote>
            {watchlistNote(selectedBook.assetClass, optionsRequest.error, catalog, schemas)}
          </TicketNote>
        )}

        {ticketValue && (
          <TicketValue
            {...ticketValue}
            loading={previewLoading}
            placeholder={valuePlaceholder}
            error={errors.preview}
          />
        )}

        {showTicket && needsQuote && quoteInstrument != null && (
          <PriceSourcePicker
            label={modelPriced ? 'UNDERLYING PRICE SOURCE' : 'PRICE SOURCE'}
            quotes={quotes}
            selected={provider}
            onSelect={selectProvider}
          >
            {hasTermField(schema, 'strike') && quote?.tradeable && Number.isFinite(quote.price) && (
              <div className="panel-form__field-assist">
                <button
                  type="button"
                  className="panel-form__inline-action"
                  onClick={() => setTerm('strike', String(quote.price))}
                >
                  Use {formatAmount(quote.price, 2)} as strike
                </button>
              </div>
            )}
            <FieldError id="new-trade-provider-error" message={providerError} />
          </PriceSourcePicker>
        )}

        {submitError && <div className="panel-form__submit-error" role="alert">{submitError}</div>}
      </form>}
    </SidePanel>
  )
}
