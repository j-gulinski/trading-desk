import { curveChoicesFor } from '../../domain/tradeActions.js'
import { curveOptionLabel } from '../../domain/curves.js'

function choiceLabel(field, value) {
  return field.labels?.[value] ?? value
}

function CurveSelect({ field, value, curves, currency, onChange }) {
  const choices = curveChoicesFor(curves, currency)
  return (
    <select
      id={`term-${field.name}`}
      className="panel-form__select"
      value={value ?? ''}
      disabled={choices.length === 0}
      onChange={(event) => onChange(field.name, event.target.value)}
    >
      <option value="">
        {curves.length === 0
          ? 'No curve sets stored yet'
          : choices.length === 0
            ? `No ${currency ?? ''} curve available`.replace('  ', ' ')
            : 'Select curve…'}
      </option>
      {choices.map((curve) => (
        <option key={curve.curve_name} value={curve.curve_name}>
          {curveOptionLabel(curve)}
        </option>
      ))}
    </select>
  )
}

export default function TermFields({ schema, values, curves, currency, onChange }) {
  return (
    <div className="panel-form__terms">
      {schema.fields.map((field) => (
        <div className="panel-form__field" key={field.name}>
          <label className="panel-form__label" htmlFor={`term-${field.name}`}>
            {field.label}
          </label>
          {field.type === 'choice' && field.choices_source === 'CURVES' ? (
            <CurveSelect
              field={field}
              value={values[field.name]}
              curves={curves}
              currency={currency}
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
            <input
              id={`term-${field.name}`}
              className="panel-form__input"
              type="number"
              inputMode="decimal"
              step={field.type === 'integer' ? 1 : 'any'}
              value={values[field.name] ?? ''}
              onChange={(event) => onChange(field.name, event.target.value)}
            />
          )}
        </div>
      ))}
    </div>
  )
}
