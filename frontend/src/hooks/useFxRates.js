import { useEffect, useState } from 'react'
import { apiGet } from '../services/apiClient.js'
import { endpoints } from '../services/endpoints.js'
import { FX_RATES_REFRESH_MS } from '../config/marketData.js'

const EMPTY = { to: null, rates: null, error: null, loading: false }

export function useFxRates(toCurrency) {
  const [state, setState] = useState(EMPTY)

  useEffect(() => {
    if (!toCurrency) {
      setState(EMPTY)
      return undefined
    }
    const controller = new AbortController()
    let cancelled = false
    let timer
    setState({ to: toCurrency, rates: null, error: null, loading: true })

    async function load() {
      try {
        const payload = await apiGet(endpoints.marketData.fxRates(toCurrency), {
          signal: controller.signal,
        })
        if (cancelled) return
        setState({
          to: toCurrency,
          rates: payload?.rates ?? {},
          error: null,
          loading: false,
        })
      } catch {
        if (cancelled || controller.signal.aborted) return
        setState((previous) => ({
          ...previous,
          to: toCurrency,
          error: 'Official rates unavailable — retrying.',
          loading: false,
        }))
      } finally {
        if (!cancelled) timer = setTimeout(load, FX_RATES_REFRESH_MS)
      }
    }

    load()
    return () => {
      cancelled = true
      controller.abort()
      clearTimeout(timer)
    }
  }, [toCurrency])

  return state
}
