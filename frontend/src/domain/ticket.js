import { providerLabel } from '../config/providers.js'
import {
  FRESHNESS_HINTS,
  freshnessHintOf,
  freshnessLabelOf,
  freshnessPillLevelOf,
} from '../config/marketData.js'
import { TRADE_QUANTITY_BOUNDS } from '../config/tradeActions.js'
import { curveTitle } from './curves.js'
import {
  directionOf,
  formatAmount,
  formatClockTime,
  formatDateTime,
  formatLongDate,
  formatNumber,
  formatSignedAmount,
  formatUnitPrice,
} from './formatting.js'
import { formatAge } from './marketFormat.js'
import { irsDirectionLabel } from './trades.js'

export function hasTermField(schema, name) {
  return schema?.fields?.some((field) => field.name === name) === true
}

export function isCustomTicket(schema) {
  return schema?.customizable === true
}

export function selectedModelOf(schema, terms = {}) {
  const name = terms.model ?? schema?.default_model ?? schema?.model
  return (schema?.models ?? []).find((model) => model.name === name) ?? null
}

export function ticketFieldsOf(schema, terms = {}) {
  const fields = (schema?.fields ?? []).filter((field) => field.hidden !== true)
  const model = selectedModelOf(schema, terms)
  if (model?.needs_curve === false) {
    return fields.filter((field) => field.name !== 'discount_curve' && field.name !== 'projection_curve')
  }
  return fields
}

const SIZE_TERM_LABEL = {
  face_value: 'FACE AMOUNT',
  notional: 'NOTIONAL',
}

export function quantityLabelOf(schema, assetClass) {
  return SIZE_TERM_LABEL[schema?.size_term]
    ?? (assetClass === 'FX' ? 'NOTIONAL (BASE CURRENCY)' : 'QUANTITY')
}

export function submitActionOf({ side, valid }) {
  if (!valid) return 'Submit trade'
  if (side === 'SELL') return 'Submit sell'
  if (side === 'BUY') return 'Submit buy'
  return 'Submit trade'
}

function bondPricePer100(price, faceValue) {
  return Number.isFinite(price) && Number.isFinite(faceValue) && faceValue > 0
    ? price / faceValue * 100
    : null
}

function parPositionOf(per100) {
  if (per100 == null) return null
  if (per100 > 100.005) return 'above par'
  if (per100 < 99.995) return 'below par'
  return 'near par'
}

function quotePill(quote) {
  if (quote == null) return null
  return {
    level: freshnessPillLevelOf(quote.state, quote.grade),
    label: freshnessLabelOf(quote.state, quote.grade, quote.providerTimestamp),
    title: quote.reason ?? freshnessHintOf(quote.state, quote.grade) ?? FRESHNESS_HINTS[quote.state],
  }
}

function curvePill(curve) {
  if (curve == null) return null
  if (curve.stale === true) {
    return {
      level: 'stale',
      label: 'STALE CURVE',
      title: `Stale by this curve’s ${curve.stale_after_days}-day limit`,
    }
  }
  return { level: 'info', label: 'MODEL', title: 'Model value from the selected curve' }
}

function quoteSourceText(quote, now) {
  const when = quote.atMs != null
    ? `${formatClockTime(quote.atMs)} · ${formatAge(now - quote.atMs)} old`
    : 'no timestamp'
  return `${providerLabel(quote.provider)} · ${when}`
}

function curveText(curve) {
  return `${curve.currency} ${curveTitle(curve)} · ${providerLabel(curve.provider)} · ${formatLongDate(curve.as_of_date)}`
}

function modelTime(preview) {
  return preview?.atMs != null ? { label: 'Model time', value: formatDateTime(preview.atMs) } : null
}

function spotValue({ assetClass, side, quantity, quote, unitLabel, quantityUnit, now }) {
  const price = quote?.price ?? null
  const currency = quote?.currency ?? ''
  return {
    label: `${side === 'SELL' ? 'SELL' : 'BUY'} AT`,
    hint: null,
    value: price != null ? formatUnitPrice(price, assetClass) : null,
    unit: price != null ? unitLabel ?? currency : null,
    tone: null,
    pill: quotePill(quote),
    total: price != null && Number.isFinite(quantity)
      ? `${formatAmount(price * quantity)} ${currency}`.trim()
      : null,
    totalNote: Number.isFinite(quantity)
      ? `for ${formatNumber(quantity)} ${quantityUnit ?? ''}`.trim()
      : null,
    assumptions: price == null ? [] : [
      { label: 'Source', value: quoteSourceText(quote, now) },
      quote.bid != null && quote.ask != null
        ? {
            label: 'Bid / ask',
            value: `${formatUnitPrice(quote.bid, assetClass)} / ${formatUnitPrice(quote.ask, assetClass)}`,
          }
        : { label: 'Basis', value: quote.last != null ? `last ${formatUnitPrice(quote.last, assetClass)}` : 'mid' },
    ],
  }
}

