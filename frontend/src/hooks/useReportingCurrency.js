import { useEffect, useState } from 'react'
import { STORAGE_KEYS } from '../config/storage.js'

export function useReportingCurrency() {
  const [currency, setCurrency] = useState(() => {
    try {
      return window.localStorage.getItem(STORAGE_KEYS.reportingCurrency) || null
    } catch {
      return null
    }
  })

  useEffect(() => {
    try {
      if (currency == null) {
        window.localStorage.removeItem(STORAGE_KEYS.reportingCurrency)
      } else {
        window.localStorage.setItem(STORAGE_KEYS.reportingCurrency, currency)
      }
    } catch {
      return
    }
  }, [currency])

  return [currency, setCurrency]
}
