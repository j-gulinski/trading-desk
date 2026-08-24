import { useState } from 'react'
import EmptyState from '../EmptyState.jsx'
import CurveChart from './CurveChart.jsx'
import { apiGet } from '../../services/apiClient.js'
import { endpoints } from '../../services/endpoints.js'
import { CURVE_PALETTE } from '../../config/marketData.js'
import { providerLabel } from '../../config/providers.js'
import { formatClockTime } from '../../domain/formatting.js'

function CurveLegendChip({ curve, color, active, onToggle }) {
  return (
    <button
      type="button"
      className={`curve-legend__chip${active ? '' : ' curve-legend__chip--off'}`}
      aria-pressed={active}
      onClick={onToggle}
    >
      <span className="curve-legend__swatch" style={{ background: color }} aria-hidden="true" />
      <span className="curve-legend__name">{curve.name}</span>
      <span className="curve-legend__meta">
        {curve.currency}
        {curve.indexTenor ? ` · ${curve.indexTenor} index` : ''}
        {` · ${providerLabel(curve.provider)} · as of ${curve.asOfDate ?? '—'}`}
      </span>
    </button>
  )
}

function PointInspector({ curve, point, raw, rawLoading, onLoadRaw }) {
  return (
    <div className="curve-inspector">
      <div className="curve-inspector__head">
        <strong>{curve.name}</strong>
        <span>{point.label}</span>
        <span className="curve-inspector__rate">{point.rate.toFixed(4)}%</span>
        {point.derived && (
          <span className="curve-inspector__derived">INTERPOLATED</span>
        )}
      </div>
      <dl className="curve-inspector__facts">
        <div>
          <dt>Tenor</dt>
          <dd>{point.years} years</dd>
        </div>
        <div>
          <dt>Source series</dt>
          <dd>{point.sourceSeries ?? 'derived between anchors'}</dd>
        </div>
        <div>
          <dt>Source as-of</dt>
          <dd>{point.sourceAsOf ?? curve.asOfDate ?? '—'}</dd>
        </div>
        <div>
          <dt>Set as-of</dt>
          <dd>{curve.asOfDate ?? '—'}</dd>
        </div>
        <div>
          <dt>Provider</dt>
          <dd>{providerLabel(curve.provider)}</dd>
        </div>
        <div>
          <dt>Last read</dt>
          <dd>{formatClockTime(curve.receivedAtMs, { day: true })}</dd>
        </div>
      </dl>
      <details
        className="curve-inspector__raw"
        onToggle={(event) => {
          if (event.target.open && raw === undefined) onLoadRaw()
        }}
      >
        <summary>Raw source response</summary>
        {rawLoading && <p className="curve-inspector__raw-note">Loading raw response…</p>}
        {!rawLoading && raw === null && (
          <p className="curve-inspector__raw-note" role="alert">
            Raw response unavailable — retry by reopening.
          </p>
        )}
        {!rawLoading && raw != null && <pre>{JSON.stringify(raw, null, 2)}</pre>}
      </details>
    </div>
  )
}

export default function CurveSection({ curves }) {
  const list = Object.values(curves).sort((a, b) => a.name.localeCompare(b.name))
  const [hidden, setHidden] = useState(() => new Set())
  const [selectedId, setSelectedId] = useState(null)
  const [rawByCurve, setRawByCurve] = useState({})
  const [rawLoading, setRawLoading] = useState(false)

  const colors = {}
  list.forEach((curve, index) => {
    colors[curve.name] = CURVE_PALETTE[index % CURVE_PALETTE.length]
  })
  const visible = list.filter((curve) => !hidden.has(curve.name))

  const selection = (() => {
    if (selectedId == null) return null
    const [name, label] = selectedId.split(':')
    const curve = curves[name]
    const point = curve?.points.find((item) => item.label === label)
    return curve && point ? { curve, point } : null
  })()

  function toggleCurve(name) {
    setHidden((previous) => {
      const next = new Set(previous)
      if (next.has(name)) next.delete(name)
      else next.add(name)
      return next
    })
  }

  async function loadRaw(name) {
    setRawLoading(true)
    try {
      const payload = await apiGet(endpoints.marketData.curves(true))
      const entries = Array.isArray(payload) ? payload : []
      setRawByCurve((previous) => ({
        ...previous,
        ...Object.fromEntries(
          entries.map((entry) => [entry.curve_name, entry.raw_payload ?? null]),
        ),
      }))
    } catch {
      setRawByCurve((previous) => ({ ...previous, [name]: null }))
    } finally {
      setRawLoading(false)
    }
  }

  return (
    <section className="market-section curve-section" aria-labelledby="curve-section-title">
      <div className="market-section__head">
        <div>
          <h2 id="curve-section-title">Rate curves</h2>
          <p>Latest stored set per curve</p>
        </div>
        {list.length > 0 && (
          <div className="market-section__actions">
            <span>Select a point for source detail</span>
            <span>{list.length} curves</span>
          </div>
        )}
      </div>
      {list.length === 0 ? (
        <EmptyState message="No curve sets stored yet." />
      ) : (
        <>
          <div className="curve-legend" role="group" aria-label="Curves shown on the chart">
            {list.map((curve) => (
              <CurveLegendChip
                key={curve.name}
                curve={curve}
                color={colors[curve.name]}
                active={!hidden.has(curve.name)}
                onToggle={() => toggleCurve(curve.name)}
              />
            ))}
          </div>
          {visible.length === 0 ? (
            <EmptyState message="Every curve is hidden — turn one back on above." />
          ) : (
            <CurveChart
              curves={visible}
              colors={colors}
              selectedId={selectedId}
              onSelectPoint={(name, index) => {
                const curve = curves[name]
                const point = curve?.points[index]
                if (point) setSelectedId(`${name}:${point.label}`)
              }}
            />
          )}
          {selection && (
            <PointInspector
              curve={selection.curve}
              point={selection.point}
              raw={rawByCurve[selection.curve.name]}
              rawLoading={rawLoading}
              onLoadRaw={() => loadRaw(selection.curve.name)}
            />
          )}
        </>
      )}
    </section>
  )
}
