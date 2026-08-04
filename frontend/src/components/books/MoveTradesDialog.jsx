import { useState } from 'react'
import { apiPost } from '../../services/apiClient.js'
import { endpoints } from '../../services/endpoints.js'
import { buildReassignIntent } from '../../domain/tradeActions.js'
import { describeApiError } from '../../domain/apiErrors.js'
import { formatNumber } from '../../domain/formatting.js'
import { useAsyncAction } from '../../hooks/useAsyncAction.js'
import { useModalDialog } from '../../hooks/useModalDialog.js'

export default function MoveTradesDialog({ book, targets, onAccepted, onClose }) {
  const { dialogRef, close, closeOnBackdrop } = useModalDialog()
  const [targetId, setTargetId] = useState(() => (targets.length === 1 ? targets[0].id : ''))
  const { pending, error, run, clearError, setError } = useAsyncAction()

  async function handleSubmit(event) {
    event.preventDefault()
    if (!targetId) {
      setError('Pick a book to move the positions into.')
      return
    }

    const succeeded = await run(
      () => apiPost(endpoints.tradeAction.submit, buildReassignIntent(book.id, targetId)),
      (err) => describeApiError(err, {
        service: 'Trade-action service',
        outcome: 'nothing was moved.',
      }),
    )
    if (succeeded) {
      const target = targets.find((candidate) => candidate.id === targetId)
      onAccepted(
        `Accepted — ${formatNumber(book.activeTrades)} open ${
          book.activeTrades === 1 ? 'position is' : 'positions are'
        } moving to ${target?.name ?? 'the selected book'}.`,
      )
      close()
    }
  }

  return (
    <dialog
      ref={dialogRef}
      className="form-dialog"
      aria-labelledby="move-trades-title"
      onClose={onClose}
      onClick={closeOnBackdrop}
    >
      <article className="form-dialog__surface">
        <header className="form-dialog__head">
          <div>
            <span className="form-dialog__eyebrow">BOOKS</span>
            <h2 id="move-trades-title">Move open positions</h2>
            <p>out of {book.name}</p>
          </div>
          <button
            type="button"
            className="form-dialog__close"
            aria-label="Close move form"
            onClick={close}
          >
            ×
          </button>
        </header>

        <div className="form-dialog__body">
          <p className="form-dialog__message">
            All {formatNumber(book.activeTrades)} open{' '}
            {book.activeTrades === 1 ? 'position moves' : 'positions move'} to the book you pick.
            Closed trades stay here — they happened in this book.
          </p>

          {targets.length === 0 ? (
            <p className="form-dialog__message">
              There is no other active {book.assetClass} book to move them into. Create one first.
            </p>
          ) : (
            <form className="form-dialog__form" onSubmit={handleSubmit} noValidate>
              <div className="form-dialog__field">
                <label className="form-dialog__label" htmlFor="move-trades-target">
                  MOVE INTO · {book.assetClass}
                </label>
                <select
                  id="move-trades-target"
                  className="form-dialog__select"
                  value={targetId}
                  autoFocus
                  onChange={(event) => {
                    setTargetId(event.target.value)
                    clearError()
                  }}
                >
                  <option value="">Select a book…</option>
                  {targets.map((target) => (
                    <option key={target.id} value={target.id}>
                      {target.name}
                    </option>
                  ))}
                </select>
              </div>

              {error && (
                <div className="form-dialog__submit-error" role="alert">
                  {error}
                </div>
              )}

              <button type="submit" className="form-dialog__submit" disabled={pending}>
                {pending ? 'Moving…' : 'Move positions'}
              </button>
            </form>
          )}
        </div>
      </article>
    </dialog>
  )
}
