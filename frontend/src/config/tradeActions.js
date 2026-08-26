export const QUEUE_POLL_INTERVAL_MS = 2000
export const FEED_POLL_INTERVAL_MS = 3000
export const TICKET_OPTIONS_POLL_INTERVAL_MS = 5000

export const FEED_LIMIT = 50
export const TRADE_QUANTITY_BOUNDS = { min: 1, max: 1000000 }
export const CURVE_PRICED_ASSET_CLASSES = ['BOND', 'IRS', 'EUROPEAN_OPTION']

const ASSET_CLASS_NAMES = {
  EQUITY: 'Equity',
  FX: 'Foreign exchange',
  COMMODITY: 'Commodity',
  BOND: 'Bond',
  IRS: 'Interest rate swap',
  EUROPEAN_OPTION: 'European option',
}

export function assetClassLabel(assetClass) {
  return ASSET_CLASS_NAMES[assetClass] ?? String(assetClass ?? '').replaceAll('_', ' ')
}
export const FEED_SERVICE = 'trade-action-service'
export const FEED_EVENT_TYPES = [
  'TRADE_CREATED',
  'TRADE_CLOSED',
  'TRADE_REASSIGNED',
  'ACTION_REJECTED',
]
