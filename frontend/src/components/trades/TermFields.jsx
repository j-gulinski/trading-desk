import NumberField from './NumberField.jsx'
import { curveChoicesFor } from '../../domain/tradeActions.js'
import {
  bondParCouponAt,
  curveBasisText,
  curveMarketAt,
  curveOptionLabel,
  curveSourceName,
  curveTitle,
  indexTenorText,
  irsParRateAt,
} from '../../domain/curves.js'
import {
  CURVE_ROLE_HINTS,
  TRADE_CURVE_ROLE_TEXT,
} from '../../config/marketData.js'
import { formatLongDate } from '../../domain/formatting.js'

const CURVE_FIELDS = ['discount_curve', 'projection_curve']

function choiceLabel(field, value) {
  return field.labels?.[value] ?? value
}

function CurveMarketContext({
  curve,
  maturityYears,
  paymentsPerYear,
  assetClass,
  onChange,
}) {
  const market = curveMarketAt(curve, maturityYears)
  if (market == null) return null
  const parCoupon = assetClass === 'BOND'
    ? bondParCouponAt(curve, maturityYears, Number(paymentsPerYear))
    : null

  return (
    <div className="panel-form__curve-market" role="note">
      <div className="panel-form__curve-market-head">
        <span>At contract maturity</span>
        <strong>{market.maturity}Y</strong>
      </div>
      <dl className="panel-form__curve-market-values">
        <div>
          <dt>Curve rate</dt>
          <dd>{market.rate.toFixed(4)}%</dd>
        </div>
        <div>
          <dt>Discount factor</dt>
          <dd>{market.discountFactor.toFixed(6)}</dd>
        </div>
      </dl>
      {parCoupon != null && (
        <div className="panel-form__curve-action">
          <span>
            Curve-implied par coupon
            <strong>{parCoupon.toFixed(4)}%</strong>
          </span>
          <button
            type="button"
            onClick={() => onChange('coupon_rate', parCoupon.toFixed(4))}
          >
            Use as coupon
          </button>
        </div>
      )}
      <details className="panel-form__curve-points">
        <summary>{market.method} · View {curve.points.length} curve points</summary>
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
  const waitingForUnderlying = assetClass === 'EUROPEAN_OPTION' && !currency
  const choices = waitingForUnderlying
    ? []
    : curveChoicesFor(
        curves,
        currency,
        field.name,
        indexTenor,
        assetClass,
      )
  const selected = choices.find((curve) => curve.curve_name === value)
  const marketCurve = selected ? marketCurves?.[value] : null
  return (
    <>
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
          : curves.length === 0
          ? 'No curves stored yet'
          : choices.length === 0
            ? `No ${currency ? `${currency} ` : ''}curve can take this role`
            : field.name === 'projection_curve'
              ? 'Choose projection curve…'
              : 'Choose discount curve…'}
      </option>
      {choices.map((curve) => (
        <option key={curve.curve_name} value={curve.curve_name}>
          {curveOptionLabel(curve)}
        </option>
      ))}
    </select>
    {selected && (
      <details className="panel-form__curve-provenance">
        <summary>
          <span>{selected.provider}</span>
          <span>as of {formatLongDate(selected.as_of_date)}</span>
        </summary>
        <dl className="panel-form__curve-facts">
          <div>
            <dt>In this trade</dt>
            <dd>{TRADE_CURVE_ROLE_TEXT[assetClass]?.[field.name] ?? field.label}</dd>
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
    {marketCurve && (
      <CurveMarketContext
        curve={marketCurve}
        maturityYears={maturityYears}
        paymentsPerYear={paymentsPerYear}
        assetClass={assetClass}
        onChange={onChange}
      />
    )}
    </>
  )
}

function ProjectionNotice({ curves, values }) {
  const chosen = curves.find((curve) => curve.curve_name === values.projection_curve)
  const legIndex = values.floating_rate_index_tenor
  if (chosen == null || legIndex == null || chosen.index_tenor === legIndex) return null
  return (
    <details className="panel-form__notice panel-form__notice--expandable">
      <summary>Projection is an approximation</summary>
      <p>
        {`${curveTitle(chosen)} does not follow the ${indexTenorText(legIndex)} `}
        {'index this leg pays, so the floating payments are approximate.'}
      </p>
    </details>
  )
}

function Field({ field, values, curves, marketCurves, currency, assetClass, onChange }) {
  const isCurve = CURVE_FIELDS.includes(field.name)
  const fairRate = assetClass === 'IRS' && field.name === 'fixed_rate'
    ? irsParRateAt(
        marketCurves?.[values.discount_curve],
        marketCurves?.[values.projection_curve],
        values.maturity_years,
        values.floating_rate_index_tenor,
      )
    : null
  return (
    <div className={`panel-form__field${isCurve ? ' panel-form__field--wide' : ''}`}>
      <label
        className={`panel-form__label${
          CURVE_ROLE_HINTS[field.name] ? ' panel-form__label--hinted' : ''
        }`}
        htmlFor={`term-${field.name}`}
        title={CURVE_ROLE_HINTS[field.name]}
      >
        {field.label}
      </label>
      {field.type === 'choice' && field.choices_source === 'CURVES' ? (
        <CurveSelect
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
      {field.name === 'projection_curve' && (
        <ProjectionNotice curves={curves} values={values} />
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
  const contract = schema.fields.filter((field) => !CURVE_FIELDS.includes(field.name))
  const curveFields = schema.fields.filter((field) => CURVE_FIELDS.includes(field.name))

  return (
    <div className="panel-form__model-layout">
      <div className="panel-form__group panel-form__group--contract">
        <h3 className="panel-form__group-title">Model contract</h3>
        <div className="panel-form__terms">
          {contract.map((field) => (
            <Field
              key={field.name}
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
      <div className="panel-form__group panel-form__group--curves">
        <h3 className="panel-form__group-title">Curves</h3>
        <div
          className={`panel-form__terms${
            curveFields.length > 1 ? ' panel-form__terms--paired-curves' : ''
          }`}
        >
          {curveFields.map((field) => (
            <Field
              key={field.name}
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
    </div>
  )
}
