import { useMarketFeed } from '../hooks/useMarketFeed.js'
import { useValuationFeed } from '../hooks/useValuationFeed.js'
import { MarketFeedContext, ValuationFeedContext } from './feedContext.js'

export function FeedProvider({ children }) {
  const marketFeed = useMarketFeed()
  const valuationFeed = useValuationFeed()

  return (
    <MarketFeedContext.Provider value={marketFeed}>
      <ValuationFeedContext.Provider value={valuationFeed}>
        {children}
      </ValuationFeedContext.Provider>
    </MarketFeedContext.Provider>
  )
}
