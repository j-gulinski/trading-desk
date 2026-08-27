import { useEffect, useMemo, useRef, useState } from 'react'
import SidePanel from '../panel/SidePanel.jsx'
import LoadingSkeleton from '../LoadingSkeleton.jsx'
import ProviderQuoteOption from './ProviderQuoteOption.jsx'
import TermFields from './TermFields.jsx'
import NumberField from './NumberField.jsx'
import { useMarketFeedContext } from '../../providers/feedContext.js'
import { useElapsedTime } from '../../hooks/useElapsedTime.js'
import { usePolling } from '../../hooks/usePolling.js'
import { apiGet, apiPost } from '../../services/apiClient.js'
import { endpoints } from '../../services/endpoints.js'
import { onWatchlistChange } from '../../services/watchlistEvents.js'
import {
  buildCurveTradeIntent,
  buildOpenTradeIntent,
  curveChoicesFor,
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
import {
  TRADE_QUANTITY_BOUNDS,
  TICKET_OPTIONS_POLL_INTERVAL_MS,
  assetClassLabel,
} from '../../config/tradeActions.js'
import {
  formatAmount,
  formatDateTime,
  formatNumber,
  formatShortId,
  formatSignedAmount,
  formatUnitPrice,
} from '../../domain/formatting.js'
import { unitLabelOf } from '../../domain/marketFormat.js'
import { irsDirectionLabel } from '../../domain/trades.js'

function FieldError({ id, message }) {
  if (!message) return null
  return (
    <span id={id} className="panel-form__error" role="alert">
      {message}
    </span>
  )
}

function ExecutionFields({
  assetClass,
  bond,
  side,
  quantityText,
  quantityError,
  onSideChange,
  onQuantityChange,
}) {
  return (
    <div className="panel-form__execution-row">
      <div className="panel-form__field">
        <span className="panel-form__label" id="new-trade-side-label">SIDE</span>
        <div className="panel-form__side" role="group" aria-labelledby="new-trade-side-label">
          {['BUY', 'SELL'].map((option) => (
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

      {!bond && (
        <div className="panel-form__field">
          <label className="panel-form__label" htmlFor="new-trade-quantity">
            {assetClass === 'FX' ? 'NOTIONAL (BASE CURRENCY)' : 'QUANTITY'}
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

const PREVIEW_DEBOUNCE_MS = 500
const CURVE_TERM_FIELDS = ['discount_curve', 'projection_curve']

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
  const [preview, setPreview] = useState(null)
  const [previewPending, setPreviewPending] = useState(false)
  const [previewRetry, setPreviewRetry] = useState(0)
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
  const refetchCatalog = catalogRequest.refetch
  const refetchTermSchemas = termSchemasRequest.refetch

  useEffect(
    () => onWatchlistChange(() => {
      refetchCatalog()
      refetchTermSchemas()
    }),
    [refetchCatalog, refetchTermSchemas],
  )

  const books = booksRequest.data == null ? null : bookSummariesOf(booksRequest.data)
  const catalog = catalogRequest.data == null ? null : instrumentCatalogOf(catalogRequest.data)
  const { schemas, curves } = termSchemasOf(termSchemasRequest.data)

  const bookList = (books ?? []).filter((book) => book.isActive)
  const selectedBook = bookList.find((book) => book.id === bookId) ?? null
  const assetClass = selectedBook?.assetClass
  const curvePriced = isCurvePriced(assetClass)
  const schema = curvePriced ? schemas[assetClass] ?? null : null
  const options = useMemo(
    () => curvePriced ? [] : tradeableInstrumentsOf(catalog, assetClass),
    [assetClass, catalog, curvePriced],
  )
  const instrument = options.find((option) => option.symbol === symbol) ?? null

  const termCurrency = curvePriced ? termCurrencyOf(assetClass, termValues, catalog) : null
  const isOption = assetClass === 'EUROPEAN_OPTION'
  const irs = assetClass === 'IRS'
  const bond = assetClass === 'BOND'
  const underlying = isOption
    ? (catalog ?? []).find((entry) => entry.symbol === termValues.underlying_symbol) ?? null
    : null
  const selectedStaleCurves = CURVE_TERM_FIELDS
    .map((field) => curves.find((curve) => curve.curve_name === termValues[field]))
    .filter((curve) => curve?.stale === true)

  useEffect(() => {
    if (selectedBook == null || curvePriced || catalog == null) return
    if (options.some((option) => option.symbol === symbol)) return
    setSymbol(options.length === 1 ? options[0].symbol : '')
    setProviderChoice('')
    setPreview(null)
    setErrors((current) => {
      if (current.instrument == null && current.provider == null) return current
      const next = { ...current }
      delete next.instrument
      delete next.provider
      return next
    })
  }, [catalog, curvePriced, options, selectedBook, symbol])

  const underlyingChoices = useMemo(
    () => isOption
      ? schema?.fields.find((field) => field.name === 'underlying_symbol')?.choices ?? []
      : [],
    [isOption, schema],
  )
  useEffect(() => {
    const currentUnderlying = termValues.underlying_symbol
    if (!isOption || schema == null || !currentUnderlying) return
    if (underlyingChoices.includes(currentUnderlying)) return
    setTermValues((current) => {
      if (current.underlying_symbol !== currentUnderlying) return current
      const next = { ...current }
      delete next.underlying_symbol
      delete next.settlement_currency
      CURVE_TERM_FIELDS.forEach((field) => delete next[field])
      return next
    })
    setProviderChoice('')
    setPreview(null)
    setPreviewPending(false)
    setErrors((current) => {
      if (current.provider == null && current.preview == null) return current
      const next = { ...current }
      delete next.provider
      delete next.preview
      return next
    })
  }, [isOption, schema, termValues.underlying_symbol, underlyingChoices])

  const quotes = providerQuotesOf({
    instrument: curvePriced ? underlying : instrument,
    feed: instruments,
    side: isOption ? null : side,
    now,
  })
  const priced = quotes.filter((option) => Number.isFinite(option.price))
  const provider = providerChoice || (priced.length === 1 ? priced[0].provider : '')
  const quote = quotes.find((option) => option.provider === provider) ?? null

  const unitLabel = symbol && !curvePriced ? unitLabelOf({ symbol, assetClass }) : null
  const trimmed = quantityText.trim()
  const quantity = curvePriced && (irs || bond) ? 1 : trimmed === '' ? null : Number(trimmed)
  const faceValue = Number(termValues.face_value)
  const termsComplete = termFormComplete(schema, termValues)
  const previewReady = termsComplete && (!isOption || quote?.tradeable === true)
  const termsKey = JSON.stringify(termValues)
  const underlyingQuotePrice = isOption ? quote?.price ?? null : null
  const expectedMarketRevisions = {
    spot: isOption && quote != null ? {
      provider: quote.provider,
      symbol: termValues.underlying_symbol,
      provider_timestamp: quote.providerTimestamp,
      received_at: quote.receivedAt,
    } : null,
    ...Object.fromEntries(CURVE_TERM_FIELDS.map((field) => {
      const selectedCurve = feedCurves?.[termValues[field]]
      return [field, selectedCurve == null ? null : {
        curve_name: selectedCurve.name,
        as_of_date: selectedCurve.asOfDate,
        received_at: selectedCurve.receivedAt,
      }]
    })),
  }
  const selectedMarketRevision = JSON.stringify(expectedMarketRevisions)
  const selectedCurveRevision = CURVE_TERM_FIELDS.map((field) => {
    const selectedCurve = feedCurves?.[termValues[field]]
    return `${field}:${selectedCurve?.receivedAtMs ?? ''}:${selectedCurve?.asOfDate ?? ''}`
  }).join('|')
  const previewRequestKey = JSON.stringify({
    assetClass,
    provider,
    termsKey,
    underlyingQuotePrice,
    selectedCurveRevision,
    selectedMarketRevision,
  })
  const previewCurrent = preview?.requestKey === previewRequestKey && !previewPending
  const previewPrice = previewCurrent && Number.isFinite(preview?.price) ? preview.price : null
  const bondPricePer100 = bond && previewPrice != null && Number.isFinite(faceValue) && faceValue > 0
    ? previewPrice / faceValue * 100
    : null
  const bondPricePosition = bondPricePer100 == null
    ? null
    : bondPricePer100 > 100.005
      ? 'premium'
      : bondPricePer100 < 99.995
        ? 'discount'
        : 'near par'
  const estimatedPositionValue = curvePriced
    ? previewPrice != null && Number.isFinite(quantity)
      ? previewPrice * quantity
      : null
    : Number.isFinite(quantity) && quote?.price != null
      ? quantity * quote.price
      : null
  const estimatedValueCurrency = curvePriced ? termCurrency : quote?.currency
  const previewLoading = curvePriced && previewReady && !previewCurrent

  const modelValueLabel = irs
    ? 'NET PRESENT VALUE'
    : bond
      ? 'PRICE / 100 FACE'
      : 'MODEL PREMIUM / CONTRACT'
  const modelValueHint = irs
    ? `${termValues.direction === 'RECEIVE_FIXED_PAY_FLOAT' ? 'Fixed leg less floating leg' : 'Floating leg less fixed leg'} for the stated notional. ${termValues.direction === 'RECEIVE_FIXED_PAY_FLOAT' ? 'Higher projected floating rates usually reduce this value.' : 'Higher projected floating rates usually increase this value.'}`
    : bond
      ? 'Price normalized to 100 face from the present value of coupons and principal. Higher discount rates reduce it; lower rates raise it.'
      : `Black–Scholes premium for a one-unit contract using the underlying mid, strike, time, ${formatNumber((schema?.defaults?.volatility ?? 0) * 100)}% volatility and the selected discount curve. Higher rates usually raise calls and reduce puts.`

  useEffect(() => {
    if (!curvePriced || !previewReady) {
      previewSeq.current += 1
      setPreview(null)
      setPreviewPending(false)
      return undefined
    }
    const sequence = previewSeq.current + 1
    previewSeq.current = sequence
    const controller = new AbortController()
    setPreview(null)
    setPreviewPending(true)
    let retryTimer
    const timer = setTimeout(async () => {
      try {
        const body = {
          asset_class: assetClass,
          symbol: curvePriced ? assetClass : symbol,
          terms: termValues,
          market_data_provider: provider || undefined,
          expected_market_revisions: expectedMarketRevisions,
        }
        const response = await apiPost(endpoints.pricing.price, body, {
          signal: controller.signal,
        })
        if (previewSeq.current === sequence) {
          const price = Number(response?.price)
          setPreview(Number.isFinite(price) ? {
            requestKey: previewRequestKey,
            price,
            atMs: Date.now(),
            fixedLegValue: Number(response?.fixed_leg_pv),
            floatingLegValue: Number(response?.floating_leg_pv),
            parRate: response?.par_rate == null ? null : Number(response.par_rate),
          } : null)
          if (Number.isFinite(price)) clearError('preview')
        }
      } catch (err) {
        if (previewSeq.current === sequence && !controller.signal.aborted) {
          setPreview({
            requestKey: previewRequestKey,
            error: describeApiError(err, {
              service: 'Pricing service',
              outcome: 'no model value yet.',
            }),
          })
          if (err?.status === 409) {
            retryTimer = window.setTimeout(() => {
              if (previewSeq.current === sequence) {
                setPreviewRetry((current) => current + 1)
              }
            }, 500)
          }
        }
      } finally {
        if (previewSeq.current === sequence) setPreviewPending(false)
      }
    }, PREVIEW_DEBOUNCE_MS)
    return () => {
      clearTimeout(timer)
      window.clearTimeout(retryTimer)
      controller.abort()
    }
    // The request key invalidates the old result synchronously when any model input,
    // underlying quote or selected curve revision changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [curvePriced, previewReady, previewRequestKey, previewRetry])

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
    setQuantityText('')
    setErrors({})
    setTermValues({})
    setStaleCurveAcknowledged(false)
    setPreview(null)
    setPreviewPending(false)
    setSubmitError(null)
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

  function resetTicket() {
    setBookId('')
    setSymbol('')
    setSide('BUY')
    setProviderChoice('')
    setQuantityText('')
    setTermValues({})
    setStaleCurveAcknowledged(false)
    setPreview(null)
    setPreviewPending(false)
    setErrors({})
    setSubmitError(null)
    setAck(null)
    setRequestId(newOpenTradeRequestId())
  }

  function setTerm(name, value) {
    previewSeq.current += 1
    setPreview(null)
    setPreviewPending(false)
    setStaleCurveAcknowledged(false)
    setTermValues((current) => {
      const next = { ...current, [name]: value }
      if (!isOption && CURVE_TERM_FIELDS.includes(name) && !next.settlement_currency) {
        const chosen = curves.find((curve) => curve.curve_name === value)
        if (chosen != null) next.settlement_currency = chosen.currency
      }
      if (isOption && name === 'underlying_symbol') {
        delete next.settlement_currency
        const nextUnderlying = (catalog ?? []).find((entry) => entry.symbol === value)
        CURVE_TERM_FIELDS.forEach((field) => {
          const eligible = nextUnderlying == null
            ? []
            : curveChoicesFor(
                curves,
                nextUnderlying.currency,
                field,
                next.floating_rate_index_tenor,
                assetClass,
              )
          if (eligible.some((curve) => curve.curve_name === next[field])) return
          if (eligible.length === 1) next[field] = eligible[0].curve_name
          else delete next[field]
        })
      }
      if (name === 'settlement_currency') {
        CURVE_TERM_FIELDS.forEach((field) => {
          const eligible = curveChoicesFor(
            curves,
            value,
            field,
            next.floating_rate_index_tenor,
            assetClass,
          )
          if (eligible.length === 1) next[field] = eligible[0].curve_name
          else delete next[field]
        })
      }
      if (name === 'floating_rate_index_tenor' && next.projection_curve) {
        const selected = curves.find(
          (curve) => curve.curve_name === next.projection_curve,
        )
        if (selected?.index_tenor && selected.index_tenor !== value) {
          delete next.projection_curve
        }
      }
      return next
    })
    if (isOption && name === 'underlying_symbol') setProviderChoice('')
    clearError('terms')
    clearError('preview')
  }

  function formErrorsOf() {
    if (!curvePriced) {
      return tradeFormErrorsOf({ bookId, symbol, quantity, quote, assetClass })
    }
    const next = {}
    if (!bookId) next.book = 'Pick a book.'
    if (schema == null) next.terms = 'Term schema unavailable — retrying.'
    else if (!termsComplete) next.terms = 'Fill in every term.'
    else if (selectedStaleCurves.length > 0 && !staleCurveAcknowledged) {
      next.terms = 'Acknowledge the stale curve before submitting this trade.'
    }
    if (isOption && provider === '') {
      next.provider = 'Pick a market data provider for the underlying.'
    } else if (isOption && quote?.state === 'STALE') {
      next.provider = 'This underlying quote is stale. Wait for the provider to update.'
    } else if (isOption && !quote?.tradeable) {
      next.provider = `${quote?.provider ?? 'The selected provider'} cannot price this option right now.`
    }
    if (
      !irs && !bond && (
        !Number.isFinite(quantity) ||
        (isOption && !Number.isSafeInteger(quantity)) ||
        quantity < TRADE_QUANTITY_BOUNDS.min ||
        quantity > TRADE_QUANTITY_BOUNDS.max
      )
    ) {
      next.quantity = isOption
        ? `Quantity must be a whole number between ${formatNumber(TRADE_QUANTITY_BOUNDS.min)} and ${formatNumber(TRADE_QUANTITY_BOUNDS.max)}.`
        : `Quantity must be between ${formatNumber(TRADE_QUANTITY_BOUNDS.min)} and ${formatNumber(TRADE_QUANTITY_BOUNDS.max)}.`
    }
    if (previewPrice == null) {
      next.preview = previewCurrent && preview?.error
        ? preview.error
        : 'Waiting for the current model value.'
    }
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
            side: irs ? 'BUY' : side,
            quantity,
            terms: termValues,
            currency: termCurrency,
            provider: isOption ? provider : null,
            previewPrice,
            staleCurveAcknowledged,
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
        assetClass,
        direction: termValues.direction ?? null,
        notional: termValues.notional ?? null,
        faceAmount: termValues.face_value ?? null,
        side: intent.side,
        quantity,
        symbol: intent.symbol ?? null,
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
    quote != null && !quote.tradeable ? currentFormErrors.provider : null
  )
  const submitLabel = !valid
    ? 'Submit trade intent'
    : curvePriced
      ? bond
        ? `${side} ${formatNumber(faceValue)} face of ${termCurrency} bond at ${formatAmount(bondPricePer100, 2)} ${termCurrency} / 100 face`
        : irs
          ? `OPEN ${termCurrency} IRS at model value ${formatSignedAmount(previewPrice)} ${termCurrency}`
          : `${side} ${termValues.underlying_symbol} ${termValues.option_type?.toLowerCase()} option at model premium ${formatSignedAmount(previewPrice)} ${termCurrency ?? ''}`
      : `${side} ${formatNumber(quantity)} ${symbol} at ${formatUnitPrice(quote.price, assetClass)} ${unitLabel ?? quote.currency ?? ''}`
  const ticketLoading = booksRequest.loading || catalogRequest.loading || termSchemasRequest.loading
  const executionFields = !irs && selectedBook != null ? (
    <ExecutionFields
      assetClass={assetClass}
      bond={bond}
      side={side}
      quantityText={quantityText}
      quantityError={errors.quantity}
      onSideChange={setSide}
      onQuantityChange={(next) => {
        setQuantityText(next)
        clearError('quantity')
      }}
    />
  ) : null

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
            {ack.assetClass === 'IRS'
              ? `${irsDirectionLabel(ack.direction)} · ${termCurrency} IRS · notional ${formatNumber(ack.notional)}`
              : ack.assetClass === 'BOND'
                ? `${ack.side} · ${termCurrency} bond · face ${formatNumber(ack.faceAmount)}`
                : ack.assetClass === 'EUROPEAN_OPTION'
                  ? `${ack.side} · ${termValues.underlying_symbol} ${termValues.option_type?.toLowerCase()} option`
                  : `${ack.side} ${formatNumber(ack.quantity)} × ${ack.symbol}`}
            {ack.provider != null && <> via {providerLabel(ack.provider)}</>}
            {ack.model && ' · model-priced'}
            {ack.tradeId != null && ` · trade ${formatShortId(ack.tradeId)}`}
          </span>
        </div>
        <div className="panel-form__actions">
          <button
            type="button"
            className="panel-form__cancel"
            onClick={resetTicket}
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
      wide
      roomy
      compact
      eyebrow="TRADE ACTION"
      title="New trade"
      subtitle={selectedBook?.name ?? 'Select a book to continue'}
      bodyClassName={`new-trade-panel${irs ? ' new-trade-panel--irs' : ''}`}
      dismissOnOutsideClick={false}
      onClose={onClose}
    >
      {ticketLoading ? (
        <LoadingSkeleton variant="panel" rows={8} label="Loading new trade inputs" />
      ) : <form className="panel-form__form" onSubmit={handleSubmit} noValidate>
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
                  {book.name} · {assetClassLabel(book.assetClass)}
                </option>
              ))}
            </select>
            <FieldError
              id="new-trade-book-error"
              message={booksRequest.error ? 'Books service unavailable — could not load books.' : errors.book}
            />
          </div>
        </div>

        {selectedBook != null && !curvePriced && (
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
            {executionFields}
          </div>
        )}

        {curvePriced && schema == null && (
          <p className="panel-form__note" role="status">
            {termSchemasRequest.error
              ? 'Term schemas unavailable — retrying.'
              : 'Term schema unavailable.'}
          </p>
        )}

        {curvePriced && schema != null && (
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
                    clearError('terms')
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

        {selectedBook != null && !curvePriced && options.length === 0 && (
          <p className="panel-form__note" role="status">
            {catalogRequest.error
                ? 'Instrument list unavailable — retrying.'
              : catalog == null
                ? 'Instrument list unavailable.'
                : `No ${assetClassLabel(selectedBook.assetClass)} symbol is on the watchlist — add one in Market data.`}
          </p>
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
                  side={isOption ? null : side}
                  selected={provider === option.provider}
                  now={now}
                  onSelect={selectProvider}
                />
              ))}
            </ul>
            {isOption && quote?.tradeable && Number.isFinite(quote.price) && (
              <div className="panel-form__market-choice">
                <span>
                  At-the-money reference
                  <strong>{formatAmount(quote.price, 2)} {quote.currency ?? ''}</strong>
                </span>
                <button
                  type="button"
                  onClick={() => setTerm('strike', String(quote.price))}
                >
                  Use as strike
                </button>
              </div>
            )}
            <FieldError id="new-trade-provider-error" message={providerError} />
          </div>
        )}

        <div className="panel-form__info">
          <div className="panel-form__info-row">
            <span
              className={`panel-form__info-label${
                curvePriced ? ' panel-form__info-label--hinted' : ''
              }`}
              title={curvePriced ? modelValueHint : undefined}
            >
              {curvePriced ? modelValueLabel : 'ESTIMATED PRICE'}
            </span>
            <span className="panel-form__info-value">
              {curvePriced
                ? previewLoading
                  ? <LoadingSkeleton variant="inline" label="Computing model value" />
                  : previewPrice != null
                    ? bond
                      ? `${formatAmount(bondPricePer100, 2)} ${termCurrency ?? ''} / 100 face`.trim()
                      : `${irs ? formatSignedAmount(previewPrice) : formatAmount(previewPrice, 2)} ${termCurrency ?? ''}`
                    : '—'
                : quote?.price != null
                  ? `${formatUnitPrice(quote.price, assetClass)} ${unitLabel ?? quote.currency ?? ''}`
                  : '—'}
            </span>
          </div>
          {irs && Number.isFinite(preview?.fixedLegValue) && (
            <>
              <div className="panel-form__info-row">
                <span
                  className="panel-form__info-label panel-form__info-label--hinted"
                  title="The fixed rate that would make both legs worth the same today — at this rate the swap is worth nothing"
                >
                  FAIR FIXED RATE
                </span>
                <span className="panel-form__info-value">
                  {Number.isFinite(preview.parRate) ? `${preview.parRate.toFixed(4)}%` : '—'}
                </span>
              </div>
              <div className="panel-form__info-row">
                <span className="panel-form__info-label">FIXED LEG</span>
                <span className="panel-form__info-value">
                  {formatAmount(preview.fixedLegValue)} {termCurrency ?? ''}
                </span>
              </div>
              <div className="panel-form__info-row">
                <span className="panel-form__info-label">FLOATING LEG</span>
                <span className="panel-form__info-value">
                  {formatAmount(preview.floatingLegValue)} {termCurrency ?? ''}
                </span>
              </div>
            </>
          )}
          {bondPricePosition != null && (
            <div className="panel-form__info-row">
              <span className="panel-form__info-label">POSITION VS PAR</span>
              <span className="panel-form__info-value">{bondPricePosition}</span>
            </div>
          )}
          {isOption && (
            <div className="panel-form__info-row">
              <span
                className="panel-form__info-label panel-form__info-label--hinted"
                title="Fixed model input used for every new option; it is not a live implied-volatility quote"
              >
                VOLATILITY ASSUMPTION
              </span>
              <span className="panel-form__info-value">
                {formatNumber((schema?.defaults?.volatility ?? 0) * 100)}%
              </span>
            </div>
          )}
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
          {!irs && (
            <div className="panel-form__info-row">
              <span className="panel-form__info-label">
                {curvePriced ? 'TOTAL MODEL VALUE' : 'EST. POSITION VALUE'}
              </span>
              <span className="panel-form__info-value">
                {formatAmount(estimatedPositionValue)} {estimatedValueCurrency ?? ''}
              </span>
            </div>
          )}
          <div className="panel-form__info-row">
            <span className="panel-form__info-label">ASSET CLASS</span>
            <span className="panel-form__info-value">
              {selectedBook != null ? (
                <span className="class-tag"><span className="class-tag__dot" />{assetClassLabel(selectedBook.assetClass)}</span>
              ) : '—'}
            </span>
          </div>
        </div>

        {curvePriced && previewCurrent && preview?.error && (
          <p className="panel-form__note" role="alert">{preview.error}</p>
        )}
        <FieldError id="new-trade-preview-error" message={errors.preview} />

        {submitError && <div className="panel-form__submit-error" role="alert">{submitError}</div>}

        <button type="submit" className="panel-form__submit" disabled={pending || !valid}>
          {pending ? 'Submitting…' : submitLabel}
        </button>
      </form>}
    </SidePanel>
  )
}
