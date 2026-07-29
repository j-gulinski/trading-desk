import { createContext, useContext } from 'react'

export const MarketFeedContext = createContext(null)

export const ValuationFeedContext = createContext(null)

function useFeed(context, label) {
  const feed = useContext(context)
  if (feed == null) throw new Error(`${label} feed must be used inside FeedProvider`)
  return feed
}

export function useMarketFeedContext() {
  return useFeed(MarketFeedContext, 'Market')
}

export function useValuationFeedContext() {
  return useFeed(ValuationFeedContext, 'Valuation')
}
