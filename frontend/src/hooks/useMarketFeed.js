import { useEffect, useMemo, useRef, useState } from 'react'
import { apiGet } from '../services/apiClient.js'
import { endpoints } from '../services/endpoints.js'
import { useBufferedUpdates } from './useBufferedUpdates.js'
import { useSseStream } from './useSseStream.js'
import { STORAGE_KEYS } from '../config/storage.js'
import { useStreamSeed } from './useStreamSeed.js'
import { STREAM_EVENTS } from '../config/marketData.js'
import {
  instrumentsForStorage,
  instrumentsFromEvent,
  mergeInstruments,
  reconcileSnapshotInstruments,
  restoreInstruments,
} from '../domain/marketData.js'


function readStoredTickCount() {
  try {
    const stored = Number(window.sessionStorage.getItem(STORAGE_KEYS.marketTickCount))
    return Number.isSafeInteger(stored) && stored >= 0 ? stored : 0
  } catch {
    return 0
  }
}

function storeTickCount(count) {
  try {
    window.sessionStorage.setItem(STORAGE_KEYS.marketTickCount, String(count))
  } catch {
    return
  }
}

function readStoredInstruments() {
  try {
    const stored = window.sessionStorage.getItem(STORAGE_KEYS.marketFeedState)
    return restoreInstruments(stored ? JSON.parse(stored) : null)
  } catch {
    return {}
  }
}

function storeInstruments(instruments) {
  try {
    window.sessionStorage.setItem(
      STORAGE_KEYS.marketFeedState,
      JSON.stringify(instrumentsForStorage(instruments)),
    )
  } catch {
    return
  }
}

export function useMarketFeed() {
  const [instruments, setInstruments] = useState(readStoredInstruments)
  const [tickCount, setTickCount] = useState(readStoredTickCount)

  const receivedTicksRef = useRef(tickCount)

  useEffect(() => {
    storeInstruments(instruments)
  }, [instruments])

  const pushUpdate = useBufferedUpdates((pending) => {
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
        pushUpdate(update.id, { ...update, receivedAtMs })
      }
    },
  })

  const seedStatus = useStreamSeed(status, (signal) =>
    apiGet(endpoints.marketData.snapshot, { signal }).then((snapshot) => {
      setInstruments((previous) => reconcileSnapshotInstruments(previous, snapshot))
    }),
  )

  return useMemo(
    () => ({ instruments, tickCount, status, seedStatus }),
    [instruments, tickCount, status, seedStatus],
  )
}
