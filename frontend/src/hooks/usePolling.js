import { useCallback, useEffect, useRef, useState } from 'react'

const MIN_RETRY_DELAY_MS = 1000

export function usePolling(
  fetchFn,
  { intervalMs = 5000, timeoutMs = 4000 } = {},
) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)
  const [lastPolled, setLastPolled] = useState(null)
  const [lastUpdated, setLastUpdated] = useState(null)

  const savedFn = useRef(fetchFn)
  savedFn.current = fetchFn
  const tickRef = useRef(null)

  useEffect(() => {
    let cancelled = false
    let inFlight = false
    let timer
    let requestController

    async function tick() {
      if (inFlight) return
      inFlight = true
      clearTimeout(timer)
      const startedAt = Date.now()
      requestController = new AbortController()
      const timeout = timeoutMs == null
        ? null
        : setTimeout(() => requestController.abort(), timeoutMs)
      setLastPolled(startedAt)

      try {
        const result = await savedFn.current({ signal: requestController.signal })
        if (cancelled) return
        setData(result)
        setError(null)
        setLastUpdated(Date.now())
      } catch (err) {
        if (cancelled) return
        setError(err)
      } finally {
        clearTimeout(timeout)
        inFlight = false
        if (!cancelled) {
          setLoading(false)
          const elapsedMs = Date.now() - startedAt
          const delayMs = Math.max(MIN_RETRY_DELAY_MS, intervalMs - elapsedMs)
          timer = setTimeout(tick, delayMs)
        }
      }
    }

    tickRef.current = tick
    tick()
    return () => {
      cancelled = true
      tickRef.current = null
      clearTimeout(timer)
      requestController?.abort()
    }
  }, [intervalMs, timeoutMs])

  const refetch = useCallback(() => tickRef.current?.(), [])

  return { data, error, loading, lastPolled, lastUpdated, refetch }
}
