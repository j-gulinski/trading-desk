import { catalogueFieldsOf } from './catalogue.js'
import { directionOf } from './formatting.js'
import { toNum } from './values.js'

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
  const staleAtMs = Date.parse(tick.stale_at ?? '')
  return {
    id: provider ? instrumentId(provider, tick.symbol) : tick.symbol,
    symbol: tick.symbol,
    name: typeof tick.name === 'string' ? tick.name : null,
    provider,
    assetClass: tick.asset_class ?? 'UNKNOWN',
    ...catalogueFieldsOf(tick),
    currency: tick.currency ?? null,
    market: typeof tick.market === 'string' ? tick.market : null,
    value: toNum(tick.mid ?? tick.last),
    bid: toNum(tick.bid),
    ask: toNum(tick.ask),
    buyPrice: toNum(tick.buy_price),
    sellPrice: toNum(tick.sell_price),
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
    freshness: typeof tick.freshness === 'string' ? tick.freshness : 'MISSING',
    staleAtMs: Number.isFinite(staleAtMs) ? staleAtMs : null,
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

function isNewer(prev, update) {
  const providerTimesKnown = Number.isFinite(prev.providerTimestampMs) &&
    Number.isFinite(update.providerTimestampMs)
  if (providerTimesKnown && update.providerTimestampMs !== prev.providerTimestampMs) {
    return update.providerTimestampMs > prev.providerTimestampMs
  }
  if (
    Number.isFinite(prev.polledAtMs) &&
    Number.isFinite(update.polledAtMs) &&
    update.polledAtMs !== prev.polledAtMs
  ) {
    return update.polledAtMs > prev.polledAtMs
  }
  if (prev.sourceEventId != null && update.sourceEventId != null) {
    return update.sourceEventId > prev.sourceEventId
  }
  return !(Number.isFinite(prev.eventTimeMs) && Number.isFinite(update.eventTimeMs)) ||
    update.eventTimeMs > prev.eventTimeMs
}

function mergeInstrument(prev, update) {
  if (prev && !isNewer(prev, update)) return prev
  const previous = prev
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

export function snapshotInstruments(snapshot) {
  const receivedAtMs = Date.now()
  const updates = instrumentsFromSnapshot(snapshot).map((instrument) => ({
    ...instrument,
    receivedAtMs,
  }))
  return mergeInstruments({}, updates)
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
  return Number.isFinite(instrument.staleAtMs) && now > instrument.staleAtMs
    ? 'STALE'
    : instrument.freshness ?? 'MISSING'
}

export function marketRowsOf(instruments, now) {
  return instruments.map((instrument) => {
    const todayChange = todayChangeOf(instrument)
    const tickChange = instrument.grade === 'EOD'
      ? { delta: null, percent: null }
      : tickChangeOf(instrument)
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
    if (state === 'LIVE') summary.live += 1
    else if (state === 'EOD') summary.eod += 1
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
    ...catalogueFieldsOf(item),
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
    freshness: 'MISSING',
    staleAtMs: null,
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
          ...catalogueFieldsOf(item),
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
