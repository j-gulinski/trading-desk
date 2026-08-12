import { useState } from 'react'
import { useLogsFeed } from '../../hooks/useLogsFeed.js'
import { usePolling } from '../../hooks/usePolling.js'
import { apiGet } from '../../services/apiClient.js'
import { endpoints } from '../../services/endpoints.js'
import { filterLogLines, logServicesOf, warnPulseOf } from '../../domain/logLines.js'
import { formatNumber } from '../../domain/formatting.js'
import { LOG_LEVELS, LOG_META_POLL_MS, LOG_RENDER_LIMIT } from '../../config/logs.js'
import { streamStatusLevel } from '../../config/stream.js'
import Panel from '../../components/Panel.jsx'
import EmptyState from '../../components/EmptyState.jsx'
import FilterBar from '../../components/filters/FilterBar.jsx'
import FilterChipGroup from '../../components/filters/FilterChipGroup.jsx'
import StatusPill from '../../components/status/StatusPill.jsx'
import Sparkline from '../../components/charts/Sparkline.jsx'
import LogLineList from '../../components/logs/LogLineList.jsx'
import StoryPanel from '../../components/logs/StoryPanel.jsx'

const LEVEL_TONES = { warning: 'warning', error: 'error', critical: 'critical' }

export default function Logs() {
  const { lines, status, seedStatus, paused, setPaused, pendingCount } = useLogsFeed()
  const meta = usePolling(
    ({ signal }) => apiGet(endpoints.monitoring.logs({ limit: 1 }), { signal }),
    { intervalMs: LOG_META_POLL_MS },
  )
  const [service, setService] = useState(null)
  const [minLevel, setMinLevel] = useState(null)
  const [query, setQuery] = useState('')
  const [story, setStory] = useState(null)

  const now = Date.now()
  const services = logServicesOf(meta.data?.meta, now)
  const pulse = warnPulseOf(meta.data?.meta, now)

  const serviceOptions = services.map((entry) => ({
    value: entry.service,
    label: entry.label,
    count: entry.buffered,
    tone: entry.warnPlus > 0 ? 'warning' : undefined,
    trailing: (
      <Sparkline values={entry.warnSeries} width={44} height={14} className="filter-chip__spark" />
    ),
  }))
  const levelOptions = LOG_LEVELS.map((level) => ({
    value: level,
    label: `${level.toUpperCase()}+`,
    tone: LEVEL_TONES[level],
  }))

  const visible = filterLogLines(lines, { service, minLevel, query })
  const rendered = visible.slice(0, LOG_RENDER_LIMIT)

  return (
    <section className="page">
      <FilterBar
        label="SERVICE"
        ariaLabel="Filter log lines by service"
        options={serviceOptions}
        value={service}
        onChange={setService}
        search={{
          label: 'SEARCH',
          placeholder: 'event, field value or correlation id…',
          value: query,
          onChange: setQuery,
        }}
      >
        <FilterChipGroup
          ariaLabel="Minimum log level"
          options={levelOptions}
          value={minLevel}
          onChange={setMinLevel}
        />
        <button
          type="button"
          className={`logs__pause${paused ? ' logs__pause--active' : ''}`}
          onClick={() => setPaused(!paused)}
        >
          {paused ? `Resume · ${formatNumber(pendingCount)} new` : 'Pause'}
        </button>
      </FilterBar>

      <Panel
        title="Live tail · all services"
        meta={
          <>
            <StatusPill level={streamStatusLevel(status)} label={status} />
            <span>
              {rendered.length < visible.length
                ? `newest ${formatNumber(rendered.length)} of ${formatNumber(visible.length)} matching · ${formatNumber(lines.length)} buffered`
                : `${formatNumber(visible.length)} of ${formatNumber(lines.length)} buffered`}
              {pulse > 0 && ` · ${formatNumber(pulse)} warn+ last 5 min`}
              {paused && ' · paused'}
            </span>
          </>
        }
      >
        {seedStatus === 'loading' && lines.length === 0 && (
          <EmptyState message="Loading log lines…" />
        )}
        {seedStatus === 'error' && lines.length === 0 && (
          <EmptyState message="Log feed unavailable — retrying." />
        )}
        {lines.length > 0 && visible.length === 0 && (
          <EmptyState message="No lines match the current filters." />
        )}
        {rendered.length > 0 && (
          <LogLineList
            lines={rendered}
            onCorrelationClick={(id) => setStory({ kind: 'correlation', id })}
            onTradeClick={(id) => setStory({ kind: 'trade', id })}
            tail
          />
        )}
      </Panel>

      {story && (
        <StoryPanel
          key={`${story.kind}:${story.id}`}
          story={story}
          onOpenStory={setStory}
          onClose={() => setStory(null)}
        />
      )}
    </section>
  )
}
