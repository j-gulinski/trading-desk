import { providerScheduleText } from '../../domain/marketData.js'
import { providerLabel, PROVIDER_STATUS_LEVELS } from '../../config/providers.js'
import StatusPill from '../status/StatusPill.jsx'

export default function ProviderStrategyStrip({ providers, now, snapshotAtMs }) {
  const wired = (Array.isArray(providers) ? providers : []).filter(
    (provider) => provider.wired && provider.runtime && provider.group === 'QUOTE',
  )
  if (wired.length === 0) return null

  return (
    <ul className="provider-strategy" aria-label="Current provider poll strategies">
      {wired.map(({ provider, runtime }) => {
        const elapsedMs = Number.isFinite(snapshotAtMs) ? Math.max(0, now - snapshotAtMs) : 0
        const schedule = providerScheduleText({ runtime }, elapsedMs)
        return (
          <li key={provider} className="provider-strategy__item">
            <span className="provider-strategy__name">{providerLabel(provider)}</span>
            <StatusPill
              level={PROVIDER_STATUS_LEVELS[runtime.status] ?? 'unknown'}
              label={runtime.status === 'OK' ? 'AVAILABLE' : runtime.status}
              compact
            />
            <span className="provider-strategy__text" title={schedule}>
              {schedule}
            </span>
          </li>
        )
      })}
    </ul>
  )
}
