import { useEffect, useState } from 'react'
import { apiGet } from '../services/apiClient.js'
import { endpoints } from '../services/endpoints.js'

const HINT_DEBOUNCE_MS = 300

export function useCurveHint(curveName, maturityYears, schedule = {}) {
  const maturity = Number(maturityYears)
  const enabled = Boolean(curveName) && Number.isFinite(maturity) && maturity > 0
  const requestKey = enabled
    ? endpoints.pricing.curveAt(curveName, { maturity_years: maturity, ...schedule })
    : null
  const [state, setState] = useState({ key: null, hint: null })

  useEffect(() => {
    if (requestKey == null) return undefined
    const controller = new AbortController()
    const timer = setTimeout(async () => {
      try {
        const hint = await apiGet(requestKey, { signal: controller.signal })
        setState({ key: requestKey, hint })
      } catch {
        if (!controller.signal.aborted) setState({ key: requestKey, hint: null })
      }
    }, HINT_DEBOUNCE_MS)
    return () => {
      clearTimeout(timer)
      controller.abort()
    }
  }, [requestKey])

  return state.key === requestKey ? state.hint : null
}
