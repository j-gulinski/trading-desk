import NumberField from './NumberField.jsx'
import { curveChoicesFor } from '../../domain/tradeActions.js'
import { hasTermField, ticketFieldsOf } from '../../domain/ticket.js'
import {
  curveBasisText,
  curveOptionLabel,
  curveSourceName,
  indexTenorText,
} from '../../domain/curves.js'
import { useCurveHint } from '../../hooks/useCurveHint.js'
import {
  CURVE_ROLE_HINTS,
} from '../../config/marketData.js'
import { formatLongDate } from '../../domain/formatting.js'

const CURVE_FIELDS = ['discount_curve']

function choiceLabel(field, value) {
  return field.labels?.[value] ?? value
}

function pointAt(curve, years) {
  return curve.points.find((point) => point.years === years)
}

function readingOf(curve, hint) {
  const [first, second] = hint.tenors.map((years) => pointAt(curve, years))
  if (hint.method === 'POINT') return first?.derived ? 'derived curve point' : 'published curve point'
  if (hint.method === 'FLAT_BEFORE') return 'flat extrapolation from the shortest point'
  if (hint.method === 'FLAT_AFTER') return 'flat extrapolation from the longest point'
  return `linear interpolation between ${first?.label ?? hint.tenors[0]} and ${second?.label ?? hint.tenors[1]}`
}

function CurveMarketContext({ curve, hint, suggestCoupon, onChange }) {
  if (hint == null) return null
  const parCoupon = suggestCoupon ? hint.par_rate_percent : null

  return (
    <div className="panel-form__curve-market" role="note">
      <div className="panel-form__curve-market-line">
        <span>
          {hint.maturity_years}Y {hint.zero_rate_percent.toFixed(4)}% · DF {hint.discount_factor.toFixed(4)}
        </span>
        {parCoupon != null && (
          <button
            type="button"
            className="panel-form__inline-action"
            onClick={() => onChange('coupon_rate', parCoupon.toFixed(4))}
          >
            Use par {parCoupon.toFixed(4)}%
          </button>
        )}
      </div>
      <details className="panel-form__curve-points">
        <summary>{readingOf(curve, hint)} · {curve.points.length} points</summary>
        <dl>
          {curve.points.map((point) => (
            <div key={`${curve.name}:${point.label}`}>
              <dt>{point.label}</dt>
              <dd>
                {point.rate.toFixed(4)}%
                {point.derived ? ' · derived' : ''}
              </dd>
            </div>
          ))}
        </dl>
      </details>
    </div>
  )
}

function CurveSelect({
  schema,
  field,
  value,
  curves,
  marketCurves,
  currency,
  maturityYears,
  paymentsPerYear,
  indexTenor,
  assetClass,
  onChange,
}) {
  const waitingForUnderlying = schema.underlying_field != null && !currency
  const waitingForCurrency = hasTermField(schema, 'settlement_currency') && !currency
  const choices = waitingForUnderlying || waitingForCurrency
    ? []
    : curveChoicesFor(curves, currency, indexTenor, assetClass)
  const selected = choices.find((curve) => curve.curve_name === value)
  const marketCurve = selected ? marketCurves?.[value] : null
  const suggestCoupon = hasTermField(schema, 'coupon_rate')
  const hint = useCurveHint(
    marketCurve ? value : null,
    maturityYears,
    suggestCoupon ? { payments_per_year: paymentsPerYear } : {},
  )
  const automaticallyResolved = selected != null && choices.length === 1
  return (
    <>
    {automaticallyResolved ? (
      <div
        id={`term-${field.name}`}
        className="panel-form__curve-selection"
        role="status"
        aria-labelledby={`term-${field.name}-label`}
        title={`Only eligible ${currency} curve for this role`}
      >
        <span>{curveOptionLabel(selected)}</span>
        <span className="panel-form__curve-selection-mode">Auto</span>
      </div>
    ) : (
      <select
        id={`term-${field.name}`}
        className="panel-form__select"
        value={selected ? value : ''}
        disabled={choices.length === 0}
        onChange={(event) => onChange(field.name, event.target.value)}
      >
        <option value="">
          {waitingForUnderlying
            ? 'Choose underlying first'
            : waitingForCurrency
              ? 'Choose currency first'
              : curves.length === 0
                ? 'No curves stored yet'
                : choices.length === 0
                  ? `No ${currency ? `${currency} ` : ''}curve can take this role`
                  : 'Choose discount curve…'}
        </option>
        {choices.map((curve) => (
          <option key={curve.curve_name} value={curve.curve_name}>
            {curveOptionLabel(curve)}
          </option>
        ))}
      </select>
    )}
    {selected && (
      <details className="panel-form__curve-provenance">
        <summary>
          <span>{selected.provider}</span>
          <span>as of {formatLongDate(selected.as_of_date)}</span>
        </summary>
        <dl className="panel-form__curve-facts">
          <div>
            <dt>In this trade</dt>
            <dd>{field.role_text ?? field.label}</dd>
          </div>
          <div>
            <dt>Basis</dt>
            <dd>{curveBasisText(selected.curve_basis)}</dd>
          </div>
          {selected.index_tenor && (
            <div>
              <dt>Index</dt>
              <dd>{indexTenorText(selected.index_tenor)}</dd>
            </div>
          )}
          <div>
            <dt>As of</dt>
            <dd>{formatLongDate(selected.as_of_date)}</dd>
          </div>
          <div>
            <dt>Source</dt>
            <dd>{curveSourceName(selected.provider)}</dd>
          </div>
        </dl>
      </details>
    )}
    {selected?.stale === true && (
      <p className="panel-form__error" role="status">
        {`Stale by this curve’s ${selected.stale_after_days}-day limit.`}
      </p>
    )}
    {marketCurve && (
      <CurveMarketContext
        curve={marketCurve}
        hint={hint}
        suggestCoupon={suggestCoupon}
        onChange={onChange}
      />
    )}
    </>
  )
}

