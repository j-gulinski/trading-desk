import json
import uuid
import datetime
from decimal import Decimal
from enum import Enum


def to_json(obj) -> str:
    def convert(o):
        if isinstance(o, Decimal):
            return str(o)
        if isinstance(o, (datetime.datetime, datetime.date)):
            return o.isoformat()
        if isinstance(o, uuid.UUID):
            return str(o)
        if isinstance(o, Enum):
            return o.value
        raise TypeError(f"Object of type {type(o).__name__} is not JSON serializable")

    return json.dumps(obj, default=convert)
