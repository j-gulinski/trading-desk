import StatusPill from './StatusPill.jsx'
import { streamStatusLabel, streamStatusLevel } from '../../config/stream.js'

export default function StreamHeader({ title, note, status, stream }) {
  return (
    <div className="stream-head">
      <span className="stream-head__title">{title}</span>
      <div className="stream-head__meta">
        {note != null && <span className="stream-head__note">{note}</span>}
        <StatusPill
          level={streamStatusLevel(status)}
          label={stream ? `${stream} ${streamStatusLabel(status)}` : streamStatusLabel(status)}
        />
      </div>
    </div>
  )
}
