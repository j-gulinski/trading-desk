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

    setStatus(STREAM_STATUS.connecting)

    function connect() {
      const current = new EventSource(url)
      let failed = false
      source = current

      current.addEventListener('open', () => {
        if (!stopped) setStatus(STREAM_STATUS.connected)
      })

      current.addEventListener('error', () => {
        if (stopped || failed) return
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

    connect()

    return () => {
      stopped = true
      clearTimeout(reconnectTimer)
      source?.close()
    }
  }, [url, eventNames])

  return { status }
}
