import { useEffect, useState } from 'react'

export function useElapsedTime(sinceMs, intervalMs = 1000) {
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), intervalMs)
    return () => clearInterval(id)
  }, [intervalMs, sinceMs])

  return {
    now,
    elapsedMs: sinceMs == null ? null : Math.max(0, now - sinceMs),
  }
}
