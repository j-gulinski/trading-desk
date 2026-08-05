import { useState } from 'react'
import SidePanel from '../panel/SidePanel.jsx'
import { apiPost } from '../../services/apiClient.js'
import { endpoints } from '../../services/endpoints.js'
import { buildReassignIntent } from '../../domain/tradeActions.js'
import { describeApiError } from '../../domain/apiErrors.js'
import { formatNumber } from '../../domain/formatting.js'

export default function MoveTradesPanel({ book, targets, onAccepted, onClose }) {
  const [targetId, setTargetId] = useState(() => (targets.length === 1 ? targets[0].id : ''))
  const [error, setError] = useState(null)
  const [pending, setPending] = useState(false)

  async function handleSubmit(event) {
    event.preventDefault()
    if (!targetId) {
      setError('Pick a book to move the positions into.')
      return
    }

    setPending(true)
    setError(null)
    try {
      await apiPost(endpoints.tradeAction.submit, buildReassignIntent(book.id, targetId))
      const target = targets.find((candidate) => candidate.id === targetId)
      onAccepted(
        `Accepted — ${formatNumber(book.activeTrades)} open ${
          book.activeTrades === 1 ? 'position is' : 'positions are'
        } moving to ${target?.name ?? 'the selected book'}.`,
      )
      onClose()
    } catch (err) {
      setError(
        describeApiError(err, {
          service: 'Trade-action service',
          outcome: 'nothing was moved.',
        }),
      )
      setPending(false)
    }
  }

  return (
    <SidePanel
      eyebrow="BOOKS"
      title="Move open positions"
      subtitle={`out of ${book.name}`}
      onClose={onClose}
    >
      <p className="panel-form__message">
        {formatNumber(book.activeTrades)} open{' '}
        {book.activeTrades === 1 ? 'position has' : 'positions have'} to leave this book before
        it can be deleted. Closed trades stay here — they happened in this book.
      </p>

      {targets.length === 0 ? (
        <p className="panel-form__message">
          There is no other {book.assetClass} book to move them into. Create another active
          {` ${book.assetClass}`} book, then move the positions before deleting this one.
        </p>
      ) : (
        <form className="panel-form__form" onSubmit={handleSubmit} noValidate>
          <div className="panel-form__field">
            <label className="panel-form__label" htmlFor="move-trades-target">
              MOVE INTO · {book.assetClass}
            </label>
            <select
              id="move-trades-target"
              className="panel-form__select"
              value={targetId}
              onChange={(event) => {
                setTargetId(event.target.value)
                setError(null)
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
            <div className="panel-form__submit-error" role="alert">
              {error}
            </div>
          )}

          <button type="submit" className="panel-form__submit" disabled={pending}>
            {pending ? 'Moving…' : 'Move positions'}
          </button>
        </form>
      )}
    </SidePanel>
  )
}
