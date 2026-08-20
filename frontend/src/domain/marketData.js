import { HISTORY_POINT_CAP } from '../config/marketData.js'
import { directionOf } from './formatting.js'
import { sortRows } from './tableSort.js'

const MARKET_STATE_STORAGE_VERSION = 8
const MAX_STORED_INSTRUMENTS = 100

function toNum(value) {
  if (value == null || value === '') return null
  const n = Number(value)
  return Number.isFinite(n) ? n : null
}

function eventIdOf(tick) {
  if (tick?.event_id == null) return null
  const eventId = Number(tick.event_id)
  return Number.isSafeInteger(eventId) && eventId >= 0 ? eventId : null
}

function eventTimeOf(tick) {
  const eventTime = Date.parse(tick?.event_time ?? '')
  return Number.isFinite(eventTime) ? eventTime : null
}

export function instrumentId(provider, symbol) {
  return `${provider}:${symbol}`
}

function spotInstrument(tick, snapshotStreamId = null) {
  if (!tick || typeof tick.symbol !== 'string' || tick.symbol.length === 0) return null
  const provider = typeof tick.provider === 'string' ? tick.provider : null
  const providerTimestampMs = Date.parse(tick.provider_timestamp ?? '')
  const polledAtMs = Date.parse(tick.received_at ?? '')
  const staleAfterSeconds = toNum(tick.stale_after_seconds)
  const closedStaleAfterSeconds = toNum(tick.closed_stale_after_seconds)
  return {
    id: provider ? instrumentId(provider, tick.symbol) : tick.symbol,
    symbol: tick.symbol,
    provider,
    assetClass: tick.asset_class ?? 'UNKNOWN',
    currency: tick.currency ?? null,
    value: toNum(tick.mid ?? tick.last),
    bid: toNum(tick.bid),
    ask: toNum(tick.ask),
    last: toNum(tick.last),
    previousClose: toNum(tick.previous_close),
    grade: tick.quote_grade ?? null,
    providerTimestampMs: Number.isFinite(providerTimestampMs) ? providerTimestampMs : null,
    polledAtMs: Number.isFinite(polledAtMs) ? polledAtMs : null,
    staleAfterMs: staleAfterSeconds != null ? staleAfterSeconds * 1000 : null,
    closedStaleAfterMs:
      closedStaleAfterSeconds != null ? closedStaleAfterSeconds * 1000 : null,
    marketOpen: typeof tick.market_open === 'boolean' ? tick.market_open : null,
    watched: tick.watched === true,
    held: tick.held === true,
    benchmark: tick.benchmark === true,
    sourceStreamId: tick.stream_id ?? snapshotStreamId,
    sourceEventId: eventIdOf(tick),
    eventTimeMs: eventTimeOf(tick),
  }
}

export function instrumentsFromEvent(name, data) {
  if (name !== 'market_tick') return []
  return [spotInstrument(data)].filter(Boolean)
}

function instrumentsFromSnapshot(snapshot) {
  const streamId = snapshot?.stream_id ?? null
  return Object.values(snapshot?.spots ?? {})
    .map((spot) => spotInstrument(spot, streamId))
    .filter(Boolean)
}

function appendPoint(history, atMs, value) {
  if (!Number.isFinite(value) || !Number.isFinite(atMs)) return history
  const last = history[history.length - 1]
  if (last && last[0] === atMs && last[1] === value) return history
  return [...history, [atMs, value]].slice(-HISTORY_POINT_CAP)
}

