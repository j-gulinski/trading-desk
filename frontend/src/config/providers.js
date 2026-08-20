export const PROVIDER_STATUS_LEVELS = {
  OK: 'healthy',
  STARTING: 'unknown',
  RATE_LIMITED: 'degraded',
  ERROR: 'degraded',
  AUTH_FAILED: 'down',
  DISABLED: 'down',
}

export function providerLabel(provider) {
  return String(provider).replaceAll('_', ' ')
}
