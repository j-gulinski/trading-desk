import { REPORTING_CURRENCY_BASE_OPTIONS } from '../config/marketData.js'
import { toNum } from './values.js'

export function fxConversionOf(rateInfo, currency, toCurrency) {
  if (currency === toCurrency) {
    return { rate: 1, identity: true, label: null, reason: null }
  }
  const rate = toNum(rateInfo?.rate)
  if (rate == null) {
    return {
      rate: null,
      identity: false,
      label: null,
      reason: rateInfo?.reason ?? `no official ${currency}→${toCurrency} rate is published`,
    }
  }
  return {
    rate,
    identity: false,
    label: `${rateInfo.path} ${rateInfo.rate} · ${rateInfo.provider} · as of ${rateInfo.as_of}`,
    reason: null,
  }
}

export function convertedValueOf(value, currency, rates, toCurrency) {
  if (!Number.isFinite(value) || !currency || !toCurrency) return null
  const conversion = fxConversionOf(rates?.[currency], currency, toCurrency)
  return conversion.rate == null ? null : value * conversion.rate
}

export function convertedTotalsOf(subtotals, rates, toCurrency, metricIds) {
  const totals = Object.fromEntries(metricIds.map((id) => [id, 0]))
  const applied = []
  const excluded = []
  for (const row of subtotals) {
    const conversion = fxConversionOf(rates?.[row.currency], row.currency, toCurrency)
    if (conversion.rate == null) {
      excluded.push({ currency: row.currency, reason: conversion.reason })
      continue
    }
    for (const id of metricIds) {
      totals[id] += (row.values[id] ?? 0) * conversion.rate
    }
    if (conversion.label) applied.push(conversion.label)
  }
  return { totals, applied, excluded }
}

export function reportedTotalsOf(
  { subtotals, currency, values }, rates, toCurrency, metricIds,
) {
  if (currency != null && (!toCurrency || currency === toCurrency)) {
    return { values, currency }
  }
  if (!toCurrency) return { values: null, currency: 'MIXED' }
  if (rates == null) return { values: null, currency: toCurrency }
  const source = subtotals.length > 0
    ? subtotals
    : [{ currency, values }]
  const converted = convertedTotalsOf(source, rates, toCurrency, metricIds)
  if (converted.excluded.length > 0) {
    return {
      values: null,
      currency: toCurrency,
      title: converted.excluded.map((row) => row.reason).join('; '),
    }
  }
  return {
    values: converted.totals,
    currency: toCurrency,
    title: converted.applied.join('; '),
  }
}

export function reportingCurrencyOptions(subtotals) {
  const options = new Set(REPORTING_CURRENCY_BASE_OPTIONS)
  for (const row of subtotals) options.add(row.currency)
  return [...options].sort()
}
