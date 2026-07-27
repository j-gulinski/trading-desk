import { createContext, useContext } from 'react'

export const MarketFeedContext = createContext(null)

export function useMarketFeedContext() {
  const feed = useContext(MarketFeedContext)
  if (feed == null) {
    throw new Error('useMarketFeedContext must be used inside MarketFeedProvider')
  }
  return feed
}
