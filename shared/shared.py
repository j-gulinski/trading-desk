import datetime

def get_iso_timestamp():
    return datetime.datetime.utcnow().isoformat()[:-3] + "Z"