import { useEffect, useRef, useState } from 'react'
import EmptyState from '../EmptyState.jsx'
import LoadingSkeleton from '../LoadingSkeleton.jsx'
import FilterChipGroup from '../filters/FilterChipGroup.jsx'
import CurveChart from './CurveChart.jsx'
import { apiGet } from '../../services/apiClient.js'
import { endpoints } from '../../services/endpoints.js'
import { CURVE_PALETTE, CURVE_TEXT } from '../../config/marketData.js'
import {
  curveBasisText,
  curveSourceName,
  curveTradeUse,
  curveTitle,
  indexTenorText,
} from '../../domain/curves.js'
import { formatClockTime, formatLongDate } from '../../domain/formatting.js'

function CurveLegendRow({ curve, color }) {
  const text = CURVE_TEXT[curve.name]
  return (
    <article
      className="curve-legend__row"
      title={text?.hint}
    >
      <span className="curve-legend__swatch" style={{ background: color }} aria-hidden="true" />
      <span className="curve-legend__text">
        <span className="curve-legend__title">{curveTitle(curve)}</span>
        <span className="curve-legend__facts">
          <span>
            <small>Trade use</small>
            {curveTradeUse(curve)}
          </span>
          <span>
            <small>Basis</small>
            {curveBasisText(curve.curveBasis)}
          </span>
          {curve.indexTenor && (
            <span>
              <small>Index</small>
              {indexTenorText(curve.indexTenor)}
            </span>
          )}
          <span>
            <small>As of</small>
            {formatLongDate(curve.asOfDate)}
          </span>
          <span>
            <small>Source</small>
            {curveSourceName(curve.provider)}
          </span>
        </span>
      </span>
    </article>
  )
}

function PointInspector({ curve, point, raw, rawLoading, onLoadRaw }) {
  const containerRef = useRef(null)
  const title = curveTitle(curve)

  useEffect(() => {
    containerRef.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }, [curve.name, point.label])

  return (
    <div className="curve-inspector" ref={containerRef}>
      <div className="curve-inspector__head">
        <strong>{title}</strong>
        <span>{point.label}</span>
        <span className="curve-inspector__rate">{point.rate.toFixed(4)}%</span>
        {point.derived && (
          <span className="curve-inspector__derived">DERIVED</span>
        )}
      </div>
      <dl className="curve-inspector__facts">
        <div>
          <dt>System key</dt>
          <dd>{curve.name}</dd>
        </div>
        <div>
          <dt>Tenor</dt>
          <dd>{point.years} years</dd>
        </div>
        <div>
          <dt>Basis</dt>
          <dd>{curveBasisText(curve.curveBasis)}</dd>
        </div>
        <div>
          <dt>Trade use</dt>
          <dd>{curveTradeUse(curve)}</dd>
        </div>
        <div>
          <dt>Published series</dt>
          <dd>{point.sourceSeries ?? '—'}</dd>
        </div>
        <div>
          <dt>Series published</dt>
          <dd>{point.sourceAsOf ? formatLongDate(point.sourceAsOf) : '—'}</dd>
        </div>
        <div>
          <dt>Curve as of</dt>
          <dd>{formatLongDate(curve.asOfDate)}</dd>
        </div>
        <div>
          <dt>Source</dt>
          <dd>{curveSourceName(curve.provider)}</dd>
        </div>
        <div>
          <dt>Last read</dt>
          <dd>{formatClockTime(curve.receivedAtMs, { day: true })}</dd>
        </div>
      </dl>
      <details
        className="curve-inspector__raw"
        onToggle={(event) => {
          if (event.target.open && raw == null) onLoadRaw()
        }}
      >
        <summary>Raw source response</summary>
        {rawLoading && (
          <LoadingSkeleton variant="panel" rows={2} label="Loading raw curve response" />
        )}
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

function emptyMessageOf(seedStatus) {
  if (seedStatus === 'error') {
    return 'Could not load the market snapshot — retrying on reconnect.'
  }
  return 'No curve sets stored yet.'
}

export default function CurveSection({ curves, seedStatus }) {
  const stored = Object.values(curves).sort((a, b) =>
    curveTitle(a).localeCompare(curveTitle(b)),
  )
  const currencies = [...new Set(stored.map((curve) => curve.currency))].sort()
  const [currency, setCurrency] = useState(null)
  const [selectedId, setSelectedId] = useState(null)
  const [rawByCurve, setRawByCurve] = useState({})
  const [rawLoading, setRawLoading] = useState(false)

  const shown = currency ?? currencies[0] ?? null
  const list = stored.filter((curve) => curve.currency === shown)

  const colors = {}
  list.forEach((curve, index) => {
    colors[curve.name] = CURVE_PALETTE[index % CURVE_PALETTE.length]
  })

  const selection = (() => {
    if (selectedId == null) return null
    const [name, label] = selectedId.split(':')
    const curve = curves[name]
    const point = curve?.points.find((item) => item.label === label)
    return curve && point ? { curve, point } : null
  })()

  async function loadRaw(name) {
    if (rawLoading) return
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
        <h2 id="curve-section-title">Rate curves</h2>
        {stored.length > 0 && (
          <div className="market-section__actions">
            <FilterChipGroup
              ariaLabel="Currency shown on the chart"
              options={currencies.map((code) => ({
                value: code,
                label: code,
                count: stored.filter((curve) => curve.currency === code).length,
              }))}
              value={shown}
              onChange={(next) => {
                setCurrency(next ?? shown)
                setSelectedId(null)
              }}
            />
            <span>Compare rates by maturity · select a point for its source</span>
          </div>
        )}
      </div>
      {list.length === 0 && seedStatus === 'loading' ? (
        <LoadingSkeleton variant="panel" rows={6} label="Loading rate curves" />
      ) : list.length === 0 ? (
        <EmptyState message={emptyMessageOf(seedStatus)} />
      ) : (
        <div className="curve-body">
          <div className="curve-legend" aria-label={`Curves available in ${shown}`}>
            {list.map((curve) => (
              <CurveLegendRow
                key={curve.name}
                curve={curve}
                color={colors[curve.name]}
              />
            ))}
          </div>
          <div className="curve-plot">
            <div className="curve-plot__head">
              <strong>{shown} curves</strong>
            </div>
            <CurveChart
              curves={list}
              colors={colors}
              selectedId={selectedId}
              onSelectPoint={(name, index) => {
                const curve = curves[name]
                const point = curve?.points[index]
                if (point) setSelectedId(`${name}:${point.label}`)
              }}
            />
          </div>
          {selection && (
            <PointInspector
              curve={selection.curve}
              point={selection.point}
              raw={rawByCurve[selection.curve.name]}
              rawLoading={rawLoading}
              onLoadRaw={() => loadRaw(selection.curve.name)}
            />
          )}
        </div>
      )}
    </section>
  )
}
