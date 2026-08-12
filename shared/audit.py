import uuid

from shared.db import session_scope
from shared.models import AuditLog
from shared.functions import utcnow
from shared.logging_config import get_logger

log = get_logger("audit")


def write_audit(service_name, event_type, message, *, entity_type=None, entity_id=None,
                correlation_id=None, severity="INFO", payload=None, session=None):
    row = AuditLog(
        audit_id=uuid.uuid4(),
        service_name=service_name,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        correlation_id=correlation_id,
        severity=severity,
        message=message,
        payload=payload,
        created_at=utcnow(),
    )
    if session is not None:
        session.add(row)
    else:
        try:
            with session_scope() as own:
                own.add(row)
        except Exception as exc:
            log.error("audit_write_failed", event_type=event_type,
                      service=service_name, error=type(exc).__name__)
