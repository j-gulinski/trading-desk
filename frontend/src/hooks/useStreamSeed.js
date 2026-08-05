import { useCallback, useEffect, useRef, useState } from 'react'
import { STREAM_STATUS } from '../config/stream.js'

export function useStreamSeed(status, load) {
  const [seedStatus, setSeedStatus] = useState('loading')

  const loadRef = useRef(load)
  loadRef.current = load
  const previousStatusRef = useRef(status)

  const runSeed = useCallback(() => {
    const controller = new AbortController()

    loadRef.current(controller.signal).then(
      () => {
        if (!controller.signal.aborted) setSeedStatus('ready')
      },
      () => {
        if (!controller.signal.aborted) setSeedStatus('error')
      },
    )

    return () => controller.abort()
  }, [])

  useEffect(runSeed, [runSeed])

  useEffect(() => {
    const wasInterrupted = previousStatusRef.current === STREAM_STATUS.reconnecting
    previousStatusRef.current = status
    return wasInterrupted && status === STREAM_STATUS.connected ? runSeed() : undefined
  }, [status, runSeed])

  return seedStatus
}
