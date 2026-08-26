import { usePolling } from '../../hooks/usePolling.js'
import { apiGet } from '../../services/apiClient.js'
import { endpoints } from '../../services/endpoints.js'
import { normalizeAuditEvents } from '../../domain/auditEvents.js'
import { normalizeLogLines, payloadEntriesOf } from '../../domain/logLines.js'
import { formatClockTime } from '../../domain/formatting.js'
import { STORY_LOG_LIMIT } from '../../config/logs.js'
import SidePanel from '../panel/SidePanel.jsx'
import StatusPill from '../status/StatusPill.jsx'
import LogPayload from './LogPayload.jsx'
import EmptyState from '../EmptyState.jsx'
import LoadingSkeleton from '../LoadingSkeleton.jsx'

const STORY_KINDS = {
  correlation: {
    eyebrow: 'CORRELATION STORY',
    subtitle: 'every log line and audit row carrying this id, oldest first',
    auditParam: 'correlation_id',
  },
  trade: {
    eyebrow: 'TRADE STORY',
    subtitle: 'every log line and audit row about this trade, oldest first',
    auditParam: 'entity_id',
  },
}

function storyEntriesOf(logLines, auditEvents) {
  const entries = []
  for (const line of logLines) {
    entries.push({
      key: `log-${line.id}`,
      trail: 'log',
      atMs: line.atMs,
      service: line.serviceLabel,
      tone: line.tone,
      label: line.level.toUpperCase(),
      text: line.event,
      payload: line.payload,
    })
  }
  for (const event of auditEvents) {
    entries.push({
      key: `audit-${event.id}`,
      trail: 'audit',
      atMs: event.createdAtMs,
      service: event.serviceLabel,
      tone: event.tone,
      label: event.severity,
      text: `${event.eventType} — ${event.message}`,
      payload: null,
    })
  }
  return entries.sort((a, b) => (a.atMs ?? 0) - (b.atMs ?? 0))
}

function StoryRow({ entry }) {
  return (
    <>
      <span className="story__time">{formatClockTime(entry.atMs, { millis: true, day: true })}</span>
      <span className={`story__trail story__trail--${entry.trail}`}>{entry.trail}</span>
      <StatusPill level={entry.tone} label={entry.label} compact />
      <span className="story__service">{entry.service}</span>
      <span className="story__text">{entry.text}</span>
    </>
  )
}

export default function StoryPanel({ story, onOpenStory, onClose }) {
  const { kind, id } = story
  const { eyebrow, subtitle, auditParam } = STORY_KINDS[kind]

  const logs = usePolling(({ signal }) =>
    apiGet(endpoints.monitoring.logs({ q: id, limit: STORY_LOG_LIMIT }), { signal }),
  )
  const audits = usePolling(({ signal }) =>
    apiGet(endpoints.monitoring.audits({ [auditParam]: id, limit: 100 }), { signal }),
  )

  const entries = storyEntriesOf(
    normalizeLogLines(logs.data?.lines),
    normalizeAuditEvents(audits.data),
  )
  const loading = logs.loading || audits.loading

  return (
    <SidePanel wide eyebrow={eyebrow} title={id} subtitle={subtitle} onClose={onClose}>
      {loading && <LoadingSkeleton variant="panel" label="Assembling the story" />}
      {!loading && entries.length === 0 && (
        <EmptyState message="Nothing recorded for this id — log lines may have rotated out of the buffer." />
      )}
      {!loading && entries.length > 0 && (
        <ol className="story">
          {entries.map((entry) => (
            <li key={entry.key} className="story__item">
              {payloadEntriesOf(entry.payload).length > 0 ? (
                <details>
                  <summary className="story__row story__row--toggle">
                    <StoryRow entry={entry} />
                  </summary>
                  <LogPayload
                    payload={entry.payload}
                    activeId={id}
                    onTradeClick={(tradeId) => onOpenStory({ kind: 'trade', id: tradeId })}
                    onCorrelationClick={(cid) => onOpenStory({ kind: 'correlation', id: cid })}
                  />
                </details>
              ) : (
                <div className="story__row">
                  <StoryRow entry={entry} />
                </div>
              )}
            </li>
          ))}
        </ol>
      )}
    </SidePanel>
  )
}
