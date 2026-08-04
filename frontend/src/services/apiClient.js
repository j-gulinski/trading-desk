import { WRITE_TIMEOUT_MS } from '../config/api.js'

export class ApiError extends Error {
  constructor(message, { path, status = null, cause = null, body = null } = {}) {
    super(message)
    this.name = 'ApiError'
    this.path = path
    this.status = status
    this.cause = cause
    this.body = body
  }
}

function withTimeout(signal, timeoutMs) {
  if (timeoutMs == null) return { signal, done: () => {} }
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  return {
    signal: signal ? AbortSignal.any([signal, controller.signal]) : controller.signal,
    done: () => clearTimeout(timer),
    timedOut: () => controller.signal.aborted,
  }
}

async function request(path, options = {}) {
  const { headers, timeoutMs = null, signal, ...fetchOptions } = options
  const timeout = withTimeout(signal, timeoutMs)
  let res
  try {
    res = await fetch(path, {
      ...fetchOptions,
      signal: timeout.signal,
      headers: { Accept: 'application/json', ...headers },
    })
  } catch (cause) {
    if (timeout.timedOut?.()) {
      throw new ApiError('Request timed out — the service did not answer', { path, cause })
    }
    throw new ApiError('Network error', { path, cause })
  } finally {
    timeout.done()
  }

  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw new ApiError(`Request failed (${res.status})`, { path, status: res.status, body })
  }

  if (res.status === 204) return null
  return res.json()
}

export const apiGet = (path, options) => request(path, options)

const write = (path, method, body, options) =>
  request(path, {
    timeoutMs: WRITE_TIMEOUT_MS,
    ...options,
    method,
    headers: { 'Content-Type': 'application/json', ...options.headers },
    body: JSON.stringify(body),
  })

export const apiPost = (path, body, options = {}) => write(path, 'POST', body, options)

export const apiPut = (path, body, options = {}) => write(path, 'PUT', body, options)

export const apiDelete = (path, options = {}) =>
  request(path, { timeoutMs: WRITE_TIMEOUT_MS, ...options, method: 'DELETE' })
