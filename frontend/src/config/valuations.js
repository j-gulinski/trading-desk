export const VALUATION_EVENT = 'valuation_update'
export const BOOK_RISK_EVENT = 'book_risk_update'

export const VALUATION_STALE_AFTER_MS = 10000

export const MAX_RENDERED_ROWS = 100

export const VALUATION_STATUS_LEVEL = {
  LIVE: 'info',
  MARKET_CLOSED: 'closed',
  STALE: 'stale',
  CLOSED: 'final',
  PENDING: 'unknown',
  CANCELLED: 'warning',
}

export const VALUATION_STATUS_LABEL = {
  MARKET_CLOSED: 'MKT CLOSED',
  CLOSED: 'FINAL',
}

export const VALUATION_COLUMNS = [
  {
    id: 'trade',
    label: 'Trade',
    required: true,
    sortable: true,
    defaultDirection: 'asc',
    cellClass: 'data-table__cell--key',
  },
  { id: 'book', label: 'Book', required: true, sortable: true, defaultDirection: 'asc' },
  { id: 'assetClass', label: 'Class', sortable: true, defaultDirection: 'asc' },
  { id: 'symbol', label: 'Instrument', sortable: true, defaultDirection: 'asc' },
  {
    id: 'provider',
    label: 'Pricing source',
    sortable: true,
    defaultDirection: 'asc',
  },
  {
    id: 'price',
    label: 'Current value',
    sortable: true,
    snapshot: true,
    defaultDirection: 'desc',
    numeric: true,
    headerNote: 'asset unit',
  },
  {
    id: 'fairValue',
    label: 'Position value',
    required: true,
    sortable: true,
    snapshot: true,
    defaultDirection: 'desc',
    numeric: true,
    headerNote: 'native currency',
  },
  {
    id: 'notional',
    label: 'Gross entry',
    required: true,
    sortable: true,
    snapshot: true,
    defaultDirection: 'desc',
    numeric: true,
    headerNote: 'native currency',
  },
  {
    id: 'unrealized',
    label: 'Unrealized PnL',
    required: true,
    sortable: true,
    snapshot: true,
    defaultDirection: 'desc',
    numeric: true,
    headerNote: 'native · ≈ USD sort',
  },
  {
    id: 'return',
    label: 'Return on entry',
    sortable: true,
    snapshot: true,
    defaultDirection: 'desc',
    numeric: true,
    headerNote: 'on gross entry',
  },
  {
    id: 'updated',
    label: 'Valued at',
    sortable: true,
    snapshot: true,
    defaultDirection: 'desc',
    numeric: true,
    headerClass: 'data-table__cell--time',
    cellClass: 'data-table__cell--time',
  },
  { id: 'valuation', label: 'Valuation status', sortable: true, snapshot: true, defaultDirection: 'desc' },
]

export const DEFAULT_VALUATION_SORT = { column: 'unrealized', direction: 'desc' }

export const VALUATION_FALLBACK_SORT = { column: 'trade', direction: 'asc' }

export const VALUATION_CURRENCY_SORT_COLUMNS = new Set([
  'fairValue',
  'notional',
  'unrealized',
  'realized',
])
