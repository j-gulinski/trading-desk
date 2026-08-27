import { directionOf } from './formatting.js'
import { toNum } from './values.js'

const MARKET_STATE_STORAGE_VERSION = 14
const MAX_STORED_INSTRUMENTS = 100

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
    name: typeof tick.name === 'string' ? tick.name : null,
    provider,
    assetClass: tick.asset_class ?? 'UNKNOWN',
    currency: tick.currency ?? null,
    market: typeof tick.market === 'string' ? tick.market : null,
    value: toNum(tick.mid ?? tick.last),
    bid: toNum(tick.bid),
    ask: toNum(tick.ask),
    last: toNum(tick.last),
    previousClose: toNum(tick.previous_close),
    priceBasis: typeof tick.price_basis === 'string' ? tick.price_basis : null,
    grade: tick.quote_grade ?? null,
    providerTimestamp: typeof tick.provider_timestamp === 'string'
      ? tick.provider_timestamp
      : null,
    receivedAt: typeof tick.received_at === 'string' ? tick.received_at : null,
    providerTimestampMs: Number.isFinite(providerTimestampMs) ? providerTimestampMs : null,
    polledAtMs: Number.isFinite(polledAtMs) ? polledAtMs : null,
    staleAfterMs: staleAfterSeconds != null ? staleAfterSeconds * 1000 : null,
    closedStaleAfterMs:
      closedStaleAfterSeconds != null ? closedStaleAfterSeconds * 1000 : null,
    marketOpen: typeof tick.market_open === 'boolean' ? tick.market_open : null,
    watched: tick.watched === true,
    held: tick.held === true,
    benchmark: tick.benchmark === true,
    reference: tick.reference === true,
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

function mergeInstrument(prev, update) {
  let sourceRestarted = false

  if (prev) {
    const providerTimesKnown = Number.isFinite(prev.providerTimestampMs) &&
      Number.isFinite(update.providerTimestampMs)
    if (providerTimesKnown && update.providerTimestampMs < prev.providerTimestampMs) {
      return prev
    }
    const sameProviderTime = providerTimesKnown &&
      update.providerTimestampMs === prev.providerTimestampMs
    if (
      sameProviderTime &&
      Number.isFinite(prev.polledAtMs) &&
      Number.isFinite(update.polledAtMs) &&
      update.polledAtMs < prev.polledAtMs
    ) {
      return prev
    }
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

  const previous = sourceRestarted ? null : prev
  const previousValue =
    previous && Number.isFinite(update.value) && Number.isFinite(previous.value)
      ? previous.value
      : null

  return {
    ...update,
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
    name: typeof candidate.name === 'string' ? candidate.name : null,
    provider: typeof candidate.provider === 'string' ? candidate.provider : null,
    assetClass: candidate.assetClass,
    currency: typeof candidate.currency === 'string' ? candidate.currency : null,
    market: typeof candidate.market === 'string' ? candidate.market : null,
    value: toNum(candidate.value),
    bid: toNum(candidate.bid),
    ask: toNum(candidate.ask),
    last: toNum(candidate.last),
    previousClose: toNum(candidate.previousClose),
    priceBasis: typeof candidate.priceBasis === 'string' ? candidate.priceBasis : null,
    grade: typeof candidate.grade === 'string' ? candidate.grade : null,
    providerTimestamp: typeof candidate.providerTimestamp === 'string'
      ? candidate.providerTimestamp
      : null,
    receivedAt: typeof candidate.receivedAt === 'string' ? candidate.receivedAt : null,
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
    reference: candidate.reference === true,
    sourceStreamId:
      typeof candidate.sourceStreamId === 'string' ? candidate.sourceStreamId : null,
    sourceEventId: eventIdOf({ event_id: candidate.sourceEventId }),
    eventTimeMs: Number.isFinite(candidate.eventTimeMs) ? candidate.eventTimeMs : null,
    receivedAtMs: Number.isFinite(candidate.receivedAtMs) ? candidate.receivedAtMs : null,
    previousValue: toNum(candidate.previousValue),
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

function tickChangeOf(instrument) {
  const previous = instrument.previousValue
  const latest = instrument.value
  if (!Number.isFinite(previous) || !Number.isFinite(latest)) {
    return { delta: null, percent: null }
  }

  const delta = latest - previous
  const percent = previous === 0 ? null : (delta / Math.abs(previous)) * 100
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
    const tickChange = tickChangeOf(instrument)
    const state = freshnessOf(instrument, now)
    return {
      instrument,
      todayChange,
      todayDirection: directionOf(todayChange.delta),
      tickChange,
      tickDirection: directionOf(tickChange.delta),
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
    eod: 0,
    stale: 0,
    closed: 0,
    missing: 0,
    lastUpdateMs: null,
  }
  for (const instrument of instruments) {
    const state = freshnessOf(instrument, now)
    if (state === 'LIVE' && instrument.grade === 'EOD') summary.eod += 1
    else if (state === 'LIVE') summary.live += 1
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
    name: item.name ?? null,
    provider,
    assetClass: item.asset_class ?? 'UNKNOWN',
    currency: item.currency ?? null,
    market: item.market ?? null,
    value: null,
    bid: null,
    ask: null,
    last: null,
    previousClose: null,
    priceBasis: null,
    grade: null,
    providerTimestampMs: null,
    polledAtMs: null,
    staleAfterMs: null,
    closedStaleAfterMs: null,
    marketOpen: null,
    watched: true,
    held: false,
    benchmark: false,
    watchlisted: true,
  }
}

export function boardInstruments(instruments, watchlistItems, watchlistReady = true) {
  const watchedIds = watchedIdsOf(watchlistItems)
  const itemBySymbol = new Map(watchlistItems.map((item) => [item.symbol, item]))
  const isWatchlisted = (instrument) =>
    watchlistReady ? watchedIds.has(instrument.id) : watchedIds.has(instrument.id) || instrument.watched
  const annotated = instruments.map((instrument) => {
    const item = itemBySymbol.get(instrument.symbol)
    const identity = item
      ? {
          name: item.name ?? instrument.name,
          market: item.market ?? instrument.market,
        }
      : null
    return isWatchlisted(instrument)
      ? { ...instrument, ...identity, watchlisted: true }
      : identity
        ? { ...instrument, ...identity }
        : instrument
  })
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

export function providerScheduleText(provider, elapsedMs = 0) {
  const strategy = provider?.runtime?.strategy
  const description = strategy?.description ?? '—'
  const snapshotSeconds = Number(strategy?.next_batch_seconds)
  if (!Number.isFinite(snapshotSeconds)) return description

  const elapsedSeconds = Math.max(0, Math.floor(elapsedMs / 1000))
  const nextBatchSeconds = Math.max(0, snapshotSeconds - elapsedSeconds)
  return description.replace(
    /next batch in \d+s/,
    `next batch in ${nextBatchSeconds}s`,
  )
}

export function providerStrategiesOf(providers) {
  const strategies = {}
  for (const provider of Array.isArray(providers) ? providers : []) {
    if (provider?.runtime?.strategy) strategies[provider.provider] = provider.runtime.strategy
  }
  return strategies
}
