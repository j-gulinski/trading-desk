import { useEffect, useRef, useState } from 'react'
import { STREAM_STATUS } from '../config/stream.js'

const RECONNECT_DELAY_MS = 2000

export function useSseStream(url, { events = ['message'], onEvent } = {}) {
  const [status, setStatus] = useState(STREAM_STATUS.connecting)

  const onEventRef = useRef(onEvent)
  onEventRef.current = onEvent

  const eventNames = events.join(',')

  useEffect(() => {
    const names = eventNames.split(',')
    let source
    let reconnectTimer
    let stopped = false

    function disconnect() {
      clearTimeout(reconnectTimer)
      source?.close()
      source = undefined
    }

    function connect() {
      const current = new EventSource(url)
      let failed = false
      source = current

      current.addEventListener('open', () => {
        if (!stopped) setStatus(STREAM_STATUS.connected)
      })

      current.addEventListener('error', () => {
        if (stopped || failed || current !== source || document.hidden) return
        failed = true
        current.close()
        setStatus(STREAM_STATUS.reconnecting)
        reconnectTimer = setTimeout(connect, RECONNECT_DELAY_MS)
      })

      for (const name of names) {
        current.addEventListener(name, (message) => {
          let data
          try {
            data = JSON.parse(message.data)
          } catch {
            return
          }
          onEventRef.current?.(name, data)
        })
      }
    }

    function handleVisibility() {
      if (stopped) return
      if (document.hidden) {
        disconnect()
        setStatus(STREAM_STATUS.suspended)
      } else if (source == null) {
        setStatus(STREAM_STATUS.connecting)
        connect()
      }
    }

    if (document.hidden) {
      setStatus(STREAM_STATUS.suspended)
    } else {
      setStatus(STREAM_STATUS.connecting)
      connect()
    }
    document.addEventListener('visibilitychange', handleVisibility)

    return () => {
      stopped = true
      document.removeEventListener('visibilitychange', handleVisibility)
      disconnect()
    }
  }, [url, eventNames])

  return { status }
}
