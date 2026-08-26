const watchlistEvents = new EventTarget()

export function announceWatchlistChange() {
  watchlistEvents.dispatchEvent(new Event('change'))
}

export function onWatchlistChange(listener) {
  watchlistEvents.addEventListener('change', listener)
  return () => watchlistEvents.removeEventListener('change', listener)
}
