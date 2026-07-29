import { useMemo, useState } from 'react'
import { apiGet } from '../services/apiClient.js'
import { endpoints } from '../services/endpoints.js'
import { useBufferedUpdates } from './useBufferedUpdates.js'
import { useSseStream } from './useSseStream.js'
import { useStreamSeed } from './useStreamSeed.js'
import { VALUATION_EVENT } from '../config/valuations.js'
import { mergeValuations, valuationOf, valuationsFromSeed } from '../domain/valuations.js'

export function useValuationFeed() {
  const [valuations, setValuations] = useState({})

  const buffer = useBufferedUpdates((pending) => {
    setValuations((previous) => mergeValuations(previous, pending))
  })

  const { status } = useSseStream(endpoints.pricing.stream, {
    events: [VALUATION_EVENT],
    onEvent: (_name, data) => {
      const update = valuationOf(data)
      if (update) buffer(update.id, { ...update, receivedAtMs: Date.now() })
    },
  })

  const seedStatus = useStreamSeed(status, (signal) =>
    apiGet(endpoints.pricing.valuations, { signal }).then((seed) => {
      setValuations((previous) => mergeValuations(previous, valuationsFromSeed(seed)))
    }),
  )

  return useMemo(
    () => ({ valuations, status, seedStatus }),
    [valuations, status, seedStatus],
  )
}
