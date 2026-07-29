import { formatClockTime } from '../../domain/formatting.js'

export default function SortCaptureStatus({ sort }) {
  if (sort.capturedAt == null) return null

  return (
    <div className="table-sort-status" role="status">
      Order captured {formatClockTime(sort.capturedAt).slice(0, 5)} · values live
    </div>
  )
}
