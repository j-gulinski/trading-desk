import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { apiGet } from '../services/apiClient.js'
import { endpoints } from '../services/endpoints.js'
import { useBufferedUpdates } from './useBufferedUpdates.js'
import { useSseStream } from './useSseStream.js'
import { STORAGE_KEYS } from '../config/storage.js'
import { useStreamSeed } from './useStreamSeed.js'
import { STREAM_EVENTS } from '../config/marketData.js'
import { STREAM_STATUS } from '../config/stream.js'
import {
  dropInstruments,
  instrumentId,
  instrumentsForStorage,
  instrumentsFromEvent,
  mergeInstruments,
  reconcileSnapshotInstruments,
  restoreInstruments,
} from '../domain/marketData.js'
import { curveOf, curvesFromSnapshot, mergeCurves } from '../domain/curves.js'

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
  const [curves, setCurves] = useState({})
  const [tickCount, setTickCount] = useState(readStoredTickCount)
  const receivedTicksRef = useRef(tickCount)
  const reconcilingRef = useRef(false)
  const bufferedEventsRef = useRef([])

  useEffect(() => {
    storeInstruments(instruments)
  }, [instruments])

  const {
    push: pushUpdate,
    drop: dropBufferedUpdates,
    clear: clearBufferedUpdates,
  } = useBufferedUpdates((pending) => {
    setInstruments((previous) => mergeInstruments(previous, pending))
    setTickCount(receivedTicksRef.current)
    storeTickCount(receivedTicksRef.current)
  })

  const dropRows = useCallback((ids) => {
    dropBufferedUpdates(ids)
    setInstruments((previous) => dropInstruments(previous, ids))
  }, [dropBufferedUpdates])

  const applyLiveEvent = useCallback((name, data) => {
    if (name === 'market_remove') {
      const rows = Array.isArray(data?.rows) ? data.rows : []
      if (rows.length > 0) {
        dropRows(rows.map((row) => instrumentId(row.provider, row.symbol)))
      }
      return
    }
    if (name === 'curve_tick') {
      const curve = curveOf(data)
      if (curve) setCurves((previous) => mergeCurves(previous, [curve]))
      return
    }
    const receivedAtMs = Date.now()
    const updates = instrumentsFromEvent(name, data)
    if (updates.length === 0) return
    receivedTicksRef.current += 1
    for (const update of updates) {
      pushUpdate(update.id, { ...update, receivedAtMs })
    }
  }, [dropRows, pushUpdate])

  const { status, reconnect } = useSseStream(endpoints.marketData.stream, {
    events: STREAM_EVENTS,
    onOpen: () => {
      clearBufferedUpdates()
      reconcilingRef.current = true
      bufferedEventsRef.current = []
    },
    onEvent: (name, data) => {
      if (reconcilingRef.current) {
        bufferedEventsRef.current.push({ name, data })
        return
      }
      applyLiveEvent(name, data)
    },
  })

  const seedStatus = useStreamSeed(status, (signal) => {
    return apiGet(endpoints.marketData.snapshot, { signal, timeoutMs: 10000 }).then((snapshot) => {
      const streamId = snapshot?.stream_id ?? null
      const watermark = Number(snapshot?.event_id ?? 0)
      const buffered = reconcilingRef.current ? bufferedEventsRef.current : []
      const afterSnapshot = buffered
        .filter(({ data }) => (
          data?.stream_id === streamId &&
          Number.isSafeInteger(Number(data?.event_id)) &&
          Number(data.event_id) > watermark
        ))
        .sort((left, right) => Number(left.data.event_id) - Number(right.data.event_id))

      bufferedEventsRef.current = []
      reconcilingRef.current = false

      setInstruments(() => {
        let next = reconcileSnapshotInstruments({}, snapshot)
        for (const { name, data } of afterSnapshot) {
          if (name === 'market_remove') {
            const ids = (Array.isArray(data?.rows) ? data.rows : [])
              .map((row) => instrumentId(row.provider, row.symbol))
            next = dropInstruments(next, ids)
            continue
          }
          const updates = instrumentsFromEvent(name, data).map((update) => ({
            ...update,
            receivedAtMs: Date.now(),
          }))
          if (updates.length > 0) {
            receivedTicksRef.current += 1
            next = mergeInstruments(next, updates)
          }
        }
        return next
      })

      let nextCurves = Object.fromEntries(
        curvesFromSnapshot(snapshot).map((curve) => [curve.name, curve]),
      )
      for (const { name, data } of afterSnapshot) {
        if (name !== 'curve_tick') continue
        const curve = curveOf(data)
        if (curve) nextCurves = mergeCurves(nextCurves, [curve])
      }
      setCurves(nextCurves)
      setTickCount(receivedTicksRef.current)
      storeTickCount(receivedTicksRef.current)
    }).catch((error) => {
      const buffered = reconcilingRef.current ? bufferedEventsRef.current : []
      bufferedEventsRef.current = []
      reconcilingRef.current = false
      for (const { name, data } of buffered) applyLiveEvent(name, data)
      throw error
    })
  }, { initial: false })

  useEffect(() => {
    if (seedStatus !== 'error' || status !== STREAM_STATUS.connected) return undefined
    const timer = window.setTimeout(reconnect, 2000)
    return () => window.clearTimeout(timer)
  }, [reconnect, seedStatus, status])

  return useMemo(
    () => ({
      instruments,
      curves,
      tickCount,
      status,
      seedStatus,
      dropRows,
    }),
    [instruments, curves, tickCount, status, seedStatus, dropRows],
  )
}
