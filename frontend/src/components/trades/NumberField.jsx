import { useState } from 'react'
import { groupDigits } from '../../domain/formatting.js'

function grouped(value) {
  const text = String(value ?? '')
  if (text === '') return ''
  const [whole, fraction] = text.split('.')
  const number = Number(whole)
  if (!Number.isFinite(number)) return text
  const separated = groupDigits(new Intl.NumberFormat('en-US').format(number))
  return fraction === undefined ? separated : `${separated}.${fraction}`
}

export default function NumberField({ id, value, onChange, ...rest }) {
  const [editing, setEditing] = useState(false)
  const text = String(value ?? '')

  return (
    <input
      id={id}
      className="panel-form__input"
      type="text"
      inputMode="decimal"
      value={editing ? text : grouped(text)}
      onFocus={() => setEditing(true)}
      onBlur={() => setEditing(false)}
      onChange={(event) => {
        const next = event.target.value.replace(/[\s ,]/g, '')
        if (next === '' || /^\d*\.?\d*$/.test(next)) onChange(next)
      }}
      {...rest}
    />
  )
}
