import { useCallback, useEffect, useRef } from 'react'
import { subscribeToStreamClock } from './streamClock.js'

export function useBufferedUpdates(onFlush) {
  const bufferRef = useRef(new Map())
  const onFlushRef = useRef(onFlush)
  onFlushRef.current = onFlush

  useEffect(
    () =>
      subscribeToStreamClock(() => {
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
