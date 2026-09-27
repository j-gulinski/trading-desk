import { useEffect, useRef } from 'react'
import { apiGet } from '../services/apiClient.js'
import { endpoints } from '../services/endpoints.js'
import { BOOK_SUMMARY_POLL_INTERVAL_MS } from '../config/books.js'
import { booksSummaryOf } from '../domain/books.js'
import { usePolling } from './usePolling.js'
import { useReportingCurrency } from './useReportingCurrency.js'

export function useBooksSummary() {
  const [reportingCurrency, setReportingCurrency] = useReportingCurrency()
  const request = usePolling(
    ({ signal }) => apiGet(endpoints.blotter.booksSummary(reportingCurrency), { signal }),
    { intervalMs: BOOK_SUMMARY_POLL_INTERVAL_MS },
  )
  const refetch = request.refetch
  const currencyMounted = useRef(false)

  useEffect(() => {
    if (!currencyMounted.current) {
      currencyMounted.current = true
      return
    }
    refetch()
  }, [reportingCurrency, refetch])

  return {
    ...request,
    ...booksSummaryOf(request.data),
    reportingCurrency,
    setReportingCurrency,
  }
}
