import { providerScheduleText } from '../../domain/marketData.js'
import { providerLabel, PROVIDER_STATUS_LEVELS } from '../../config/providers.js'
import StatusPill from '../status/StatusPill.jsx'

export default function ProviderStrategyStrip({ providers }) {
  const wired = (Array.isArray(providers) ? providers : []).filter(
    (provider) => provider.wired && provider.runtime && provider.group === 'QUOTE',
  )
  if (wired.length === 0) return null

  return (
    <ul className="provider-strategy" aria-label="Current provider poll strategies">
      {wired.map(({ provider, runtime }) => (
        <li key={provider} className="provider-strategy__item">
          <span className="provider-strategy__name">{providerLabel(provider)}</span>
          <StatusPill
            level={PROVIDER_STATUS_LEVELS[runtime.status] ?? 'unknown'}
            label={runtime.status}
            compact
          />
          <span
            className="provider-strategy__text"
            title={providerScheduleText({ runtime })}
          >
            {providerScheduleText({ runtime })}
          </span>
        </li>
      ))}
    </ul>
  )
}
