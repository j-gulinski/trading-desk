import { useCallback, useEffect, useState } from 'react'
import { usePolling } from '../../hooks/usePolling.js'
import { useElapsedTime } from '../../hooks/useElapsedTime.js'
import { apiGet, apiPost } from '../../services/apiClient.js'
import { endpoints } from '../../services/endpoints.js'
import { normalizeAuditEvents } from '../../domain/auditEvents.js'
import {
  generatorStatusOf,
  intentRowsOf,
  summarizeIntents,
} from '../../domain/generator.js'
import {
  formatElapsedTime,
  formatNumber,
} from '../../domain/formatting.js'
import Panel from '../../components/Panel.jsx'
import EmptyState from '../../components/EmptyState.jsx'
import StatCard from '../../components/cards/StatCard.jsx'
import StatusPill from '../../components/status/StatusPill.jsx'
import IntentFeed from '../../components/generator/IntentFeed.jsx'
import {
  ACTION_EVENT_TYPES,
  ACTION_SERVICE,
  BOOKS_POLL_INTERVAL_MS,
  FEED_LIMIT,
  FEED_POLL_INTERVAL_MS,
  INTERVAL_BOUNDS,
  STATUS_POLL_INTERVAL_MS,
  TARGET_BOUNDS,
} from '../../config/generator.js'

// The generator opens into one book per asset class, so the books are the
// authoritative list of what it can trade. The market feed is the wrong source:
// it carries INDEX (a benchmark, never traded) and omits BOND (priced off the
// curve, never ticked).
function assetClassesOf(books) {
  if (!Array.isArray(books)) return []
  return [...new Set(books.map((book) => book.expected_asset_class).filter(Boolean))].sort()
}

