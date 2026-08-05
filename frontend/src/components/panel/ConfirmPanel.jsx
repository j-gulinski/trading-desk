import { useState } from 'react'
import SidePanel from './SidePanel.jsx'

export default function ConfirmPanel({
  eyebrow,
  title,
  subtitle,
  message,
  confirmLabel,
  onConfirm,
  describeError,
  onClose,
}) {
  const [pending, setPending] = useState(false)
  const [error, setError] = useState(null)

  async function handleConfirm() {
    setPending(true)
    setError(null)
    try {
      await onConfirm()
      onClose()
    } catch (err) {
      setError(describeError(err))
      setPending(false)
    }
  }

  return (
    <SidePanel eyebrow={eyebrow} title={title} subtitle={subtitle} onClose={onClose}>
      <p className="panel-form__message">{message}</p>

      {error && (
        <div className="panel-form__submit-error" role="alert">
          {error}
        </div>
      )}

      <div className="panel-form__actions">
        <button type="button" className="panel-form__cancel" onClick={onClose}>
          Cancel
        </button>
        <button
          type="button"
          className="panel-form__submit panel-form__submit--danger"
          disabled={pending}
          onClick={handleConfirm}
        >
          {pending ? 'Working…' : confirmLabel}
        </button>
      </div>
    </SidePanel>
  )
}
