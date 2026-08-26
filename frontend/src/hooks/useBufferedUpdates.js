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

  const push = useCallback((key, update) => {
    bufferRef.current.set(key, update)
  }, [])

  const drop = useCallback((keys) => {
    for (const key of keys) bufferRef.current.delete(key)
  }, [])

  const clear = useCallback(() => {
    bufferRef.current = new Map()
  }, [])

  return { push, drop, clear }
}
