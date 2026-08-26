import { useCallback, useEffect, useRef, useState } from 'react'
import { STREAM_STATUS } from '../config/stream.js'

export function useStreamSeed(status, load, { initial = true } = {}) {
  const [seedStatus, setSeedStatus] = useState('loading')

  const loadRef = useRef(load)
  loadRef.current = load
  const previousStatusRef = useRef(status)
  const controllerRef = useRef(null)

  const runSeed = useCallback(() => {
    controllerRef.current?.abort()
    const controller = new AbortController()
    controllerRef.current = controller
    setSeedStatus('loading')

    loadRef.current(controller.signal).then(
      () => {
        if (!controller.signal.aborted && controllerRef.current === controller) {
          setSeedStatus('ready')
        }
      },
      () => {
        if (!controller.signal.aborted && controllerRef.current === controller) {
          setSeedStatus('error')
        }
      },
    )

    return () => {
      if (controllerRef.current === controller) controllerRef.current = null
      controller.abort()
    }
  }, [])

  useEffect(() => (initial ? runSeed() : undefined), [initial, runSeed])

  useEffect(() => {
    const previousStatus = previousStatusRef.current
    previousStatusRef.current = status
    const becameConnected =
      previousStatus !== STREAM_STATUS.connected && status === STREAM_STATUS.connected
    return becameConnected ? runSeed() : undefined
  }, [status, runSeed])

  return seedStatus
}
