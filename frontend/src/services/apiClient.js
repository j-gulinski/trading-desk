export class ApiError extends Error {
  constructor(message, { path, status = null, cause = null } = {}) {
    super(message)
    this.name = 'ApiError'
    this.path = path
    this.status = status
    this.cause = cause
  }
}

async function request(path, options = {}) {
  const { headers, ...fetchOptions } = options
  let res
  try {
    res = await fetch(path, {
      ...fetchOptions,
      headers: { Accept: 'application/json', ...headers },
    })
  } catch (cause) {
    throw new ApiError('Network error', { path, cause })
  }

  if (!res.ok) {
    throw new ApiError(`Request failed (${res.status})`, { path, status: res.status })
  }

  if (res.status === 204) return null
  return res.json()
}

export const apiGet = (path, options) => request(path, options)

export const apiPost = (path, body, options = {}) =>
  request(path, {
    ...options,
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...options.headers },
    body: JSON.stringify(body),
  })

export const apiPut = (path, body, options = {}) =>
  request(path, {
    ...options,
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', ...options.headers },
    body: JSON.stringify(body),
  })

export const apiDelete = (path, options = {}) =>
  request(path, { ...options, method: 'DELETE' })
