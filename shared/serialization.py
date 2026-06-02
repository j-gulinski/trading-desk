import json
import uuid
import datetime
from decimal import Decimal
from enum import Enum


class TradingJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return str(obj)
        if isinstance(obj, (datetime.datetime, datetime.date)):
            return obj.isoformat()
        if isinstance(obj, uuid.UUID):
            return str(obj)
        if isinstance(obj, Enum):
            return obj.value
        return super().default(obj)


def to_json(obj) -> str:
    return json.dumps(obj, cls=TradingJSONEncoder)


def model_to_dict(model_instance) -> dict:
    result = {}
    for col in model_instance.__table__.columns:
        val = getattr(model_instance, col.name)
        if isinstance(val, Decimal):
            val = str(val)
        elif isinstance(val, (datetime.datetime, datetime.date)):
            val = val.isoformat()
        elif isinstance(val, uuid.UUID):
            val = str(val)
        elif isinstance(val, Enum):
            val = val.value
        result[col.name] = val
    return result