function premiumValue({ terms, quantity, preview, quote, curve, currency, volatility, now, model }) {
  const price = preview?.price ?? null
  const intrinsic = (model ?? terms.model) === 'INTRINSIC'
  if (intrinsic) {
    return {
      label: 'INTRINSIC PREMIUM / CONTRACT',
      hint: 'Payoff of a one-unit contract from the underlying mid and strike. A call pays max(spot − strike, 0); a put pays max(strike − spot, 0). No volatility or discount curve.',
      value: price != null ? formatAmount(price, 2) : null,
      unit: price != null ? currency : null,
      tone: null,
      pill: quotePill(quote),
      total: price != null && Number.isFinite(quantity)
        ? `${formatAmount(price * quantity)} ${currency ?? ''}`.trim()
        : null,
      totalNote: Number.isFinite(quantity)
        ? `for ${formatNumber(quantity)} ${quantity === 1 ? 'contract' : 'contracts'}`
        : null,
      assumptions: [
        quote?.price != null
          ? {
              label: 'Underlying',
              value: `${terms.underlying_symbol} ${formatAmount(quote.price, 2)} ${quote.currency ?? ''} · ${quoteSourceText(quote, now)}`,
            }
          : null,
        modelTime(preview),
      ].filter(Boolean),
    }
  }
  const volatilityText = `${formatNumber(volatility * 100)}%`
  return {
    label: 'MODEL PREMIUM / CONTRACT',
    hint: `Model premium for a one-unit contract using the underlying mid, strike, time, ${volatilityText} volatility and the selected discount curve. Higher rates usually raise calls and reduce puts.`,
    value: price != null ? formatAmount(price, 2) : null,
    unit: price != null ? currency : null,
    tone: null,
    pill: quotePill(quote),
    total: price != null && Number.isFinite(quantity)
      ? `${formatAmount(price * quantity)} ${currency ?? ''}`.trim()
      : null,
    totalNote: Number.isFinite(quantity)
      ? `for ${formatNumber(quantity)} ${quantity === 1 ? 'contract' : 'contracts'}`
      : null,
    assumptions: [
      { label: 'Volatility', value: `${volatilityText} · fixed model input` },
      quote?.price != null
        ? {
            label: 'Underlying',
            value: `${terms.underlying_symbol} ${formatAmount(quote.price, 2)} ${quote.currency ?? ''} · ${quoteSourceText(quote, now)}`,
          }
        : null,
      curve ? { label: 'Discount curve', value: curveText(curve) } : null,
      modelTime(preview),
    ].filter(Boolean),
  }
}

function swapValue({ terms, preview, curve, currency }) {
  const price = preview?.price ?? null
  const receiveFixed = terms.direction === 'RECEIVE_FIXED_PAY_FLOAT'
  return {
    label: 'NET PRESENT VALUE',
    hint: `${receiveFixed ? 'Fixed leg less floating leg' : 'Floating leg less fixed leg'} for the stated notional. Higher projected floating rates usually ${receiveFixed ? 'reduce' : 'increase'} this value.`,
    value: price != null ? formatSignedAmount(price) : null,
    unit: price != null ? currency : null,
    tone: price != null ? directionOf(price) : null,
    pill: curvePill(curve),
    total: null,
    totalNote: null,
    assumptions: [
      Number.isFinite(Number(terms.notional))
        ? {
            label: 'Notional',
            value: `${formatNumber(Number(terms.notional))} ${currency ?? ''} · ${irsDirectionLabel(terms.direction)}`,
          }
        : null,
      preview != null && Number.isFinite(preview.parRate)
        ? { label: 'Fair fixed rate', value: `${preview.parRate.toFixed(4)}%` }
        : null,
      preview != null && Number.isFinite(preview.fixedLegValue)
        ? { label: 'Fixed leg', value: `${formatAmount(preview.fixedLegValue)} ${currency ?? ''}` }
        : null,
      preview != null && Number.isFinite(preview.floatingLegValue)
        ? { label: 'Floating leg', value: `${formatAmount(preview.floatingLegValue)} ${currency ?? ''}` }
        : null,
      curve ? { label: 'Curve', value: curveText(curve) } : null,
      modelTime(preview),
    ].filter(Boolean),
  }
}