function percentLabel(value, decimals = 2) {
  if (!Number.isFinite(value)) return '—'
  const formatted = new Intl.NumberFormat('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value)
  return `${formatted}%`
}

function clampInteger(value, { min, max }) {
  if (!Number.isFinite(value)) return null
  return Math.max(min, Math.min(max, Math.round(value)))
}

export default function Generator() {
  const [draft, setDraft] = useState({})
  const [pending, setPending] = useState(false)
  const [actionError, setActionError] = useState(null)

  const status = usePolling(
    ({ signal }) => apiGet(endpoints.tradeGeneration.status, { signal }),
    { intervalMs: STATUS_POLL_INTERVAL_MS },
  )

  const feed = usePolling(
    ({ signal }) => apiGet(
      endpoints.monitoring.audits({
        service: ACTION_SERVICE,
        event_type: ACTION_EVENT_TYPES,
        limit: FEED_LIMIT,
      }),
      { signal },
    ),
    { intervalMs: FEED_POLL_INTERVAL_MS },
  )

  const books = usePolling(
    ({ signal }) => apiGet(endpoints.blotter.booksSummary, { signal }),
    { intervalMs: BOOKS_POLL_INTERVAL_MS },
  )

  const { elapsedMs: pollAgeMs } = useElapsedTime(status.lastPolled)

  const generator = generatorStatusOf(status.data)
  const rows = intentRowsOf(normalizeAuditEvents(feed.data), { generatedOnly: true })
  const intents = summarizeIntents(rows)
  const assetClasses = assetClassesOf(books.data)
  const running = generator.running
  const refetchStatus = status.refetch

  const send = useCallback(async (fn) => {
    setPending(true)
    setActionError(null)
    try {
      await fn()
      return true
    } catch (err) {
      setActionError(err?.message ?? 'Request failed')
      return false
    } finally {
      setPending(false)
    }
  }, [])

  const commitConfig = useCallback(async (patch) => {
    const ok = await send(() => apiPost(endpoints.tradeGeneration.config, patch))
    if (!ok) return false
    await refetchStatus()
    setDraft((current) => {
      let hasChange = false
      const next = { ...current }
      for (const [key, value] of Object.entries(patch)) {
        if (next[key] === value) {
          delete next[key]
          hasChange = true
        }
      }
      return hasChange ? next : current
    })
    return true
  }, [refetchStatus, send])

  const handleIntervalChange = useCallback((event) => {
    setDraft((d) => ({ ...d, interval_ms: Number(event.target.value) }))
  }, [])

  const handleTargetBlur = useCallback(() => {
    const next = clampInteger(draft.target_open_trades, {
      min: TARGET_BOUNDS.min,
      max: TARGET_BOUNDS.max,
    })
    if (next == null) return
    setDraft((current) => {
      if (current.target_open_trades === next) return current
      return { ...current, target_open_trades: next }
    })
    if (next !== generator.targetOpenTrades) {
      commitConfig({ target_open_trades: next })
    }
  }, [commitConfig, draft.target_open_trades, generator.targetOpenTrades])

  useEffect(() => {
    const interval = draft.interval_ms
    if (interval == null || interval === generator.intervalMs) return

    const timer = setTimeout(() => {
      commitConfig({ interval_ms: interval })
    }, 120)

    return () => clearTimeout(timer)
  }, [commitConfig, draft.interval_ms, generator.intervalMs])

  const toggleRunning = useCallback(() => {
    const path = running ? endpoints.tradeGeneration.stop : endpoints.tradeGeneration.start
    send(() => apiPost(path, {})).then((ok) => {
      if (ok) refetchStatus()
    })
  }, [refetchStatus, running, send])

  const generateOnce = useCallback(() => {
    send(() => apiPost(endpoints.tradeGeneration.generateOnce, {})).then((ok) => {
      if (ok) refetchStatus()
    })
  }, [refetchStatus, send])

  const intervalValue = draft.interval_ms ?? generator.intervalMs
  const targetValue = draft.target_open_trades ?? generator.targetOpenTrades
  const unreachable = status.error != null
  const capacityPercent = Number.isFinite(generator.openTrades)
    && Number.isFinite(generator.targetOpenTrades)
    && generator.targetOpenTrades > 0
    ? (generator.openTrades / generator.targetOpenTrades) * 100
    : null

  return (
    <section className="page">
      <div className="generator">
        <div className="generator__controls">
          <Panel
            title="Generator controls"
            meta={
              unreachable
                ? <StatusPill level="down" label="UNAVAILABLE" />
                : (
                  <StatusPill
                    level={running ? 'healthy' : 'stale'}
                    label={running ? 'RUNNING' : 'STOPPED'}
                  />
                )
            }
          >
            {status.loading && <EmptyState message="Loading generator status…" />}

            {!status.loading && unreachable && (
              <EmptyState message="Trade generation service unavailable — retrying." />
            )}

            {!status.loading && !unreachable && (
              <div className="generator__form">
                <div className="generator__row">
                  <button
                    type="button"
                    className={`generator__toggle${running ? ' generator__toggle--on' : ''}`}
                    onClick={toggleRunning}
                    disabled={pending}
                    aria-pressed={running}
                  >
                    <span className="generator__toggle-track">
                      <span className="generator__toggle-knob" />
                    </span>
                    Generator running
                  </button>
                  <button
                    type="button"
                    className="generator__once"
                    onClick={generateOnce}
                    disabled={pending}
                  >
                    Generate once
                  </button>
                </div>

                {actionError && <div className="generator__error">{actionError}</div>}

                <label className="generator__field" htmlFor="generator-interval">
                  <span className="generator__label">
                    Interval · {intervalValue != null ? `${formatNumber(intervalValue)} ms` : '—'}
                  </span>
                  <input
                    id="generator-interval"
                    type="range"
                    min={INTERVAL_BOUNDS.min}
                    max={INTERVAL_BOUNDS.max}
                    step={INTERVAL_BOUNDS.step}
                    value={intervalValue ?? INTERVAL_BOUNDS.min}
                    disabled={intervalValue == null}
                    onChange={handleIntervalChange}
                  />
                </label>

                <label className="generator__field" htmlFor="generator-target">
                  <span className="generator__label">Max active positions</span>
                  <input
                    id="generator-target"
                    type="number"
                    className="generator__number"
                    min={TARGET_BOUNDS.min}
                    max={TARGET_BOUNDS.max}
                    step={TARGET_BOUNDS.step}
                    value={targetValue ?? ''}
                    disabled={pending || targetValue == null}
                    onChange={(e) => setDraft((d) => ({
                      ...d,
                      target_open_trades: Number(e.target.value),
                    }))}
                    onBlur={handleTargetBlur}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') e.currentTarget.blur()
                    }}
                  />
                </label>

                <div className="generator__field">
                  <span className="generator__label">Close probability · derived</span>
                  <div className="generator__derived">
                    <strong>
                      {generator.closeProbability != null
                        ? `${(generator.closeProbability * 100).toFixed(1)}%`
                        : '—'}
                    </strong>
                    <code>min(0.9, 0.5 × open / target)</code>
                  </div>
                </div>

                <div className="generator__field">
                  <span className="generator__label">Asset classes · one book each</span>
                  <div className="generator__chips">
                    {assetClasses.length > 0
                      ? assetClasses.map((assetClass) => (
                        <span key={assetClass} className="generator__chip">{assetClass}</span>
                      ))
                      : (
                        <span className="generator__muted">
                          {books.error ? 'Book list unavailable.' : 'Loading books…'}
                        </span>
                      )}
                  </div>
                </div>
              </div>
            )}
          </Panel>

          <div className="generator__stats">
            <StatCard
              label="OPEN TRADES"
              value={unreachable ? '—' : formatNumber(generator.openTrades)}
              sub={generator.targetOpenTrades != null
                ? `target ${formatNumber(generator.targetOpenTrades)}`
                : 'target unknown'}
            />
            <StatCard
              label="CAPACITY"
              value={unreachable || capacityPercent == null
                ? '—'
                : percentLabel(capacityPercent, 2)}
              sub="open / target"
            />
            <StatCard
              label="OPENED"
              value={unreachable ? '—' : formatNumber(generator.opened)}
              sub="this process"
            />
            <StatCard
              label="CLOSED"
              value={unreachable ? '—' : formatNumber(generator.closed)}
              sub="this process"
            />
            <StatCard
              label="FAILED"
              value={unreachable ? '—' : formatNumber(generator.failed)}
              sub="submission errors"
              tone={generator.failed > 0 ? 'warn' : 'default'}
            />
          </div>
        </div>

        <Panel
          title="Live intent feed"
          meta={
            <>
              {feed.error
                ? <StatusPill level="down" label="UNAVAILABLE" />
                : <StatusPill level="healthy" label="LIVE" />}
              <span>
                {intents.opened} in · {intents.closed} out
                {intents.rejected > 0 && ` · ${intents.rejected} rejected`}
                {pollAgeMs != null && ` · ${formatElapsedTime(pollAgeMs)}`}
              </span>
            </>
          }
        >
          {feed.loading && <EmptyState message="Loading recent intents…" />}
          {!feed.loading && feed.error && (
            <EmptyState message="Audit feed unavailable — retrying." />
          )}
          {!feed.loading && !feed.error && rows.length === 0 && (
            <EmptyState message="No generated intents recorded yet. Start the generator to produce some." />
          )}
          {!feed.loading && !feed.error && rows.length > 0 && <IntentFeed rows={rows} />}
        </Panel>
      </div>
    </section>
  )
}
