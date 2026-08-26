export const STREAM_EVENTS = ['market_tick', 'market_remove', 'curve_tick']

export const CURVE_PALETTE = [
  'var(--accent)',
  'var(--info)',
  'var(--pos)',
  'var(--warn)',
  'var(--neg)',
  'var(--text-secondary)',
]

export const CURVE_BASIS_TEXT = {
  GOVERNMENT_BONDS: 'Government bonds',
  INTEREST_RATE_SWAPS: 'Interest-rate swaps',
  OVERNIGHT_INDEX: 'Overnight index swaps',
  INTERBANK_COMPOSITE: 'Interbank + government reference rates',
}

export const CURVE_TEXT = {
  EUR_RISK_FREE: {
    title: 'Risk-free',
    tradeUse: 'Bond, IRS and option pricing',
    cadence: 'monthly',
    hint: 'The euro discount curve a rates desk would expect. Points past the publisher’s last liquid maturity are extrapolated, not observed',
  },
  USD_RISK_FREE: {
    title: 'Risk-free',
    tradeUse: 'Bond, IRS and option pricing',
    cadence: 'monthly',
    hint: 'The dollar discount curve a rates desk would expect, quoted far enough out that none of its points is extrapolated',
  },
  PLN_RISK_FREE: {
    title: 'Risk-free',
    tradeUse: 'Bond, IRS and option pricing',
    cadence: 'monthly',
    hint: 'The zloty risk-free curve. Its publisher derives Poland from government bonds because the Polish swap market is not liquid enough to derive one from swaps, and points past ten years are extrapolated',
  },
  EUR_GOVERNMENT_BONDS_AAA: {
    title: 'Government bonds · AAA',
    tradeUse: 'Bond pricing',
    cadence: 'daily',
    hint: 'The euro area yield curve fitted to sovereign bonds rated AAA',
  },
  EUR_GOVERNMENT_BONDS_ALL: {
    title: 'Government bonds · all ratings',
    tradeUse: 'Bond pricing',
    cadence: 'daily',
    hint: 'The same euro area fit taken over sovereign bonds of every rating. Its distance from the AAA curve is the credit quality spread',
  },
  USD_GOVERNMENT_BONDS: {
    title: 'Government bonds',
    tradeUse: 'Bond pricing',
    cadence: 'daily',
    hint: 'United States Treasury constant maturity yields from one month to thirty years. The desk reads these par yields as zero rates',
  },
  PLN_REFERENCE_PROJECTION_3M: {
    title: 'Reference projection · 3M',
    tradeUse: '3M PLN IRS projection',
    cadence: 'monthly',
    hint: 'Two monthly reference rates with the maturities between them interpolated. Published about two months behind, and the only curve here that follows a floating leg’s own index',
  },
}

export const CURVE_ROLE_HINTS = {
  discount_curve:
    'Turns each future cashflow into today’s money — the rate at each tenor sets what money promised then is worth now',
  projection_curve:
    'Sets the floating leg’s cashflows — forward rates implied by this curve stand in for index fixings that have not happened yet',
}

export const TRADE_CURVE_ROLE_TEXT = {
  BOND: {
    discount_curve: 'Discounts coupons and principal',
  },
  IRS: {
    discount_curve: 'Discounts both swap legs',
    projection_curve: 'Projects the floating leg',
  },
  EUROPEAN_OPTION: {
    discount_curve: 'Discounts the strike payment',
  },
}

export const WATCHLIST_POLL_INTERVAL_MS = 10000

export const SYMBOL_SEARCH_DEBOUNCE_MS = 400

export const SYMBOL_SEARCH_MIN_CHARS = 2

export const SYMBOL_SEARCH_SHOWN_LIMIT = 8

export const PROVIDERS_POLL_INTERVAL_MS = 5000

export const FX_RATES_REFRESH_MS = 60000

export const REPORTING_CURRENCY_BASE_OPTIONS = ['EUR', 'PLN', 'USD']

