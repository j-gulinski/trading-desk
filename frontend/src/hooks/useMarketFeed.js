import { useEffect, useRef, useState } from 'react'
import { apiGet } from '../services/apiClient.js'
import { endpoints } from '../services/endpoints.js'
import { useSseStream } from './useSseStream.js'
import { STREAM_EVENTS, FLUSH_INTERVAL_MS } from '../config/marketData.js'
import {
  instrumentsForStorage,
  instrumentsFromEvent,
  instrumentsFromSnapshot,
  mergeInstruments,
  restoreInstruments,
} from '../domain/marketData.js'

const TICK_COUNT_STORAGE_KEY = 'market-data.tick-count'
const MARKET_STATE_STORAGE_KEY = 'market-data.feed-state'

function readStoredTickCount() {
  try {
    const stored = Number(window.sessionStorage.getItem(TICK_COUNT_STORAGE_KEY))
    return Number.isSafeInteger(stored) && stored >= 0 ? stored : 0
  } catch {
    return 0
  }
}

function storeTickCount(count) {
  try {
    window.sessionStorage.setItem(TICK_COUNT_STORAGE_KEY, String(count))
  } catch {
    return
  }
}

function readStoredInstruments() {
  try {
    const stored = window.sessionStorage.getItem(MARKET_STATE_STORAGE_KEY)
    return restoreInstruments(stored ? JSON.parse(stored) : null)
  } catch {
    return {}
  }
}

function storeInstruments(instruments) {
  try {
    window.sessionStorage.setItem(
      MARKET_STATE_STORAGE_KEY,
      JSON.stringify(instrumentsForStorage(instruments)),
    )
  } catch {
    return
  }
}

function snapshotUpdates(snapshot) {
  const receivedAtMs = Date.now()
  return instrumentsFromSnapshot(snapshot).map((instrument) => ({
    ...instrument,
    receivedAtMs,
  }))
}

export function useMarketFeed() {
  const [instruments, setInstruments] = useState(readStoredInstruments)
  const [tickCount, setTickCount] = useState(readStoredTickCount)
  const [snapshotSettled, setSnapshotSettled] = useState(false)

  const pendingUpdatesRef = useRef(new Map())
  const receivedTicksRef = useRef(tickCount)
  const previousStatusRef = useRef('CONNECTING')

  useEffect(() => {
    storeInstruments(instruments)
  }, [instruments])

  useEffect(() => {
    let cancelled = false
    const controller = new AbortController()

    apiGet(endpoints.marketData.snapshot, { signal: controller.signal })
      .then((snapshot) => {
        if (cancelled) return
        setInstruments((previous) => mergeInstruments(previous, snapshotUpdates(snapshot)))
        setSnapshotSettled(true)
      })
      .catch(() => {
        if (!cancelled) setSnapshotSettled(true)
      })

    return () => {
      cancelled = true
      controller.abort()
    }
  }, [])

  const { status } = useSseStream(endpoints.marketData.stream, {
    events: STREAM_EVENTS,
    onEvent: (name, data) => {
      const receivedAtMs = Date.now()
      const updates = instrumentsFromEvent(name, data)
      if (updates.length === 0) return
      receivedTicksRef.current += 1
      for (const update of updates) {
        pendingUpdatesRef.current.set(update.id, { ...update, receivedAtMs })
      }
    },
  })

  useEffect(() => {
    const reconnected = previousStatusRef.current === 'RECONNECTING' && status === 'CONNECTED'
    previousStatusRef.current = status
    if (!reconnected) return undefined

    const controller = new AbortController()
    apiGet(endpoints.marketData.snapshot, { signal: controller.signal })
      .then((snapshot) => {
        setInstruments((previous) => mergeInstruments(previous, snapshotUpdates(snapshot)))
      })
      .catch(() => undefined)

    return () => controller.abort()
  }, [status])

  useEffect(() => {
    const flushId = setInterval(() => {
      if (pendingUpdatesRef.current.size === 0) return
      const pending = Array.from(pendingUpdatesRef.current.values())
      pendingUpdatesRef.current = new Map()
      setInstruments((previous) => mergeInstruments(previous, pending))
      setTickCount(receivedTicksRef.current)
      storeTickCount(receivedTicksRef.current)
    }, FLUSH_INTERVAL_MS)

    return () => clearInterval(flushId)
  }, [])

  return { instruments, tickCount, status, snapshotSettled }
}