function bondValue({ terms, preview, curve, currency }) {
  const price = preview?.price ?? null
  const face = Number(terms.face_value)
  const per100 = bondPricePer100(price, face)
  return {
    label: 'PRICE / 100 FACE',
    hint: 'Price normalized to 100 face from the present value of coupons and principal. Higher discount rates reduce it; lower rates raise it.',
    value: per100 != null ? formatAmount(per100, 2) : null,
    unit: per100 != null ? `${currency ?? ''} / 100 face`.trim() : null,
    tone: null,
    pill: curvePill(curve),
    total: price != null ? `${formatAmount(price)} ${currency ?? ''}`.trim() : null,
    totalNote: price != null
      ? `for ${formatNumber(face)} face · ${parPositionOf(per100)}`
      : null,
    assumptions: [
      curve ? { label: 'Discount curve', value: curveText(curve) } : null,
      modelTime(preview),
    ].filter(Boolean),
  }
}

function modelValue({ preview, curve, currency }) {
  const price = preview?.price ?? null
  return {
    label: 'MODEL VALUE',
    hint: null,
    value: price != null ? formatSignedAmount(price) : null,
    unit: price != null ? currency : null,
    tone: null,
    pill: curvePill(curve),
    total: null,
    totalNote: null,
    assumptions: [
      curve ? { label: 'Curve', value: curveText(curve) } : null,
      modelTime(preview),
    ].filter(Boolean),
  }
}

const MODEL_VALUE_BY_KIND = {
  bond: bondValue,
  swap: swapValue,
  premium: premiumValue,
}

export function ticketValueOf(input) {
  if (!isCustomTicket(input.schema)) return spotValue(input)
  const model = selectedModelOf(input.schema, input.terms)?.name
  return (MODEL_VALUE_BY_KIND[input.schema.ticket_kind] ?? modelValue)({ ...input, model })
}

export function ackSummaryOf({ schema, side, quantity, symbol, terms, currency }) {
  const kind = schema?.ticket_kind
  if (kind === 'swap') {
    return `${irsDirectionLabel(terms.direction)} · ${currency} IRS · notional ${formatNumber(Number(terms.notional))}`
  }
  if (kind === 'bond') {
    return `${side} · ${currency} bond · face ${formatNumber(Number(terms.face_value))}`
  }
  if (kind === 'premium') {
    return `${side} ${formatNumber(quantity)} × ${terms.underlying_symbol} ${terms.option_type?.toLowerCase()} option`
  }
  return `${side} ${formatNumber(quantity)} × ${symbol}`
}

export function ticketErrorsOf({
  bookId,
  schema,
  schemaError,
  symbol,
  termsComplete,
  staleCurves,
  staleAcknowledged,
  hasQuoteInstrument,
  quote,
  quantity,
  previewPrice,
  previewError,
}) {
  const errors = {}
  if (!bookId) errors.book = 'Pick a book.'
  if (schema == null) {
    if (bookId) {
      errors.terms = schemaError
        ? 'Ticket configuration unavailable.'
        : 'Ticket configuration unavailable.'
    }
    return errors
  }
  const modelPriced = isCustomTicket(schema)
  if (!modelPriced && !symbol) errors.instrument = 'Pick an instrument.'
  if (modelPriced && !termsComplete) errors.terms = 'Fill in every term.'
  else if (modelPriced && staleCurves.length > 0 && !staleAcknowledged) {
    errors.terms = 'Acknowledge the stale curve before submitting this trade.'
  }
  if (schema.needs_quote && hasQuoteInstrument) {
    if (quote == null) {
      errors.provider = modelPriced ? 'Pick a price source for the underlying.' : 'Pick a price source.'
    } else if (quote.state === 'STALE') {
      errors.provider = 'This quote is stale. Wait for the provider to update.'
    } else if (!quote.tradeable) {
      errors.provider = `${providerLabel(quote.provider)} cannot ${modelPriced ? 'price this contract' : 'fill this trade'} right now.`
    }
  }
  if (schema.fixed_quantity == null) {
    const whole = schema.whole_quantity === true
    if (
      !Number.isFinite(quantity) ||
      (whole && !Number.isSafeInteger(quantity)) ||
      quantity < TRADE_QUANTITY_BOUNDS.min ||
      quantity > TRADE_QUANTITY_BOUNDS.max
    ) {
      errors.quantity = `${whole ? 'Quantity must be a whole number' : 'Amount must be'} between ${formatNumber(
        TRADE_QUANTITY_BOUNDS.min,
      )} and ${formatNumber(TRADE_QUANTITY_BOUNDS.max)}.`
    }
  }
  if (modelPriced && previewPrice == null) {
    errors.preview = previewError ?? 'Waiting for the current model value.'
  }
  return errors
}
