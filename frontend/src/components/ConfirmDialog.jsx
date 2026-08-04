import { useAsyncAction } from '../hooks/useAsyncAction.js'
import { useModalDialog } from '../hooks/useModalDialog.js'

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
  const { dialogRef, close, closeOnBackdrop } = useModalDialog()
  const { pending, error, run } = useAsyncAction()

  async function handleConfirm() {
    const succeeded = await run(onConfirm, describeError)
    if (succeeded) {
      close()
    }
  }

  return (
    <dialog
      ref={dialogRef}
      className="form-dialog"
      aria-labelledby="confirm-dialog-title"
      onClose={onClose}
      onClick={closeOnBackdrop}
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
            onClick={close}
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
              onClick={close}
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
