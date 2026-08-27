import logging
import logging.handlers
from pathlib import Path

import structlog

from desk_runtime.config import LOG_DIR, LOG_FILE_BACKUP_COUNT, LOG_FILE_MAX_BYTES, LOG_LEVEL


def _file_handler(service_name):
    if not LOG_DIR or not service_name:
        return None, None
    try:
        directory = Path(LOG_DIR)
        directory.mkdir(parents=True, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(
            directory / f"{service_name}.log",
            maxBytes=LOG_FILE_MAX_BYTES,
            backupCount=LOG_FILE_BACKUP_COUNT,
        )
        return handler, None
    except OSError as exc:
        return None, str(exc)


def configure_logging(service_name=None):
    level = getattr(logging, (LOG_LEVEL or "INFO").upper(), logging.INFO)

    handlers = [logging.StreamHandler()]
    file_handler, file_error = _file_handler(service_name)
    if file_handler is not None:
        handlers.append(file_handler)
    logging.basicConfig(format="%(message)s", level=level, handlers=handlers, force=True)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    if file_error is not None:
        get_logger(service_name).warning("log_file_sink_unavailable", log_dir=LOG_DIR, error=file_error)


def get_logger(name=None):
    return structlog.get_logger(name)
