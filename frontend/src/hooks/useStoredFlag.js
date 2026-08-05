import { useEffect, useState } from 'react'

export function useStoredFlag(storageKey, fallback = false) {
  const [value, setValue] = useState(() => {
    try {
      const stored = window.localStorage.getItem(storageKey)
      return stored == null ? fallback : stored === 'true'
    } catch {
      return fallback
    }
  })

  useEffect(() => {
    try {
      window.localStorage.setItem(storageKey, String(value))
    } catch {
      return
    }
  }, [storageKey, value])

  return [value, setValue]
}
