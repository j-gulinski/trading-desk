import { useCallback, useState } from 'react'
import { apiDelete, apiGet, apiPost } from '../services/apiClient.js'
import { endpoints } from '../services/endpoints.js'
import { usePolling } from './usePolling.js'
import { WATCHLIST_POLL_INTERVAL_MS } from '../config/marketData.js'
import { instrumentId } from '../domain/marketData.js'
import { announceWatchlistChange } from '../services/watchlistEvents.js'

function messageOf(error) {
  return error?.body?.error ?? error?.message ?? 'Request failed'
}

export function useWatchlist() {
  const [addError, setAddError] = useState(null)
  const [removeError, setRemoveError] = useState(null)
  const [refreshError, setRefreshError] = useState(null)
  const [busyKey, setBusyKey] = useState(null)
  const [refreshingKey, setRefreshingKey] = useState(null)

  const { data, loading, error, refetch } = usePolling(
    ({ signal }) => apiGet(endpoints.marketData.watchlist, { signal }),
    { intervalMs: WATCHLIST_POLL_INTERVAL_MS },
  )

  const add = useCallback(
    async (result, providers) => {
      setBusyKey(result.symbol)
      setAddError(null)
      try {
        await apiPost(endpoints.marketData.watchlist, {
          symbol: result.symbol,
          name: result.name,
          asset_class: result.asset_class,
          currency: result.currency,
          market: result.market ?? result.exchange,
          providers,
        })
        announceWatchlistChange()
        refetch()
        return true
      } catch (err) {
        setAddError(messageOf(err))
        return false
      } finally {
        setBusyKey(null)
      }
    },
    [refetch],
  )

  const remove = useCallback(
    async (symbol, provider) => {
      setBusyKey(instrumentId(provider, symbol))
      setRemoveError(null)
      try {
        const result = await apiDelete(
          endpoints.marketData.watchlistItem(symbol, provider),
        )
        announceWatchlistChange()
        refetch()
        return result
      } catch (err) {
        setRemoveError(messageOf(err))
        return null
      } finally {
        setBusyKey(null)
      }
    },
    [refetch],
  )

  const refresh = useCallback(async (symbol, provider) => {
    const key = instrumentId(provider, symbol)
    setRefreshingKey(key)
    setRefreshError(null)
    try {
      await apiPost(endpoints.marketData.refresh(symbol, provider), {})
      return true
    } catch (err) {
      setRefreshError({ symbol, provider, message: messageOf(err) })
      return false
    } finally {
      setRefreshingKey(null)
    }
  }, [])

  return {
    items: Array.isArray(data) ? data : [],
    loading,
    error,
    add,
    remove,
    refresh,
    busyKey,
    refreshingKey,
    addError,
    removeError,
    refreshError,
    clearAddError: () => setAddError(null),
    clearRemoveError: () => setRemoveError(null),
    clearRefreshError: () => setRefreshError(null),
  }
}
