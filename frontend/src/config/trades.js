export const BLOTTER_POLL_INTERVAL_MS = 5000

export const TRADE_PAGE_SIZE = 50

export const TRADE_HISTORY_FETCH_LIMIT = 250

export const TRADE_COLUMNS = [
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
  { id: 'side', label: 'Side', sortable: true, defaultDirection: 'asc' },
  {
    id: 'quantity',
    label: 'Qty',
    sortable: true,
    defaultDirection: 'desc',
    numeric: true,
  },
  {
    id: 'entry',
    label: 'Entry',
    sortable: true,
    defaultDirection: 'desc',
    numeric: true,
  },
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
    id: 'pnl',
    label: 'PnL',
    required: true,
    sortable: true,
    snapshot: true,
    defaultDirection: 'desc',
    numeric: true,
    headerNote: 'realized once closed',
  },
  {
    id: 'return',
    label: 'Return',
    sortable: true,
    snapshot: true,
    defaultDirection: 'desc',
    numeric: true,
    headerNote: 'unrealized only',
  },
  {
    id: 'opened',
    label: 'Opened',
    sortable: true,
    defaultDirection: 'desc',
    numeric: true,
    headerClass: 'data-table__cell--time',
    cellClass: 'data-table__cell--time',
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
  {
    id: 'valuation',
    label: 'Valuation',
    required: true,
    sortable: true,
    snapshot: true,
    defaultDirection: 'desc',
  },
]

export const DEFAULT_TRADE_COLUMNS = [
  'trade',
  'book',
  'assetClass',
  'side',
  'quantity',
  'entry',
  'fairValue',
  'pnl',
  'valuation',
]

export const DEFAULT_TRADE_SORT = { column: 'pnl', direction: 'desc' }

export const TRADE_FALLBACK_SORT = { column: 'trade', direction: 'asc' }
