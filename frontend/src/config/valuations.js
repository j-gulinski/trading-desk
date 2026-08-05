export const VALUATION_EVENT = 'valuation_update'

export const VALUATION_STALE_AFTER_MS = 10000

export const MAX_RENDERED_ROWS = 100

export const VALUATION_STATUS_LEVEL = {
  LIVE: 'info',
  STALE: 'stale',
  CLOSED: 'unknown',
  PENDING: 'unknown',
  CANCELLED: 'warning',
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
  { id: 'symbol', label: 'Symbol', sortable: true, defaultDirection: 'asc' },
  {
    id: 'price',
    label: 'Mark',
    sortable: true,
    snapshot: true,
    defaultDirection: 'desc',
    numeric: true,
    headerNote: 'valuation input',
  },
  {
    id: 'fairValue',
    label: 'Fair value',
    required: true,
    sortable: true,
    snapshot: true,
    defaultDirection: 'desc',
    numeric: true,
  },
  {
    id: 'unrealized',
    label: 'Unrealized',
    required: true,
    sortable: true,
    snapshot: true,
    defaultDirection: 'desc',
    numeric: true,
    headerNote: 'open PnL',
  },
  {
    id: 'return',
    label: 'Return',
    sortable: true,
    snapshot: true,
    defaultDirection: 'desc',
    numeric: true,
    headerNote: 'on notional',
  },
  {
    id: 'updated',
    label: 'Updated',
    sortable: true,
    snapshot: true,
    defaultDirection: 'desc',
    numeric: true,
    headerClass: 'data-table__cell--time',
    cellClass: 'data-table__cell--time',
  },
  { id: 'valuation', label: 'Valuation', sortable: true, snapshot: true, defaultDirection: 'desc' },
]

export const DEFAULT_VALUATION_SORT = { column: 'unrealized', direction: 'desc' }

export const VALUATION_FALLBACK_SORT = { column: 'trade', direction: 'asc' }


export const ALPHA_BETA_UNAVAILABLE = 'Pricing does not publish book alpha/beta yet'
