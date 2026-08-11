import { useMemo, useState } from 'react'
import { apiGet } from '../services/apiClient.js'
import { endpoints } from '../services/endpoints.js'
import { useBufferedUpdates } from './useBufferedUpdates.js'
import { useSseStream } from './useSseStream.js'
import { useStreamSeed } from './useStreamSeed.js'
import { BOOK_RISK_EVENT, VALUATION_EVENT } from '../config/valuations.js'
import {
  bookRiskOf,
  bookRisksFromSeed,
  mergeBookRisks,
  mergeValuations,
  valuationOf,
  valuationsFromSeed,
} from '../domain/valuations.js'

export function useValuationFeed() {
  const [valuations, setValuations] = useState({})
  const [bookRisk, setBookRisk] = useState({})

  const pushUpdate = useBufferedUpdates((pending) => {
    setValuations((previous) => mergeValuations(previous, pending))
  })

  const { status } = useSseStream(endpoints.pricing.stream, {
    events: [VALUATION_EVENT, BOOK_RISK_EVENT],
    onEvent: (name, data) => {
      if (name === BOOK_RISK_EVENT) {
        const metric = bookRiskOf(data)
        if (metric) setBookRisk((previous) => mergeBookRisks(previous, [metric]))
        return
      }
      const update = valuationOf(data)
      if (!update) return

      const received = { ...update, receivedAtMs: Date.now() }
      if (received.closed) {
        setValuations((previous) => mergeValuations(previous, [received]))
        return
      }
      pushUpdate(received.id, received)
    },
  })

  const seedStatus = useStreamSeed(status, (signal) =>
    Promise.all([
      apiGet(endpoints.pricing.valuations, { signal }),
      apiGet(endpoints.pricing.bookRisk, { signal }),
    ]).then(([valuationSeed, riskSeed]) => {
      setValuations((previous) =>
        mergeValuations(previous, valuationsFromSeed(valuationSeed)),
      )
      setBookRisk((previous) => mergeBookRisks(previous, bookRisksFromSeed(riskSeed)))
    }),
  )

  return useMemo(
    () => ({ valuations, bookRisk, status, seedStatus }),
    [valuations, bookRisk, status, seedStatus],
  )
}
