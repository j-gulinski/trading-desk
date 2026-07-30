import SystemOverview from '../views/SystemOverview/SystemOverview.jsx'
import Generator from '../views/Generator/Generator.jsx'
import TradeActions from '../views/TradeActions/TradeActions.jsx'
import BusinessOverview from '../views/BusinessOverview/BusinessOverview.jsx'
import MarketData from '../views/MarketData/MarketData.jsx'
import Valuations from '../views/Valuations/Valuations.jsx'
import Books from '../views/Books/Books.jsx'
import Trades from '../views/Trades/Trades.jsx'

export const ROUTES = [
  { path: '', label: 'System Overview', subtitle: 'service health, streams & errors', group: 'SYSTEM', component: SystemOverview },
  { path: 'generator', label: 'Generator', subtitle: 'trade generation control & events', group: 'SYSTEM', component: Generator },
  { path: 'trade-actions', label: 'Trade Actions', subtitle: 'order processing & throughput', group: 'SYSTEM', component: TradeActions },

  { path: 'business-overview', label: 'Business Overview', subtitle: 'top-level PnL, book risk & valuation freshness', group: 'TRADING', component: BusinessOverview },
  { path: 'market-data', label: 'Market Data', subtitle: 'live market data ticks', group: 'TRADING', component: MarketData },
  { path: 'valuations', label: 'Valuations & Risk', subtitle: 'fair value, PnL, alpha & beta', group: 'TRADING', component: Valuations },
  { path: 'books', label: 'Books', subtitle: 'manage trading books', group: 'TRADING', component: Books },
  { path: 'trades', label: 'Trades & PnL', subtitle: 'operational blotter — trades, valuations & audit', group: 'TRADING', component: Trades },
]

export const GROUP_ORDER = ['SYSTEM', 'TRADING']

export function findRoute(path) {
  return ROUTES.find((r) => r.path === path) ?? ROUTES[0]
}
