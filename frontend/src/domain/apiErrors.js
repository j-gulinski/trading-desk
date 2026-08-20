const UNREACHABLE = [502, 503, 504]

export function describeApiError(error, { service, outcome }) {
  const status = error?.status ?? null
  const reason = typeof error?.body?.error === 'string' ? error.body.error : null

  if (status == null || UNREACHABLE.includes(status)) {
    const timedOut = /timed out/i.test(error?.message ?? '')
    return timedOut
      ? `${service} did not answer in time — ${outcome}`
      : `${service} unavailable — ${outcome}`
  }

  if (status >= 500) return `${service} could not process the request — ${outcome}`
  if (reason) return `Rejected — ${reason}.`
  if (status === 404) return `No longer available — ${outcome}`
  return `Rejected by ${service} — ${outcome}`
}
