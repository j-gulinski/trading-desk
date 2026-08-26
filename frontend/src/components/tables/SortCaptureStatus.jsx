import { formatClockTime } from '../../domain/formatting.js'

export default function SortCaptureStatus({ sort, approximateCurrency = null }) {
  if (sort.capturedAt == null) return null

  return (
    <div className="table-sort-status" role="status">
      Order captured {formatClockTime(sort.capturedAt).slice(0, 5)}
      {approximateCurrency && ` · ≈ ${approximateCurrency} comparison`} · native values live
    </div>
  )
}
