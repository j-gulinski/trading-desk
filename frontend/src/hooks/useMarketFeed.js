import { useEffect, useMemo, useRef, useState } from 'react'
import { apiGet } from '../services/apiClient.js'
import { endpoints } from '../services/endpoints.js'
import { useBufferedUpdates } from './useBufferedUpdates.js'
import { useSseStream } from './useSseStream.js'
import { useStreamSeed } from './useStreamSeed.js'
import { STREAM_EVENTS } from '../config/marketData.js'
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

  const receivedTicksRef = useRef(tickCount)

  useEffect(() => {
    storeInstruments(instruments)
  }, [instruments])

  const buffer = useBufferedUpdates((pending) => {
    setInstruments((previous) => mergeInstruments(previous, pending))
    setTickCount(receivedTicksRef.current)
    storeTickCount(receivedTicksRef.current)
  })

  const { status } = useSseStream(endpoints.marketData.stream, {
    events: STREAM_EVENTS,
    onEvent: (name, data) => {
      const receivedAtMs = Date.now()
      const updates = instrumentsFromEvent(name, data)
      if (updates.length === 0) return
      receivedTicksRef.current += 1
      for (const update of updates) {
        buffer(update.id, { ...update, receivedAtMs })
      }
    },
  })

  const seedStatus = useStreamSeed(status, (signal) =>
    apiGet(endpoints.marketData.snapshot, { signal }).then((snapshot) => {
      setInstruments((previous) => mergeInstruments(previous, snapshotUpdates(snapshot)))
    }),
  )

  return useMemo(
    () => ({ instruments, tickCount, status, seedStatus }),
    [instruments, tickCount, status, seedStatus],
  )
}
