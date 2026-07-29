import { useEffect, useState } from 'react'
import { FRESHNESS_INTERVAL_MS } from '../config/stream.js'
import { subscribeToStreamClock } from './streamClock.js'

export function useElapsedTime(sinceMs) {
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => subscribeToStreamClock(setNow, FRESHNESS_INTERVAL_MS), [])

  return {
    now,
    elapsedMs: sinceMs == null ? null : Math.max(0, now - sinceMs),
  }
}
