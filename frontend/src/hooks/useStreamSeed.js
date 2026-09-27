import { useCallback, useEffect, useRef, useState } from 'react'
import { STREAM_STATUS } from '../config/stream.js'

const RESEED_RETRY_MS = 2000

export function useStreamSeed(status, load, { initial = true, reconnect } = {}) {
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

  useEffect(() => {
    if (seedStatus !== 'error' || status !== STREAM_STATUS.connected || reconnect == null) {
      return undefined
    }
    const timer = window.setTimeout(reconnect, RESEED_RETRY_MS)
    return () => window.clearTimeout(timer)
  }, [reconnect, seedStatus, status])

  return seedStatus
}
