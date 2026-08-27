import { toNum } from './values.js'

function conciseNumber(value) {
  return new Intl.NumberFormat('en-US', { maximumFractionDigits: 3 }).format(value)
}

export function instrumentLabelOf(instrument) {
  const terms = instrument.terms ?? instrument.contractTerms ?? {}
  const currency = instrument.currency ?? terms.settlement_currency ?? terms.currency
  const maturity = toNum(terms.maturity_years)

  if (instrument.assetClass === 'BOND') {
    const coupon = toNum(terms.coupon_rate)
    return [
      currency ? `${currency} bond` : 'Bond',
      maturity == null ? null : `${conciseNumber(maturity)}Y`,
      coupon == null ? null : `${conciseNumber(coupon)}%`,
    ].filter(Boolean).join(' · ')
  }

  if (instrument.assetClass === 'IRS') {
    const fixedRate = toNum(terms.fixed_rate)
    return [
      currency ? `${currency} IRS` : 'IRS',
      maturity == null ? null : `${conciseNumber(maturity)}Y`,
      fixedRate == null ? null : `${conciseNumber(fixedRate)}% fixed`,
    ].filter(Boolean).join(' · ')
  }

  if (instrument.assetClass === 'EUROPEAN_OPTION') {
    const underlying = terms.underlying_symbol ?? instrument.underlyingSymbol ?? instrument.symbol
    const optionType = terms.option_type?.toUpperCase()
    const strike = toNum(terms.strike)
    return [
      underlying,
      optionType,
      strike == null ? null : `K ${conciseNumber(strike)}`,
      maturity == null ? null : `${conciseNumber(maturity)}Y`,
    ].filter(Boolean).join(' · ')
  }

  return instrument.symbol ?? '—'
}
