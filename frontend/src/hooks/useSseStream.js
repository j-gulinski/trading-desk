import { useCallback, useEffect, useRef, useState } from 'react'
import { STREAM_STATUS } from '../config/stream.js'

const RECONNECT_DELAY_MS = 2000

export function useSseStream(url, { events = ['message'], onEvent, onOpen } = {}) {
  const [status, setStatus] = useState(STREAM_STATUS.connecting)
  const [generation, setGeneration] = useState(0)

  const onEventRef = useRef(onEvent)
  onEventRef.current = onEvent
  const onOpenRef = useRef(onOpen)
  onOpenRef.current = onOpen

  const eventNames = events.join(',')

  useEffect(() => {
    const names = eventNames.split(',')
    let source
    let reconnectTimer
    let stopped = false

    function connect() {
      const current = new EventSource(url)
      let failed = false
      source = current

      current.addEventListener('open', () => {
        if (!stopped) {
          onOpenRef.current?.()
          setStatus(STREAM_STATUS.connected)
        }
      })

      current.addEventListener('error', () => {
        if (stopped || failed || current !== source) return
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

    setStatus(STREAM_STATUS.connecting)
    connect()

    return () => {
      stopped = true
      clearTimeout(reconnectTimer)
      source?.close()
    }
  }, [url, eventNames, generation])

  const reconnect = useCallback(() => {
    setGeneration((current) => current + 1)
  }, [])

  return { status, reconnect }
}