function mergeInstrument(prev, update) {
  let sourceRestarted = false

  if (prev) {
    const previousStream = prev.sourceStreamId
    const nextStream = update.sourceStreamId
    const streamsKnown = previousStream != null && nextStream != null
    const streamChanged = streamsKnown && previousStream !== nextStream
    const previousTime = prev.eventTimeMs
    const nextTime = update.eventTimeMs
    const timesKnown = Number.isFinite(previousTime) && Number.isFinite(nextTime)

    if (streamChanged) {
      if (timesKnown && nextTime < previousTime) return prev
      sourceRestarted = true
    } else if (prev.sourceEventId != null && update.sourceEventId != null) {
      if (update.sourceEventId === prev.sourceEventId) return prev
      if (update.sourceEventId < prev.sourceEventId) {
        if (!streamsKnown && timesKnown && nextTime > previousTime) {
          sourceRestarted = true
        } else {
          return prev
        }
      }
    } else if (timesKnown && nextTime <= previousTime) {
      return prev
    }
  }

  const previous = sourceRestarted ? { history: prev.history } : prev
  const history = appendPoint(
    previous?.history ?? [],
    update.eventTimeMs ?? update.receivedAtMs,
    update.value,
  )
  const previousValue =
    previous && Number.isFinite(update.value) && Number.isFinite(previous.value)
      ? previous.value
      : null

  return {
    ...update,
    history,
    previousValue,
    lastDirection: directionOf(
      Number.isFinite(previousValue) ? update.value - previousValue : null,
    ),
  }
}

export function mergeInstruments(previous, updates) {
  let instruments = previous
  let accepted = false

  for (const update of updates) {
    const current = instruments[update.id]
    const merged = mergeInstrument(current, update)
    if (merged === current) continue
    if (instruments === previous) instruments = { ...instruments }
    instruments[update.id] = merged
    accepted = true
  }

  return accepted ? instruments : previous
}

export function dropInstruments(previous, ids) {
  const dropped = new Set(ids)
  const kept = Object.entries(previous).filter(([id]) => !dropped.has(id))
  if (kept.length === Object.keys(previous).length) return previous
  return Object.fromEntries(kept)
}

export function reconcileSnapshotInstruments(previous, snapshot, seedStartedMs = null) {
  const receivedAtMs = Date.now()
  const updates = instrumentsFromSnapshot(snapshot).map((instrument) => ({
    ...instrument,
    receivedAtMs,
  }))
  const snapshotStreamId = snapshot?.stream_id ?? null
  if (snapshotStreamId == null) return mergeInstruments(previous, updates)

  const snapshotIds = new Set(updates.map((instrument) => instrument.id))
  const retained = Object.fromEntries(
    Object.entries(previous).filter(
      ([id, instrument]) =>
        snapshotIds.has(id) ||
        (instrument.sourceStreamId === snapshotStreamId &&
          seedStartedMs != null &&
          instrument.receivedAtMs != null &&
          instrument.receivedAtMs >= seedStartedMs),
    ),
  )
  return mergeInstruments(retained, updates)
}

export function instrumentsForStorage(instruments) {
  return {
    version: MARKET_STATE_STORAGE_VERSION,
    instruments: Object.values(instruments ?? {}).slice(0, MAX_STORED_INSTRUMENTS),
  }
}

function restoreInstrument(candidate) {
  if (
    !candidate ||
    typeof candidate.id !== 'string' ||
    candidate.id.length === 0 ||
    typeof candidate.symbol !== 'string' ||
    candidate.symbol.length === 0 ||
    typeof candidate.assetClass !== 'string' ||
    candidate.assetClass.length === 0
  ) {
    return null
  }

  return {
    id: candidate.id,
    symbol: candidate.symbol,
    provider: typeof candidate.provider === 'string' ? candidate.provider : null,
    assetClass: candidate.assetClass,
    currency: typeof candidate.currency === 'string' ? candidate.currency : null,
    value: toNum(candidate.value),
    bid: toNum(candidate.bid),
    ask: toNum(candidate.ask),
    last: toNum(candidate.last),
    previousClose: toNum(candidate.previousClose),
    grade: typeof candidate.grade === 'string' ? candidate.grade : null,
    providerTimestampMs: Number.isFinite(candidate.providerTimestampMs)
      ? candidate.providerTimestampMs
      : null,
    polledAtMs: Number.isFinite(candidate.polledAtMs) ? candidate.polledAtMs : null,
    staleAfterMs: Number.isFinite(candidate.staleAfterMs) ? candidate.staleAfterMs : null,
    closedStaleAfterMs: Number.isFinite(candidate.closedStaleAfterMs)
      ? candidate.closedStaleAfterMs
      : null,
    marketOpen: typeof candidate.marketOpen === 'boolean' ? candidate.marketOpen : null,
    watched: candidate.watched === true,
    held: candidate.held === true,
    benchmark: candidate.benchmark === true,
    sourceStreamId:
      typeof candidate.sourceStreamId === 'string' ? candidate.sourceStreamId : null,
    sourceEventId: eventIdOf({ event_id: candidate.sourceEventId }),
    eventTimeMs: Number.isFinite(candidate.eventTimeMs) ? candidate.eventTimeMs : null,
    receivedAtMs: Number.isFinite(candidate.receivedAtMs) ? candidate.receivedAtMs : null,
    previousValue: toNum(candidate.previousValue),
    history: [],
    lastDirection: ['pos', 'neg', 'flat'].includes(candidate.lastDirection)
      ? candidate.lastDirection
      : 'flat',
  }
}

