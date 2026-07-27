import { useMarketFeed } from '../hooks/useMarketFeed.js'
import { MarketFeedContext } from './marketFeedContext.js'

export function MarketFeedProvider({ children }) {
  const feed = useMarketFeed()

  return <MarketFeedContext.Provider value={feed}>{children}</MarketFeedContext.Provider>
}
