import { useCallback, useEffect, useRef } from 'react'
import { FLUSH_INTERVAL_MS } from '../config/stream.js'

const subscribers = new Set()
let clockId = null

function tick() {
  for (const flush of Array.from(subscribers)) flush()
}

function subscribeToClock(flush) {
  subscribers.add(flush)
  if (clockId === null) clockId = setInterval(tick, FLUSH_INTERVAL_MS)

  return () => {
    subscribers.delete(flush)
    if (subscribers.size > 0) return
    clearInterval(clockId)
    clockId = null
  }
}

export function useBufferedUpdates(onFlush) {
  const bufferRef = useRef(new Map())
  const onFlushRef = useRef(onFlush)
  onFlushRef.current = onFlush

  useEffect(
    () =>
      subscribeToClock(() => {
        if (bufferRef.current.size === 0) return
        const pending = Array.from(bufferRef.current.values())
        bufferRef.current = new Map()
        onFlushRef.current(pending)
      }),
    [],
  )

  return useCallback((key, update) => {
    bufferRef.current.set(key, update)
  }, [])
}
