const SEVERITY_TONE = {
  CRITICAL: 'critical',
  ERROR: 'error',
  WARNING: 'warning',
  INFO: 'info',
}

export function labelForService(name) {
  if (!name) return 'UNKNOWN'
  return name.replace(/-service$/, '').replace(/-/g, ' ').toUpperCase()
}
export function normalizeAuditEvents(raw) {
  if (!Array.isArray(raw)) return []
  return raw.map((row, index) => {
    const severity = String(row?.severity ?? 'INFO').toUpperCase()
    const createdAtMs = Date.parse(row?.created_at ?? '')
    return {
      id: row?.audit_id ?? `${row?.service_name}:${row?.created_at}:${index}`,
      createdAtMs: Number.isNaN(createdAtMs) ? null : createdAtMs,
      service: row?.service_name ?? null,
      serviceLabel: labelForService(row?.service_name),
      eventType: row?.event_type ?? 'UNKNOWN',
      severity,
      tone: SEVERITY_TONE[severity] ?? 'unknown',
      message: row?.message ?? '',
      entityId: row?.entity_id ?? null,
      correlationId: row?.correlation_id ?? null,
    }
  })
}
