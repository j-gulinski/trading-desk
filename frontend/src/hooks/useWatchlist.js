import { useCallback, useState } from 'react'
import { apiDelete, apiGet, apiPost } from '../services/apiClient.js'
import { endpoints } from '../services/endpoints.js'
import { usePolling } from './usePolling.js'
import { WATCHLIST_POLL_INTERVAL_MS } from '../config/marketData.js'
import { instrumentId } from '../domain/marketData.js'

function messageOf(error) {
  return error?.body?.error ?? error?.message ?? 'Request failed'
}

export function useWatchlist() {
  const [addError, setAddError] = useState(null)
  const [removeError, setRemoveError] = useState(null)
  const [busyKey, setBusyKey] = useState(null)

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
          asset_class: result.asset_class,
          currency: result.currency,
          providers,
        })
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

  return {
    items: Array.isArray(data) ? data : [],
    loading,
    error,
    add,
    remove,
    busyKey,
    addError,
    removeError,
    clearAddError: () => setAddError(null),
    clearRemoveError: () => setRemoveError(null),
  }
}
