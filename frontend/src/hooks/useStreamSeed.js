import { useCallback, useEffect, useRef, useState } from 'react'

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
    const reconnected = previousStatusRef.current === 'RECONNECTING' && status === 'CONNECTED'
    previousStatusRef.current = status
    return reconnected ? runSeed() : undefined
  }, [status, runSeed])

  return seedStatus
}