export function restoreInstruments(payload) {
  if (
    payload?.version !== MARKET_STATE_STORAGE_VERSION ||
    !Array.isArray(payload.instruments)
  ) {
    return {}
  }

  const restored = payload.instruments
    .slice(0, MAX_STORED_INSTRUMENTS)
    .map(restoreInstrument)
    .filter(Boolean)
  return Object.fromEntries(restored.map((instrument) => [instrument.id, instrument]))
}

function todayChangeOf(instrument) {
  const previousClose = instrument.previousClose
  const latest = instrument.value
  if (!Number.isFinite(previousClose) || !Number.isFinite(latest)) {
    return { delta: null, percent: null }
  }

  const delta = latest - previousClose
  const percent = previousClose === 0 ? null : (delta / Math.abs(previousClose)) * 100
  return { delta, percent }
}

function providerAgeMs(instrument, now) {
  if (!Number.isFinite(instrument.providerTimestampMs)) return null
  return Math.max(0, now - instrument.providerTimestampMs)
}

export function freshnessOf(instrument, now) {
  const polledAt = Number.isFinite(instrument.polledAtMs) ? instrument.polledAtMs : null
  const hasProviderTime = Number.isFinite(instrument.providerTimestampMs)
  if (!hasProviderTime && polledAt == null) return 'MISSING'
  if (
    instrument.marketOpen === false &&
    polledAt != null &&
    Number.isFinite(instrument.closedStaleAfterMs) &&
    instrument.closedStaleAfterMs > 0
  ) {
    return now - polledAt <= instrument.closedStaleAfterMs ? 'CLOSED' : 'STALE'
  }
  if (!hasProviderTime) return 'MISSING'
  if (!Number.isFinite(instrument.staleAfterMs)) return 'MISSING'
  return now - instrument.providerTimestampMs <= instrument.staleAfterMs
    ? 'LIVE'
    : 'STALE'
}

export function marketRowsOf(instruments, now) {
  return instruments.map((instrument) => {
    const todayChange = todayChangeOf(instrument)
    const state = freshnessOf(instrument, now)
    return {
      instrument,
      todayChange,
      todayDirection: directionOf(todayChange.delta),
      providerAgeMs: providerAgeMs(instrument, now),
      state,
      live: state === 'LIVE',
    }
  })
}

export function summarizeFeed(instruments, now) {
  const summary = {
    rows: instruments.length,
    symbols: new Set(instruments.map((instrument) => instrument.symbol)).size,
    live: 0,
    stale: 0,
    closed: 0,
    missing: 0,
    lastUpdateMs: null,
  }
  for (const instrument of instruments) {
    const state = freshnessOf(instrument, now)
    if (state === 'LIVE') summary.live += 1
    else if (state === 'CLOSED') summary.closed += 1
    else if (state === 'MISSING') summary.missing += 1
    else summary.stale += 1
    const seenAt = instrument.polledAtMs ?? instrument.eventTimeMs
    if (seenAt != null && (summary.lastUpdateMs == null || seenAt > summary.lastUpdateMs)) {
      summary.lastUpdateMs = seenAt
    }
  }
  return summary
}

