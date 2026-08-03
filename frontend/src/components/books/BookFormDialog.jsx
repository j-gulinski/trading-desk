import { useEffect, useRef, useState } from 'react'
import EmptyState from '../EmptyState.jsx'
import { apiGet, apiPost, apiPut } from '../../services/apiClient.js'
import { endpoints } from '../../services/endpoints.js'
import {
  BOOK_ASSET_CLASSES,
  BOOK_DESCRIPTION_MAX_LENGTH,
  BOOK_NAME_MAX_LENGTH,
} from '../../config/books.js'
import { bookFormErrorsOf, bookFormValuesOf, bookPayloadOf } from '../../domain/books.js'
import { describeApiError } from '../../domain/apiErrors.js'

function FieldError({ id, message }) {
  if (!message) return null
  return (
    <span id={id} className="form-dialog__error" role="alert">
      {message}
    </span>
  )
}

export default function BookFormDialog({ bookId = null, onSaved, onClose }) {
  const dialogRef = useRef(null)
  const editing = bookId != null

  const [values, setValues] = useState(() => (editing ? null : bookFormValuesOf(null)))
  const [loadError, setLoadError] = useState(null)
  const [errors, setErrors] = useState({})
  const [pending, setPending] = useState(false)
  const [submitError, setSubmitError] = useState(null)

  useEffect(() => {
    const dialog = dialogRef.current
    if (dialog && !dialog.open) dialog.showModal()
  }, [])

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
      dialogRef.current?.close()
    } catch (err) {
      setSubmitError(
        err?.status === 500
          ? 'Could not save — the name may already be taken.'
          : describeApiError(err, {
              service: 'Books service',
              outcome: 'the book was not saved.',
            }),
      )
    } finally {
      setPending(false)
    }
  }

  const title = editing ? 'Edit book' : 'Create book'
  const ready = values != null && loadError == null

  return (
    <dialog
      ref={dialogRef}
      className="form-dialog"
      aria-labelledby="book-form-title"
      onClose={onClose}
      onClick={(event) => {
        if (event.target === event.currentTarget) event.currentTarget.close()
      }}
    >
      <article className="form-dialog__surface">
        <header className="form-dialog__head">
          <div>
            <span className="form-dialog__eyebrow">BOOKS</span>
            <h2 id="book-form-title">{title}</h2>
            <p>{editing ? 'name, asset class & description' : 'a new empty trading book'}</p>
          </div>
          <button
            type="button"
            className="form-dialog__close"
            aria-label="Close book form"
            autoFocus
            onClick={() => dialogRef.current?.close()}
          >
            ×
          </button>
        </header>

        <div className="form-dialog__body">
          {editing && values == null && loadError == null && (
            <EmptyState message="Loading book…" />
          )}
          {loadError != null && <EmptyState message={loadError} />}

          {ready && (
            <form className="form-dialog__form" onSubmit={handleSubmit} noValidate>
              <div className="form-dialog__field">
                <label className="form-dialog__label" htmlFor="book-form-name">
                  NAME
                </label>
                <input
                  id="book-form-name"
                  className="form-dialog__input"
                  type="text"
                  value={values.name}
                  maxLength={BOOK_NAME_MAX_LENGTH}
                  aria-invalid={errors.name != null}
                  aria-describedby={errors.name ? 'book-form-name-error' : undefined}
                  onChange={(event) => setField('name', event.target.value)}
                />
                <FieldError id="book-form-name-error" message={errors.name} />
              </div>

              <div className="form-dialog__field">
                <label className="form-dialog__label" htmlFor="book-form-class">
                  ASSET CLASS
                </label>
                <select
                  id="book-form-class"
                  className="form-dialog__select"
                  value={values.assetClass}
                  aria-invalid={errors.assetClass != null}
                  aria-describedby={errors.assetClass ? 'book-form-class-error' : undefined}
                  onChange={(event) => setField('assetClass', event.target.value)}
                >
                  <option value="">Select asset class…</option>
                  {BOOK_ASSET_CLASSES.map((assetClass) => (
                    <option key={assetClass} value={assetClass}>
                      {assetClass}
                    </option>
                  ))}
                </select>
                <FieldError id="book-form-class-error" message={errors.assetClass} />
              </div>

              <div className="form-dialog__field">
                <label className="form-dialog__label" htmlFor="book-form-description">
                  DESCRIPTION · OPTIONAL
                </label>
                <textarea
                  id="book-form-description"
                  className="form-dialog__textarea"
                  rows={3}
                  value={values.description}
                  maxLength={BOOK_DESCRIPTION_MAX_LENGTH}
                  aria-invalid={errors.description != null}
                  aria-describedby={
                    errors.description ? 'book-form-description-error' : undefined
                  }
                  onChange={(event) => setField('description', event.target.value)}
                />
                <FieldError id="book-form-description-error" message={errors.description} />
              </div>

              {submitError && (
                <div className="form-dialog__submit-error" role="alert">
                  {submitError}
                </div>
              )}

              <button type="submit" className="form-dialog__submit" disabled={pending}>
                {pending ? 'Saving…' : editing ? 'Save changes' : 'Create book'}
              </button>
            </form>
          )}
        </div>
      </article>
    </dialog>
  )
}
