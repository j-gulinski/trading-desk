import { useEffect, useRef, useState } from 'react'
import { apiPost } from '../services/apiClient.js'
import { endpoints } from '../services/endpoints.js'
import { describeApiError } from '../domain/apiErrors.js'

const PREVIEW_DEBOUNCE_MS = 500
const REVISION_RETRY_MS = 500

function previewOf(response) {
  const price = Number(response?.price)
  if (!Number.isFinite(price)) return null
  return {
    price,
    atMs: Date.now(),
    fixedLegValue: Number(response?.fixed_leg_pv),
    floatingLegValue: Number(response?.floating_leg_pv),
    parRate: response?.par_rate == null ? null : Number(response.par_rate),
  }
}

// Debounced model preview. `requestKey` names every input the price depends on, so a
// result is only shown while the inputs it was computed for are still the current ones.
export function useModelPreview({ enabled, requestKey, buildBody }) {
  const [state, setState] = useState({ key: null, preview: null, error: null, pending: false })
  const [revisionRetry, setRevisionRetry] = useState(0)
  const bodyRef = useRef(buildBody)
  bodyRef.current = buildBody

  useEffect(() => {
    if (!enabled) {
      setState((current) => (
        current.key == null && !current.pending
          ? current
          : { key: null, preview: null, error: null, pending: false }
      ))
      return undefined
    }
    const controller = new AbortController()
    let retryTimer
    setState({ key: requestKey, preview: null, error: null, pending: true })
    const timer = setTimeout(async () => {
      try {
        const response = await apiPost(endpoints.pricing.price, bodyRef.current(), {
          signal: controller.signal,
        })
        setState({ key: requestKey, preview: previewOf(response), error: null, pending: false })
      } catch (err) {
        if (controller.signal.aborted) return
        setState({
          key: requestKey,
          preview: null,
          error: describeApiError(err, {
            service: 'Pricing service',
            outcome: 'no model value yet.',
          }),
          pending: false,
        })
        if (err?.status === 409) {
          retryTimer = window.setTimeout(
            () => setRevisionRetry((count) => count + 1),
            REVISION_RETRY_MS,
          )
        }
      }
    }, PREVIEW_DEBOUNCE_MS)
    return () => {
      clearTimeout(timer)
      window.clearTimeout(retryTimer)
      controller.abort()
    }
  }, [enabled, requestKey, revisionRetry])

  const current = enabled && state.key === requestKey && !state.pending
  return {
    preview: current ? state.preview : null,
    previewError: current ? state.error : null,
    previewLoading: enabled && !current,
  }
}
