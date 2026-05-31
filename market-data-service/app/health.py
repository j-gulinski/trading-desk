from app import persistence


def get_health():
    with persistence.data_lock:
        return {
            "service": "market-data-service",
            "status": "UP",
            "generated_events": persistence.ticks_generated,
            "last_event_timestamp": persistence.last_event_timestamp,
        }
