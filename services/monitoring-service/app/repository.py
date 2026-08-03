from shared.db import session_scope
from shared.models import AuditLog

DEFAULT_LIMIT = 100
MAX_LIMIT = 500


def _to_dict(row: AuditLog) -> dict:
    return {
        "audit_id": row.audit_id,
        "created_at": row.created_at,
        "service_name": row.service_name,
        "event_type": row.event_type,
        "severity": row.severity,
        "message": row.message,
        "entity_type": row.entity_type,
        "entity_id": row.entity_id,
        "correlation_id": row.correlation_id,
    }


def recent_audits(*, limit=DEFAULT_LIMIT, since=None, severities=None,
                  services=None, event_types=None) -> list[dict]:
    limit = max(1, min(int(limit), MAX_LIMIT))
    with session_scope() as session:
        q = session.query(AuditLog)
        if since is not None:
            q = q.filter(AuditLog.created_at >= since)
        if severities:
            q = q.filter(AuditLog.severity.in_(severities))
        if services:
            q = q.filter(AuditLog.service_name.in_(services))
        if event_types:
            q = q.filter(AuditLog.event_type.in_(event_types))
        rows = q.order_by(AuditLog.created_at.desc()).limit(limit).all()
        return [_to_dict(r) for r in rows]
