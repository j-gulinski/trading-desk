import { useCallback, useRef, useState } from 'react'
import { apiGet } from '../services/apiClient.js'
import { endpoints } from '../services/endpoints.js'
import { useBufferedUpdates } from './useBufferedUpdates.js'
import { useSseStream } from './useSseStream.js'
import { useStreamSeed } from './useStreamSeed.js'
import { LOG_SEED_LIMIT } from '../config/logs.js'
import { mergeLogLines, normalizeLogLine, normalizeLogLines } from '../domain/logLines.js'

export function useLogsFeed() {
  const [lines, setLines] = useState([])
  const [paused, setPausedFlag] = useState(false)
  const [pendingCount, setPendingCount] = useState(0)
  const pausedRef = useRef(false)
  const pendingRef = useRef([])
  const runRef = useRef(null)

  const applyRun = useCallback((runId) => {
    if (runId == null || runId === runRef.current) return false
    const hadRun = runRef.current != null
    runRef.current = runId
    if (!hadRun) return false
    pendingRef.current = []
    setPendingCount(0)
    setLines([])
    return true
  }, [])

  const pushLine = useBufferedUpdates((pending) => {
    if (pausedRef.current) {
      pendingRef.current = mergeLogLines(pendingRef.current, pending)
      setPendingCount(pendingRef.current.length)
    } else {
      setLines((previous) => mergeLogLines(previous, pending))
    }
  })

  const { status } = useSseStream(endpoints.monitoring.logsStream, {
    events: ['run', 'log_line'],
    onEvent: (name, data) => {
      if (name === 'run') {
        applyRun(data?.run_id)
        return
      }
      const line = normalizeLogLine(data)
      if (line != null && line.id != null) pushLine(line.id, line)
    },
  })

  const seedStatus = useStreamSeed(status, (signal) =>
    apiGet(endpoints.monitoring.logs({ limit: LOG_SEED_LIMIT }), { signal }).then((payload) => {
      const reset = applyRun(payload?.meta?.run_id)
      const seeded = normalizeLogLines(payload?.lines)
      setLines((previous) => mergeLogLines(reset ? [] : previous, seeded))
    }),
  )

  const setPaused = useCallback((next) => {
    pausedRef.current = next
    setPausedFlag(next)
    if (!next) {
      const pending = pendingRef.current
      pendingRef.current = []
      setPendingCount(0)
      if (pending.length > 0) setLines((previous) => mergeLogLines(previous, pending))
    }
  }, [])

  return { lines, status, seedStatus, paused, setPaused, pendingCount }
}