function watchedIdsOf(watchlistItems) {
  const ids = new Set()
  for (const item of watchlistItems) {
    for (const [provider, chosen] of Object.entries(item.providers ?? {})) {
      if (chosen) ids.add(instrumentId(provider, item.symbol))
    }
  }
  return ids
}

function placeholderInstrument(id, provider, item) {
  return {
    id,
    symbol: item.symbol,
    provider,
    assetClass: item.asset_class ?? 'UNKNOWN',
    currency: item.currency ?? null,
    value: null,
    bid: null,
    ask: null,
    last: null,
    previousClose: null,
    grade: null,
    providerTimestampMs: null,
    polledAtMs: null,
    staleAfterMs: null,
    closedStaleAfterMs: null,
    marketOpen: null,
    watched: true,
    held: false,
    benchmark: false,
    history: [],
    watchlisted: true,
  }
}

export function boardInstruments(instruments, watchlistItems, watchlistReady = true) {
  const watchedIds = watchedIdsOf(watchlistItems)
  const isWatchlisted = (instrument) =>
    watchlistReady ? watchedIds.has(instrument.id) : watchedIds.has(instrument.id) || instrument.watched
  const annotated = instruments.map((instrument) =>
    isWatchlisted(instrument) ? { ...instrument, watchlisted: true } : instrument,
  )
  const presentIds = new Set(annotated.map((instrument) => instrument.id))
  for (const item of watchlistItems) {
    for (const [provider, chosen] of Object.entries(item.providers ?? {})) {
      const id = instrumentId(provider, item.symbol)
      if (!chosen || presentIds.has(id)) continue
      annotated.push(placeholderInstrument(id, provider, item))
    }
  }
  return annotated
}

export function seedInstrumentHistories(previous, series) {
  if (!series || typeof series !== 'object') return previous
  const instruments = {}
  for (const [id, current] of Object.entries(previous)) {
    const rawPoints = series[id]
    const points = (Array.isArray(rawPoints) ? rawPoints : [])
      .map((point) => [toNum(point?.[0]), toNum(point?.[1])])
      .filter(([atMs, value]) => atMs != null && value != null)
    instruments[id] = {
      ...current,
      history: appendPoint(points, current.eventTimeMs, current.value),
    }
  }
  return instruments
}

const STATE_SORT_RANK = { LIVE: 0, CLOSED: 1, STALE: 2, MISSING: 3 }

function structuralValueOf(instrument, column) {
  if (column === 'symbol') return instrument.symbol
  if (column === 'provider') return instrument.provider
  if (column === 'assetClass') return instrument.assetClass
  return undefined
}

function snapshotValueOf(instrument, column, now) {
  if (!instrument) return null
  if (column === 'bid') return instrument.bid
  if (column === 'ask') return instrument.ask
  if (column === 'last') return instrument.last
  if (column === 'todayChange') {
    const { percent } = todayChangeOf(instrument)
    return Number.isFinite(percent) ? percent : null
  }
  if (column === 'age') return providerAgeMs(instrument, now)
  if (column === 'feed') return STATE_SORT_RANK[freshnessOf(instrument, now)] ?? 9
  if (column === 'updated') return instrument.eventTimeMs ?? null
  return null
}

function compareInstruments(a, b) {
  const classDiff = a.assetClass.localeCompare(b.assetClass)
  if (classDiff !== 0) return classDiff
  const symbolDiff = a.symbol.localeCompare(b.symbol)
  return symbolDiff || a.id.localeCompare(b.id)
}

export function captureMarketSnapshot(rows, column, now) {
  const values = {}
  for (const row of rows) {
    values[row.instrument.id] = snapshotValueOf(row.instrument, column, now)
  }
  return values
}

export function sortMarketRows(rows, sort) {
  return sortRows(rows, sort, {
    valueOf: (row) => {
      const structural = structuralValueOf(row.instrument, sort.column)
      return structural === undefined
        ? (sort.snapshot?.[row.instrument.id] ?? null)
        : structural
    },
    tieBreak: (a, b) => compareInstruments(a.instrument, b.instrument),
  })
}

export function providerScheduleText(provider) {
  return provider?.runtime?.strategy?.description ?? '—'
}
