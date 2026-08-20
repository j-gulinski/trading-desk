import { useEffect, useState } from 'react'
import { apiGet } from '../services/apiClient.js'
import { endpoints } from '../services/endpoints.js'

const EMPTY = {
  key: null,
  rows: [],
  loading: false,
  error: null,
}

function messageOf(error) {
  return error?.body?.error ?? error?.message ?? 'Could not load observed quote changes'
}

export function useQuoteHistory(instrument) {
  const [state, setState] = useState(EMPTY)
  const key = instrument?.id ?? null
  const provider = instrument?.provider ?? null
  const symbol = instrument?.symbol ?? null
  const priceVersion = [instrument?.bid, instrument?.ask, instrument?.last, instrument?.value]
    .map((value) => value ?? '')
    .join('|')

  useEffect(() => {
    if (!key || !provider || !symbol) {
      setState(EMPTY)
      return undefined
    }

    const controller = new AbortController()
    setState((previous) =>
      previous.key === key
        ? { ...previous, error: null }
        : { ...EMPTY, key, loading: true },
    )

    apiGet(endpoints.marketData.quoteHistory(provider, symbol), { signal: controller.signal })
      .then((payload) => {
        setState({
          key,
          rows: Array.isArray(payload?.rows) ? payload.rows : [],
          loading: false,
          error: null,
        })
      })
      .catch((error) => {
        if (controller.signal.aborted) return
        setState((previous) => ({
          ...previous,
          key,
          loading: false,
          error: messageOf(error),
        }))
      })

    return () => controller.abort()
  }, [key, provider, symbol, priceVersion])

  return state
}
