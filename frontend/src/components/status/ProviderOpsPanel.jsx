import { usePolling } from '../../hooks/usePolling.js'
import { useElapsedTime } from '../../hooks/useElapsedTime.js'
import { apiGet } from '../../services/apiClient.js'
import { endpoints } from '../../services/endpoints.js'
import { PROVIDERS_POLL_INTERVAL_MS } from '../../config/marketData.js'
import { providerLabel, PROVIDER_STATUS_LEVELS } from '../../config/providers.js'
import { providerScheduleText } from '../../domain/marketData.js'
import { formatElapsedTime, formatNumber } from '../../domain/formatting.js'
import Panel from '../Panel.jsx'
import EmptyState from '../EmptyState.jsx'
import StatusPill from './StatusPill.jsx'

const GROUP_TITLES = {
  QUOTE: 'Quote providers',
  OFFICIAL: 'Reference data',
}

function BudgetGauge({ label, used, capacity, detail }) {
  const share = capacity > 0 ? Math.min(1, Math.max(0, used / capacity)) : 0
  return (
    <div className="provider-card__gauge">
      <div className="provider-card__gauge-head">
        <span>{label}</span>
        <span>{detail}</span>
      </div>
      <div
        className="provider-card__gauge-track"
        role="meter"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={capacity}
        aria-valuenow={used}
      >
        <div
          className={`provider-card__gauge-fill${share >= 0.9 ? ' provider-card__gauge-fill--hot' : ''}`}
          style={{ transform: `scaleX(${share.toFixed(3)})` }}
        />
      </div>
    </div>
  )
}

function marketSessionText(runtime) {
  const states = runtime?.market_states ?? {}
  const open = Number(states.open) || 0
  const closed = Number(states.closed) || 0
  const unknown = Number(states.unknown) || 0
  const total = open + closed + unknown
  if (total === 0) return '—'
  if (open === total) return 'open'
  if (closed === total) return 'closed'
  if (unknown === total) return 'awaiting quotes'
  return [
    open > 0 && `${open} open`,
    closed > 0 && `${closed} closed`,
    unknown > 0 && `${unknown} pending`,
  ].filter(Boolean).join(' · ')
}

function Fact({ label, children }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  )
}

function ProviderCard({ provider, now }) {
  const runtime = provider.runtime
  if (!provider.wired) {
    return (
      <article className="provider-card provider-card--unwired">
        <header className="provider-card__head">
          <h3>{providerLabel(provider.provider)}</h3>
          <StatusPill level="unknown" label="NOT AVAILABLE" compact />
        </header>
      </article>
    )
  }

  const budget = runtime?.budget ?? {}
  const strategy = runtime?.strategy ?? {}
  const keyless = runtime?.keyless === true
  const minuteUsed = Math.max(0, (budget.capacity ?? 0) - (budget.tokens_available ?? 0))
  const cooldown = runtime?.cooldown_seconds_left ?? 0
  const lastSuccessMs = Date.parse(runtime?.last_success_at ?? '')

  const budgetUnit = budget.daily_budget == null ? 'requests' : 'credits'

  return (
    <a
      className="provider-card provider-card--linked"
      href={`#/logs?service=market-data-service&provider=${encodeURIComponent(
        provider.provider,
      )}&scope=provider-http`}
      aria-label={`View ${providerLabel(provider.provider)} logs`}
    >
      <header className="provider-card__head">
        <h3>{providerLabel(provider.provider)}</h3>
        {keyless && (
          <span
            className="provider-card__keyless"
            title="Official source — no API key, no rate-limit budget"
          >
            KEYLESS
          </span>
        )}
        <StatusPill
          level={PROVIDER_STATUS_LEVELS[runtime?.status] ?? 'unknown'}
          label={runtime?.status ?? 'UNKNOWN'}
          compact
        />
      </header>
      <p className="provider-card__strategy">{providerScheduleText(provider)}</p>
      <dl className="provider-card__facts">
        {keyless ? (
          <Fact label="Last fixing">{strategy.last_as_of ?? '—'}</Fact>
        ) : (
          <Fact label="Market">{marketSessionText(runtime)}</Fact>
        )}
        <Fact label="Polling">
          {runtime?.active_symbols?.length ?? 0} symbols
        </Fact>
        <Fact label={keyless ? 'Last read' : 'Last quote'}>
          {Number.isFinite(lastSuccessMs) ? formatElapsedTime(now - lastSuccessMs) : '—'}
        </Fact>
        <Fact label="Calls today">{formatNumber(budget.requests_today ?? 0)}</Fact>
      </dl>
      {budget.capacity != null && (
        <BudgetGauge
          label="Rate limit"
          used={minuteUsed}
          capacity={budget.capacity ?? 0}
          detail={`${budget.tokens_available ?? 0} of ${budget.capacity ?? 0} safe ${budgetUnit} available${
            budget.provider_minute_limit
              ? ` · ${budget.usage_percent}% of ${budget.provider_minute_limit}/min`
              : ''
          }`}
        />
      )}
      {budget.daily_budget != null && (
        <BudgetGauge
          label="Credits today"
          used={budget.credits_today ?? 0}
          capacity={budget.daily_budget}
          detail={`${formatNumber(budget.credits_today ?? 0)} counted · ${formatNumber(budget.daily_budget)} safe of ${formatNumber(budget.provider_daily_limit)}/day · ${budget.active_window_hours}h window${
            strategy.on_pace === false ? ' · ahead of pace' : ''
          }`}
        />
      )}
      {cooldown > 0 && (
        <p className="provider-card__note provider-card__note--warn">
          Cooling down — next poll in {cooldown}s
        </p>
      )}
      {runtime?.last_error && (
        <p className="provider-card__note provider-card__note--warn provider-card__note--clamped"
          title={runtime.last_error}>
          {runtime.last_error}
        </p>
      )}
      <span className="provider-card__logs">View provider logs →</span>
    </a>
  )
}

export default function ProviderOpsPanel() {
  const { data, error, loading } = usePolling(
    ({ signal }) => apiGet(endpoints.marketData.providers, { signal }),
    { intervalMs: PROVIDERS_POLL_INTERVAL_MS },
  )
  const { now } = useElapsedTime()
  const providers = Array.isArray(data) ? data : []
  const wiredCount = providers.filter((provider) => provider.wired).length
  const groups = ['QUOTE', 'OFFICIAL'].filter((group) =>
    providers.some((provider) => provider.group === group),
  )

  return (
    <Panel
      title="Market data providers"
      meta={error ? 'UNAVAILABLE' : `${wiredCount} feeding`}
    >
      {loading && <EmptyState message="Loading provider status…" />}
      {!loading && error && (
        <EmptyState message="Provider status unavailable — retrying." />
      )}
      {!loading &&
        !error &&
        groups.map((group) => (
          <section key={group} className="provider-group">
            <h3 className="provider-group__title">{GROUP_TITLES[group] ?? group}</h3>
            <div className={`provider-grid provider-grid--${group.toLowerCase()}`}>
              {providers
                .filter((provider) => provider.group === group)
                .map((provider) => (
                  <ProviderCard key={provider.provider} provider={provider} now={now} />
                ))}
            </div>
          </section>
        ))}
    </Panel>
  )
}
