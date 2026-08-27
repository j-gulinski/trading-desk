import { useEffect, useState } from 'react'
import EmptyState from '../EmptyState.jsx'
import LoadingSkeleton from '../LoadingSkeleton.jsx'
import SidePanel from '../panel/SidePanel.jsx'
import { apiGet, apiPost, apiPut } from '../../services/apiClient.js'
import { endpoints } from '../../services/endpoints.js'
import {
  BOOK_ASSET_CLASSES,
  BOOK_DESCRIPTION_MAX_LENGTH,
  BOOK_NAME_MAX_LENGTH,
} from '../../config/books.js'
import { bookFormErrorsOf, bookFormValuesOf, bookPayloadOf } from '../../domain/books.js'
import { describeApiError } from '../../domain/apiErrors.js'
import { assetClassLabel } from '../../config/tradeActions.js'

function FieldError({ id, message }) {
  if (!message) return null
  return (
    <span id={id} className="panel-form__error" role="alert">
      {message}
    </span>
  )
}

export default function BookFormPanel({ bookId = null, onSaved, onClose }) {
  const editing = bookId != null

  const [values, setValues] = useState(() => (editing ? null : bookFormValuesOf(null)))
  const [loadError, setLoadError] = useState(null)
  const [errors, setErrors] = useState({})
  const [pending, setPending] = useState(false)
  const [submitError, setSubmitError] = useState(null)

  useEffect(() => {
    if (!editing) return undefined
    let cancelled = false
    const controller = new AbortController()
    apiGet(endpoints.books.book(bookId), { signal: controller.signal })
      .then((book) => {
        if (cancelled) return
        if (book == null) setLoadError('This book no longer exists.')
        else setValues(bookFormValuesOf(book))
      })
      .catch((err) => {
        if (cancelled) return
        setLoadError(
          describeApiError(err, {
            service: 'Books service',
            outcome: 'this book could not be loaded.',
          }),
        )
      })
    return () => {
      cancelled = true
      controller.abort()
    }
  }, [bookId, editing])

  function setField(field, value) {
    setValues((current) => ({ ...current, [field]: value }))
    setErrors((current) => {
      if (!current[field]) return current
      const next = { ...current }
      delete next[field]
      return next
    })
  }

  async function handleSubmit(event) {
    event.preventDefault()
    const nextErrors = bookFormErrorsOf(values)
    setErrors(nextErrors)
    if (Object.keys(nextErrors).length > 0) return

    setPending(true)
    setSubmitError(null)
    try {
      const payload = bookPayloadOf(values)
      if (editing) await apiPut(endpoints.books.book(bookId), payload)
      else await apiPost(endpoints.books.list, payload)
      onSaved()
      onClose()
    } catch (err) {
      setSubmitError(
        err?.status === 500
          ? 'Could not save — the name may already be taken.'
          : describeApiError(err, {
              service: 'Books service',
              outcome: 'the book was not saved.',
            }),
      )
      setPending(false)
    }
  }

  const ready = values != null && loadError == null

  return (
    <SidePanel
      eyebrow="BOOKS"
      title={editing ? 'Edit book' : 'Create book'}
      subtitle={editing ? 'name, asset class & description' : 'a new empty trading book'}
      onClose={onClose}
    >
      {editing && values == null && loadError == null && (
        <LoadingSkeleton variant="panel" rows={4} label="Loading book" />
      )}
      {loadError != null && <EmptyState message={loadError} />}

      {ready && (
        <form className="panel-form__form" onSubmit={handleSubmit} noValidate>
          <div className="panel-form__field">
            <label className="panel-form__label" htmlFor="book-form-name">
              NAME
            </label>
            <input
              id="book-form-name"
              className="panel-form__input"
              type="text"
              value={values.name}
              maxLength={BOOK_NAME_MAX_LENGTH}
              aria-invalid={errors.name != null}
              aria-describedby={errors.name ? 'book-form-name-error' : undefined}
              onChange={(event) => setField('name', event.target.value)}
            />
            <FieldError id="book-form-name-error" message={errors.name} />
          </div>

          <div className="panel-form__field">
            <label className="panel-form__label" htmlFor="book-form-class">
              ASSET CLASS
            </label>
            <select
              id="book-form-class"
              className="panel-form__select"
              value={values.assetClass}
              aria-invalid={errors.assetClass != null}
              aria-describedby={errors.assetClass ? 'book-form-class-error' : undefined}
              onChange={(event) => setField('assetClass', event.target.value)}
            >
              <option value="">Select asset class…</option>
              {BOOK_ASSET_CLASSES.map((assetClass) => (
                <option key={assetClass} value={assetClass}>
                  {assetClassLabel(assetClass)}
                </option>
              ))}
            </select>
            <FieldError id="book-form-class-error" message={errors.assetClass} />
          </div>

          <div className="panel-form__field">
            <label className="panel-form__label" htmlFor="book-form-description">
              DESCRIPTION · OPTIONAL
            </label>
            <textarea
              id="book-form-description"
              className="panel-form__textarea"
              rows={3}
              value={values.description}
              maxLength={BOOK_DESCRIPTION_MAX_LENGTH}
              aria-invalid={errors.description != null}
              aria-describedby={errors.description ? 'book-form-description-error' : undefined}
              onChange={(event) => setField('description', event.target.value)}
            />
            <FieldError id="book-form-description-error" message={errors.description} />
          </div>

          {submitError && (
            <div className="panel-form__submit-error" role="alert">
              {submitError}
            </div>
          )}

          <div className="panel-form__actions">
            <button type="button" className="panel-form__cancel" onClick={onClose}>
              Cancel
            </button>
            <button type="submit" className="panel-form__submit" disabled={pending}>
              {pending ? 'Saving…' : editing ? 'Save changes' : 'Create book'}
            </button>
          </div>
        </form>
      )}
    </SidePanel>
  )
}
