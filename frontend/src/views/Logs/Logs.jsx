import { useState } from 'react'
import { useLogsFeed } from '../../hooks/useLogsFeed.js'
import { usePolling } from '../../hooks/usePolling.js'
import { apiGet } from '../../services/apiClient.js'
import { endpoints } from '../../services/endpoints.js'
import { filterLogLines, logServicesOf, warnPulseOf } from '../../domain/logLines.js'
import { formatNumber } from '../../domain/formatting.js'
import {
  LOG_LEVELS,
  LOG_LEVEL_TONES,
  LOG_META_POLL_MS,
  LOG_RENDER_LIMIT,
} from '../../config/logs.js'
import { streamStatusLevel } from '../../config/stream.js'
import Panel from '../../components/Panel.jsx'
import EmptyState from '../../components/EmptyState.jsx'
import LoadingSkeleton from '../../components/LoadingSkeleton.jsx'
import FilterBar from '../../components/filters/FilterBar.jsx'
import FilterChipGroup from '../../components/filters/FilterChipGroup.jsx'
import StatusPill from '../../components/status/StatusPill.jsx'
import LogLineList from '../../components/logs/LogLineList.jsx'
import StoryPanel from '../../components/logs/StoryPanel.jsx'
import { providerLabel } from '../../config/providers.js'

function initialFilters() {
  const queryString = window.location.hash.split('?')[1] ?? ''
  const params = new URLSearchParams(queryString)
  return {
    service: params.get('service'),
    provider: params.get('provider'),
    scope: params.get('scope'),
    query: params.get('q') ?? '',
  }
}

export default function Logs() {
  const initial = initialFilters()
  const { lines, status, seedStatus, paused, setPaused, pendingCount } = useLogsFeed()
  const meta = usePolling(
    ({ signal }) => apiGet(endpoints.monitoring.logs({ limit: 1 }), { signal }),
    { intervalMs: LOG_META_POLL_MS },
  )
  const [service, setService] = useState(initial.service)
  const [minLevel, setMinLevel] = useState(null)
  const [provider, setProvider] = useState(initial.provider)
  const [scope, setScope] = useState(initial.scope)
  const [query, setQuery] = useState(initial.query)
  const [story, setStory] = useState(null)

  const now = Date.now()
  const services = logServicesOf(meta.data?.meta)
  const pulse = warnPulseOf(meta.data?.meta, now)

  const serviceOptions = services.map((entry) => ({
    value: entry.service,
    label: entry.label,
    count: entry.buffered,
  }))
  const levelOptions = LOG_LEVELS.map((level) => ({
    value: level,
    label: `${level.toUpperCase()}+`,
    tone: LOG_LEVEL_TONES[level],
  }))
  const providerOptions = [
    ...new Set([provider, ...lines.map((line) => line.provider)].filter(Boolean)),
  ]
    .sort()
    .map((value) => ({
      value,
      label: providerLabel(value),
    }))
  const eventOptions = [{ value: 'provider-http', label: 'PROVIDER API' }]

  const visible = filterLogLines(lines, { service, minLevel, provider, scope, query })
  const rendered = visible.slice(0, LOG_RENDER_LIMIT)
  const filtered = service != null || minLevel != null || provider != null || scope != null || query !== ''

  function clearFilters() {
    setService(null)
    setMinLevel(null)
    setProvider(null)
    setScope(null)
    setQuery('')
  }

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
        <button
          type="button"
          className={`logs__pause${paused ? ' logs__pause--active' : ''}`}
          onClick={() => setPaused(!paused)}
        >
          {paused ? `Resume · ${formatNumber(pendingCount)} new` : 'Pause'}
        </button>
      </FilterBar>
      <div className="logs__filter-row">
        <div className="logs__filter-cluster">
          <span className="filter-bar__label">PROVIDER</span>
          <FilterChipGroup
            ariaLabel="Filter log lines by provider"
            options={providerOptions}
            value={provider}
            onChange={setProvider}
          />
        </div>
        <div className="logs__filter-cluster">
          <span className="filter-bar__label">EVENTS</span>
          <FilterChipGroup
            ariaLabel="Filter provider API events"
            options={eventOptions}
            value={scope}
            onChange={setScope}
          />
        </div>
        <div className="logs__filter-cluster logs__filter-cluster--level">
          <span className="filter-bar__label">LEVEL</span>
          <FilterChipGroup
            ariaLabel="Minimum log level"
            options={levelOptions}
            value={minLevel}
            onChange={setMinLevel}
          />
        </div>
        {filtered && (
          <button type="button" className="logs__clear" onClick={clearFilters}>
            Clear filters
          </button>
        )}
      </div>

      <Panel
        title={scope === 'provider-http'
          ? `Provider API · ${provider ? providerLabel(provider) : 'all providers'}`
          : 'Live tail · all services'}
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
          <LoadingSkeleton variant="list" rows={7} label="Loading log lines" />
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
