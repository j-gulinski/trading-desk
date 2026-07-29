import { FLUSH_INTERVAL_MS } from '../config/stream.js'

const subscriptions = new Set()
let clockId = null

function tick() {
  const now = Date.now()
  for (const subscription of Array.from(subscriptions)) {
    subscription.ticksUntilRun -= 1
    if (subscription.ticksUntilRun > 0) continue
    subscription.ticksUntilRun = subscription.everyTicks
    subscription.subscriber(now)
  }
}

export function subscribeToStreamClock(subscriber, intervalMs = FLUSH_INTERVAL_MS) {
  const everyTicks = Math.max(1, Math.ceil(intervalMs / FLUSH_INTERVAL_MS))
  const subscription = { subscriber, everyTicks, ticksUntilRun: everyTicks }

  subscriptions.add(subscription)
  if (clockId === null) clockId = setInterval(tick, FLUSH_INTERVAL_MS)

  return () => {
    subscriptions.delete(subscription)
    if (subscriptions.size > 0) return
    clearInterval(clockId)
    clockId = null
  }
}
