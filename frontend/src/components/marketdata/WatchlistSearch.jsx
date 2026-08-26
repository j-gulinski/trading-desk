import { useEffect, useRef, useState } from 'react'
import { apiGet } from '../../services/apiClient.js'
import { endpoints } from '../../services/endpoints.js'
import {
  SYMBOL_SEARCH_DEBOUNCE_MS,
  SYMBOL_SEARCH_MIN_CHARS,
  SYMBOL_SEARCH_SHOWN_LIMIT,
} from '../../config/marketData.js'
import { providerLabel } from '../../config/providers.js'

function mergeBySymbol(results) {
  const bySymbol = new Map()
  for (const result of results) {
    const market = ['US', 'USA', 'UNITED STATES'].includes(result.exchange?.toUpperCase())
      ? null
      : result.exchange
    const existing = bySymbol.get(result.symbol)
    if (!existing) {
      bySymbol.set(result.symbol, {
        ...result,
        market,
        providers: [result.provider],
      })
      continue
    }
    if (!existing.providers.includes(result.provider)) {
      existing.providers.push(result.provider)
    }
    if (!existing.market && market) {
      existing.market = market
      existing.exchange = result.exchange
      existing.name = result.name
      existing.provider_symbol = result.provider_symbol
    }
  }
  return [...bySymbol.values()].slice(0, SYMBOL_SEARCH_SHOWN_LIMIT)
}

function ResultRow({ result, onBoard, busy, onAdd }) {
  const addable = result.providers.filter((provider) => !onBoard.has(provider))
  const [skipped, setSkipped] = useState(() => new Set())

  function toggle(provider) {
    setSkipped((current) => {
      const next = new Set(current)
      if (next.has(provider)) next.delete(provider)
      else next.add(provider)
      return next
    })
  }

  const chosen = addable.filter((provider) => !skipped.has(provider))
  const label = busy
    ? 'Adding…'
    : addable.length === 0
      ? 'On board'
      : `Add (${chosen.length})`

  return (
    <li className="watchlist-search__result">
      <span className="watchlist-search__symbol">{result.provider_symbol}</span>
      <span className="watchlist-search__name" title={result.name}>
        {result.name}
      </span>
      <span className="watchlist-search__meta">
        {result.asset_class}
        {result.exchange ? ` · ${result.exchange}` : ''}
        {' · '}quoted in {result.currency}
      </span>
      <span className="watchlist-search__providers">
        {result.providers.map((provider) => {
          const already = onBoard.has(provider)
          return (
            <button
              key={provider}
              type="button"
              className="watchlist-search__provider"
              aria-pressed={already || !skipped.has(provider)}
              disabled={already}
              title={
                already
                  ? `${providerLabel(provider)} already feeds ${result.symbol}`
                  : `Poll ${result.symbol} on ${providerLabel(provider)}`
              }
              onClick={() => toggle(provider)}
            >
              {providerLabel(provider)}
            </button>
          )
        })}
      </span>
      <button
        type="button"
        className="watchlist-search__add"
        disabled={busy || chosen.length === 0}
        onClick={() => onAdd(result, chosen)}
      >
        {label}
      </button>
    </li>
  )
}

export default function WatchlistSearch({
  watchedProviders,
  onAdd,
  busyKey,
  addError,
  onDismissAddError,
}) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState(null)
  const [searching, setSearching] = useState(false)
  const [searchError, setSearchError] = useState(false)
  const [open, setOpen] = useState(false)
  const containerRef = useRef(null)

  useEffect(() => {
    const trimmed = query.trim()
    if (trimmed.length < SYMBOL_SEARCH_MIN_CHARS) {
      setResults(null)
      setSearching(false)
      setSearchError(false)
      setOpen(false)
      return undefined
    }
    const controller = new AbortController()
    setSearching(true)
    const timer = setTimeout(() => {
      apiGet(endpoints.marketData.symbolSearch(trimmed), {
        signal: controller.signal,
      }).then(
        (payload) => {
          setResults(mergeBySymbol(payload?.results ?? []))
          setSearching(false)
          setSearchError(false)
          setOpen(true)
        },
        () => {
          if (controller.signal.aborted) return
          setResults([])
          setSearching(false)
          setSearchError(true)
          setOpen(true)
        },
      )
    }, SYMBOL_SEARCH_DEBOUNCE_MS)
    return () => {
      controller.abort()
      clearTimeout(timer)
    }
  }, [query])

  useEffect(() => {
    if (!open) return undefined
    function handlePointerDown(event) {
      if (!containerRef.current?.contains(event.target)) setOpen(false)
    }
    function handleKeyDown(event) {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', handlePointerDown)
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('mousedown', handlePointerDown)
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [open])

  async function handleAdd(result, providers) {
    onDismissAddError()
    const added = await onAdd(result, providers)
    if (added) {
      setQuery('')
      setOpen(false)
    }
  }

  return (
    <div className="watchlist-search" ref={containerRef}>
      <div className="watchlist-search__controls">
        <label className="watchlist-search__label" htmlFor="watchlist-search-input">
          ADD SYMBOL
        </label>
        <input
          id="watchlist-search-input"
          className="watchlist-search__input"
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onFocus={() => results != null && setOpen(true)}
          placeholder="Search provider catalogs…"
          autoComplete="off"
        />
        <span className="watchlist-search__hint" aria-live="polite">
          {searching && 'searching…'}
        </span>
      </div>
      {addError && (
        <p className="watchlist-search__error" role="alert">
          {addError}
          <button type="button" onClick={onDismissAddError}>
            dismiss
          </button>
        </p>
      )}
      {open && results != null && (
        <ul
          id="watchlist-search-results"
          className="watchlist-search__results"
          aria-label="Symbol search results"
        >
          {searchError && (
            <li className="watchlist-search__empty">Search unavailable — try again.</li>
          )}
          {!searchError && results.length === 0 && !searching && (
            <li className="watchlist-search__empty">No symbols match this search.</li>
          )}
          {!searchError &&
            results.map((result) => (
              <ResultRow
                key={result.symbol}
                result={result}
                onBoard={watchedProviders.get(result.symbol) ?? new Set()}
                busy={busyKey === result.symbol}
                onAdd={handleAdd}
              />
            ))}
        </ul>
      )}
    </div>
  )
}
