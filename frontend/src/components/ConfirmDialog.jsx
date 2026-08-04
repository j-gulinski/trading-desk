import { useEffect, useRef, useState } from 'react'

export default function ConfirmDialog({
  eyebrow,
  title,
  subtitle,
  message,
  confirmLabel,
  onConfirm,
  describeError,
  onClose,
}) {
  const dialogRef = useRef(null)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    const dialog = dialogRef.current
    if (dialog && !dialog.open) dialog.showModal()
  }, [])

  async function handleConfirm() {
    setPending(true)
    setError(null)
    try {
      await onConfirm()
      dialogRef.current?.close()
    } catch (err) {
      setError(describeError(err))
    } finally {
      setPending(false)
    }
  }

  return (
    <dialog
      ref={dialogRef}
      className="form-dialog"
      aria-labelledby="confirm-dialog-title"
      onClose={onClose}
      onClick={(event) => {
        if (event.target === event.currentTarget) event.currentTarget.close()
      }}
    >
      <article className="form-dialog__surface">
        <header className="form-dialog__head">
          <div>
            <span className="form-dialog__eyebrow">{eyebrow}</span>
            <h2 id="confirm-dialog-title">{title}</h2>
            {subtitle && <p>{subtitle}</p>}
          </div>
          <button
            type="button"
            className="form-dialog__close"
            aria-label="Close"
            onClick={() => dialogRef.current?.close()}
          >
            ×
          </button>
        </header>

        <div className="form-dialog__body">
          <p className="form-dialog__message">{message}</p>

          {error && (
            <div className="form-dialog__submit-error" role="alert">
              {error}
            </div>
          )}

          <div className="form-dialog__actions">
            <button
              type="button"
              className="form-dialog__cancel"
              onClick={() => dialogRef.current?.close()}
            >
              Cancel
            </button>
            <button
              type="button"
              className="form-dialog__submit form-dialog__submit--danger"
              disabled={pending}
              autoFocus
              onClick={handleConfirm}
            >
              {pending ? 'Working…' : confirmLabel}
            </button>
          </div>
        </div>
      </article>
    </dialog>
  )
}