export const FRESHNESS_PILL_LEVELS = {
  LIVE: 'info',
  STALE: 'stale',
  CLOSED: 'closed',
  MISSING: 'degraded',
  UNSUPPORTED: 'unknown',
}

export const FRESHNESS_LABELS = {
  LIVE: 'LIVE',
  STALE: 'STALE',
  CLOSED: 'CLOSED',
  MISSING: 'NO DATA',
  UNSUPPORTED: 'N/A',
}

export const FRESHNESS_HINTS = {
  LIVE: 'Provider timestamp is inside this feed’s freshness budget',
  STALE: 'Older than the freshness budget — the provider has not moved this price',
  CLOSED: 'Market is closed; the last session close is the current price',
  MISSING: 'Watched, but this provider has not returned a quote yet',
  UNSUPPORTED: 'This provider does not quote this asset class',
}

export function freshnessLabelOf(state, grade) {
  if (grade === 'REFERENCE' && state === 'LIVE') return 'CURRENT'
  return FRESHNESS_LABELS[state] ?? state
}

export function freshnessHintOf(state, grade) {
  if (grade === 'REFERENCE') {
    if (state === 'LIVE') {
      return 'Official fixing — current until the source’s next expected publication'
    }
    if (state === 'STALE') {
      return 'The source missed its expected publication — the fixing is overdue'
    }
  }
  return FRESHNESS_HINTS[state]
}

export const MARKET_COLUMNS = [
  {
    id: 'symbol',
    label: 'Symbol',
    required: true,
    sortable: true,
    defaultDirection: 'asc',
    cellClass: 'data-table__cell--key',
    reorderGroup: 'identity',
    reorderLocked: true,
  },
  {
    id: 'name',
    label: 'Name',
    required: true,
    sortable: true,
    defaultDirection: 'asc',
    reorderGroup: 'identity',
    reorderLocked: true,
  },
  {
    id: 'assetClass',
    label: 'Class',
    sortable: true,
    defaultDirection: 'asc',
    reorderGroup: 'identity',
    reorderLocked: true,
  },
  {
    id: 'market',
    label: 'Market',
    sortable: true,
    defaultDirection: 'asc',
    reorderGroup: 'identity',
    reorderLocked: true,
  },
  {
    id: 'provider',
    label: 'Provider',
    cellClass: 'market-provider-cell',
    reorderGroup: 'observation',
  },
  {
    id: 'last',
    label: 'Mark',
    numeric: true,
    headerNote: 'quote currency',
    reorderGroup: 'observation',
  },
  {
    id: 'todayChange',
    label: 'Day move',
    numeric: true,
    headerNote: 'vs prior close',
    reorderGroup: 'observation',
  },
  {
    id: 'tickChange',
    label: 'Tick move',
    sortable: false,
    numeric: true,
    headerNote: 'vs last update',
    reorderGroup: 'observation',
  },
  {
    id: 'feed',
    label: 'Status',
    reorderGroup: 'observation',
  },
  {
    id: 'age',
    label: 'Quote age',
    numeric: true,
    headerNote: 'provider time',
    reorderGroup: 'observation',
  },
  {
    id: 'updated',
    label: 'Received',
    numeric: true,
    headerClass: 'data-table__cell--time',
    cellClass: 'data-table__cell--time',
    reorderGroup: 'observation',
  },
  {
    id: 'watch',
    label: '',
    sortable: false,
    headerClass: 'market-cell--watch',
    cellClass: 'market-cell--watch',
    reorderGroup: 'observation',
  },
]

const MARKET_COLUMNS_HIDDEN_BY_DEFAULT = ['updated']

export const DEFAULT_MARKET_COLUMNS = MARKET_COLUMNS.filter(
  (column) => !MARKET_COLUMNS_HIDDEN_BY_DEFAULT.includes(column.id),
).map((column) => column.id)

export const DEFAULT_MARKET_SORT = { column: 'symbol', direction: 'asc' }

export const MARKET_FALLBACK_SORT = { column: 'symbol', direction: 'asc' }
