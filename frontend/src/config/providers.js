export const PROVIDER_STATUS_LEVELS = {
  OK: 'healthy',
  STARTING: 'unknown',
  RATE_LIMITED: 'degraded',
  ERROR: 'degraded',
  AUTH_FAILED: 'down',
  DISABLED: 'down',
}

const PROVIDER_NAMES = {
  ALPHA_VANTAGE: 'Alpha Vantage',
  NBP: 'National Bank of Poland',
  ECB: 'European Central Bank',
  FRED: 'Federal Reserve Economic Data',
  EIOPA: 'European Insurance and Occupational Pensions Authority',
}

export function providerLabel(provider) {
  return String(provider).replaceAll('_', ' ')
}

export function providerFullName(provider) {
  return PROVIDER_NAMES[provider] ?? providerLabel(provider)
}
