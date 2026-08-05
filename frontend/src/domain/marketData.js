
import {
  HISTORY_LENGTH,
  MARKET_STALE_AFTER_MS,
  BOND_CURVE_TENORS,
} from '../config/marketData.js'
import { formatTenor } from './marketFormat.js'
import { directionOf } from './formatting.js'
import { sortRows } from './tableSort.js'

const MARKET_STATE_STORAGE_VERSION = 1
const MAX_STORED_INSTRUMENTS = 100

function toNum(value) {
  if (value == null || value === '') return null
  const n = Number(value)
  return Number.isFinite(n) ? n : null
}

function pickSpotValue(tick) {
  return toNum(tick.mid ?? tick.last ?? tick.spot)
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

function spotInstrument(tick, snapshotStreamId = null) {
  if (!tick || typeof tick.symbol !== 'string' || tick.symbol.length === 0) return null
  return {
    id: tick.symbol,
    symbol: tick.symbol,
    assetClass: tick.asset_class ?? 'UNKNOWN',
    currency: tick.currency ?? null,
    value: pickSpotValue(tick),
    bid: toNum(tick.bid),
    ask: toNum(tick.ask),
    unit: 'price',
    tenor: null,
    sourceStreamId: tick.stream_id ?? snapshotStreamId,
    sourceEventId: eventIdOf(tick),
    eventTimeMs: eventTimeOf(tick),
  }
}

function curveInstruments(curve, snapshotStreamId = null) {
  if (!curve || typeof curve.curve_name !== 'string' || curve.curve_name.length === 0) {
    return []
  }
  const tenors = curve.tenors ?? []
  const rates = curve.rates ?? []
  const eventTimeMs = eventTimeOf(curve)
  return tenors.flatMap((tenor, i) =>
    BOND_CURVE_TENORS.includes(Number(tenor))
      ? [
          {
            id: `${curve.curve_name}@${tenor}`,
            symbol: `${curve.curve_name} · ${formatTenor(tenor)}`,
            assetClass: 'RATE',
            currency: curve.currency ?? null,
            value: toNum(rates[i]),
            bid: null,
            ask: null,
            unit: 'rate',
            tenor,
            sourceStreamId: curve.stream_id ?? snapshotStreamId,
            sourceEventId: eventIdOf(curve),
            eventTimeMs,
          },
        ]
      : [],
  )
}

export function instrumentsFromEvent(name, data) {
  if (name === 'curve_tick') return curveInstruments(data)
  if (name === 'market_tick') return [spotInstrument(data)].filter(Boolean)
  return []
}

export function instrumentsFromSnapshot(snapshot) {
  const streamId = snapshot?.stream_id ?? null
  const spots = Object.values(snapshot?.spots ?? {})
    .map((spot) => spotInstrument(spot, streamId))
    .filter(Boolean)
  const curves = Object.values(snapshot?.curves ?? {}).flatMap((curve) =>
    curveInstruments(curve, streamId),
  )
  return [...spots, ...curves]
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

  const previous = sourceRestarted ? null : prev
  const prevHistory = previous?.history ?? []
  const hasValue = Number.isFinite(update.value)
  const history = hasValue
    ? [...prevHistory, update.value].slice(-HISTORY_LENGTH)
    : prevHistory
  const observedOpen = Number.isFinite(previous?.observedOpen)
    ? previous.observedOpen
    : (prevHistory.find(Number.isFinite) ?? update.value)
  const observationCount =
    (previous?.observationCount ?? prevHistory.length) + (hasValue ? 1 : 0)
  const previousValue =
    previous && hasValue && Number.isFinite(previous.value) ? previous.value : null
  let lastDirection = 'flat'
  if (Number.isFinite(previousValue)) {
    if (update.value > previousValue) lastDirection = 'pos'
    else if (update.value < previousValue) lastDirection = 'neg'
  }

  return {
    ...update,
    history,
    observedOpen,
    observationCount,
    previousValue,
    lastDirection,
    updateSeq: (previous?.updateSeq ?? 0) + 1,
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

  const tenor = Number(candidate.tenor)
  if (candidate.assetClass === 'RATE' && !BOND_CURVE_TENORS.includes(tenor)) {
    return null
  }

  const value = toNum(candidate.value)
  const history = (Array.isArray(candidate.history) ? candidate.history : [])
    .map(toNum)
    .filter(Number.isFinite)
    .slice(-HISTORY_LENGTH)
  if (Number.isFinite(value) && history[history.length - 1] !== value) {
    history.push(value)
    if (history.length > HISTORY_LENGTH) history.shift()
  }

  const observedOpen = Number.isFinite(candidate.observedOpen)
    ? candidate.observedOpen
    : (history[0] ?? value)
  const storedObservationCount = Number(candidate.observationCount)
  const observationCount = Number.isSafeInteger(storedObservationCount)
    ? Math.max(storedObservationCount, history.length)
    : history.length
  const storedUpdateSeq = Number(candidate.updateSeq)

  return {
    id: candidate.id,
    symbol: candidate.symbol,
    assetClass: candidate.assetClass,
    currency: typeof candidate.currency === 'string' ? candidate.currency : null,
    value,
    bid: toNum(candidate.bid),
    ask: toNum(candidate.ask),
    unit: candidate.unit === 'rate' ? 'rate' : 'price',
    tenor: Number.isFinite(tenor) ? tenor : null,
    sourceStreamId:
      typeof candidate.sourceStreamId === 'string' ? candidate.sourceStreamId : null,
    sourceEventId: eventIdOf({ event_id: candidate.sourceEventId }),
    eventTimeMs: Number.isFinite(candidate.eventTimeMs) ? candidate.eventTimeMs : null,
    receivedAtMs: Number.isFinite(candidate.receivedAtMs)
      ? candidate.receivedAtMs
      : null,
    previousValue: toNum(candidate.previousValue),
    history,
    observedOpen,
    observationCount,
    lastDirection: ['pos', 'neg', 'flat'].includes(candidate.lastDirection)
      ? candidate.lastDirection
      : 'flat',
    updateSeq: Number.isSafeInteger(storedUpdateSeq) ? Math.max(0, storedUpdateSeq) : 0,
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

export function observedChangeOf(instrument) {
  const history = instrument.history ?? []
  const observations = instrument.observationCount ?? history.length
  const first = Number.isFinite(instrument.observedOpen)
    ? instrument.observedOpen
    : history[0]
  const last = Number.isFinite(instrument.value)
    ? instrument.value
    : history[history.length - 1]

  if (observations < 2 || !Number.isFinite(first) || !Number.isFinite(last)) {
    return { delta: null, percent: null, observations }
  }

  const delta = last - first
  const percent = first === 0 ? null : (delta / Math.abs(first)) * 100

  return { delta, percent, observations }
}

export function lastTickChangeOf(instrument) {
  const previous = instrument.previousValue
  const latest = instrument.value
  if (!Number.isFinite(previous) || !Number.isFinite(latest)) {
    return { delta: null, percent: null }
  }

  const delta = latest - previous
  const percent = previous === 0 ? null : (delta / Math.abs(previous)) * 100
  return { delta, percent }
}

export function isStale(instrument, now) {
  if (instrument.receivedAtMs == null) return true
  return now - instrument.receivedAtMs > MARKET_STALE_AFTER_MS
}

export function marketRowsOf(instruments, now) {
  return instruments.map((instrument) => {
    const observedChange = observedChangeOf(instrument)
    const lastTickChange = lastTickChangeOf(instrument)
    return {
      instrument,
      observedChange,
      lastTickChange,
      observedDirection: directionOf(observedChange.delta),
      lastTickDirection: directionOf(lastTickChange.delta),
      live: !isStale(instrument, now),
    }
  })
}

export function summarizeFeed(instruments, now) {
  let live = 0
  let stale = 0
  let lastUpdateMs = null
  for (const instrument of instruments) {
    if (isStale(instrument, now)) stale += 1
    else live += 1
    const seenAt = instrument.receivedAtMs ?? instrument.eventTimeMs
    if (seenAt != null && (lastUpdateMs == null || seenAt > lastUpdateMs)) {
      lastUpdateMs = seenAt
    }
  }
  return { total: instruments.length, live, stale, lastUpdateMs }
}

function structuralValueOf(instrument, column) {
  if (column === 'symbol') return instrument.symbol
  if (column === 'assetClass') return instrument.assetClass
  if (column === 'tenor') return instrument.tenor
  return undefined
}

function snapshotValueOf(instrument, column, now) {
  if (!instrument) return null
  if (column === 'marketLevel') return instrument.value
  if (column === 'observedChange' || column === 'lastTickChange') {
    const change =
      column === 'observedChange'
        ? observedChangeOf(instrument)
        : lastTickChangeOf(instrument)
    if (instrument.unit === 'rate') {
      return Number.isFinite(change.delta) ? change.delta * 10000 : null
    }
    return Number.isFinite(change.percent) ? change.percent : null
  }
  if (column === 'quote') {
    if (
      !Number.isFinite(instrument.bid) ||
      !Number.isFinite(instrument.ask) ||
      !Number.isFinite(instrument.value) ||
      instrument.value === 0
    ) {
      return null
    }
    return ((instrument.ask - instrument.bid) / Math.abs(instrument.value)) * 10000
  }
  if (column === 'feed') return isStale(instrument, now) ? 0 : 1
  if (column === 'updated') return instrument.eventTimeMs ?? null
  return null
}

function compareInstruments(a, b) {
  const classDiff = a.assetClass.localeCompare(b.assetClass)
  if (classDiff !== 0) return classDiff
  if (a.tenor != null && b.tenor != null && a.tenor !== b.tenor) {
    return a.tenor - b.tenor
  }
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
      return structural === undefined ? (sort.snapshot?.[row.instrument.id] ?? null) : structural
    },
    tieBreak: (a, b) => compareInstruments(a.instrument, b.instrument),
  })
}