function Field({
  schema,
  field,
  values,
  curves,
  marketCurves,
  currency,
  assetClass,
  onChange,
  visuallyHideLabel = false,
}) {
  const isCurve = CURVE_FIELDS.includes(field.name)
  const isModel = field.name === 'model'
  const swapRate = field.name === 'fixed_rate' && hasTermField(schema, 'floating_rate_index_tenor')
  const fairRate = useCurveHint(
    swapRate && marketCurves?.[values.discount_curve] ? values.discount_curve : null,
    values.maturity_years,
    { index_tenor: values.floating_rate_index_tenor },
  )?.par_rate_percent ?? null
  return (
    <div className={`panel-form__field${isCurve || isModel ? ' panel-form__field--wide' : ''}`}>
      <label
        id={`term-${field.name}-label`}
        className={`panel-form__label${visuallyHideLabel ? ' panel-form__label--sr-only' : ''}${
          CURVE_ROLE_HINTS[field.name] && !visuallyHideLabel
            ? ' panel-form__label--hinted'
            : ''
        }`}
        htmlFor={`term-${field.name}`}
        title={CURVE_ROLE_HINTS[field.name]}
      >
        {field.label}
      </label>
      {field.type === 'choice' && field.choices_source === 'CURVES' ? (
        <CurveSelect
          schema={schema}
          field={field}
          value={values[field.name]}
          curves={curves}
          marketCurves={marketCurves}
          currency={currency}
          maturityYears={values.maturity_years}
          paymentsPerYear={values.payments_per_year}
          indexTenor={values.floating_rate_index_tenor}
          assetClass={assetClass}
          onChange={onChange}
        />
      ) : field.type === 'choice' ? (
        <select
          id={`term-${field.name}`}
          className="panel-form__select"
          value={values[field.name] ?? ''}
          disabled={field.choices.length === 0}
          onChange={(event) => onChange(field.name, event.target.value)}
        >
          <option value="">
            {field.choices.length === 0 ? 'No choice available' : 'Select…'}
          </option>
          {field.choices.map((choice) => (
            <option key={choice} value={choice}>
              {choiceLabel(field, choice)}
            </option>
          ))}
        </select>
      ) : (
        <NumberField
          id={`term-${field.name}`}
          value={values[field.name] ?? ''}
          onChange={(next) => onChange(field.name, next)}
        />
      )}
      {fairRate != null && (
        <div className="panel-form__field-assist" role="note">
          <button
            type="button"
            className="panel-form__inline-action"
            aria-label={`Use fair fixed rate ${fairRate.toFixed(4)}%`}
            title="Use the curve-implied fair fixed rate"
            onClick={() => onChange('fixed_rate', fairRate.toFixed(4))}
          >
            Use fair {fairRate.toFixed(4)}%
          </button>
        </div>
      )}
    </div>
  )
}

export default function TermFields({
  schema,
  values,
  curves,
  marketCurves,
  currency,
  assetClass,
  onChange,
  executionFields,
}) {
  const fields = ticketFieldsOf(schema, values)
  const contract = fields.filter((field) => !CURVE_FIELDS.includes(field.name))
  const curveFields = fields.filter((field) => CURVE_FIELDS.includes(field.name))
  const compactSingleCurve = curveFields.length === 1
  const denseTerms = contract.length >= 4

  return (
    <div className="panel-form__model-layout">
      <div className="panel-form__group panel-form__group--contract">
        <h3 className="panel-form__group-title">Model contract</h3>
        <div className={`panel-form__terms${denseTerms ? ' panel-form__terms--dense' : ''}`}>
          {contract.map((field) => (
            <Field
              key={field.name}
              schema={schema}
              field={field}
              values={values}
              curves={curves}
              marketCurves={marketCurves}
              currency={currency}
              assetClass={assetClass}
              onChange={onChange}
            />
          ))}
        </div>
      </div>
      {executionFields}
      {curveFields.length > 0 && (
        <div className="panel-form__group panel-form__group--curves">
          <h3 className="panel-form__group-title">
            {compactSingleCurve ? 'Pricing curve' : 'Curves'}
          </h3>
          <div
            className={`panel-form__terms${
              curveFields.length > 1 ? ' panel-form__terms--paired-curves' : ''
            }`}
          >
            {curveFields.map((field) => (
              <Field
                key={field.name}
                schema={schema}
                field={field}
                values={values}
                curves={curves}
                marketCurves={marketCurves}
                currency={currency}
                assetClass={assetClass}
                onChange={onChange}
                visuallyHideLabel={compactSingleCurve}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
