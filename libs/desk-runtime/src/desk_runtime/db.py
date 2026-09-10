from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from desk_runtime.config import env_required
from desk_runtime.serialization import to_json

engine = create_engine(env_required("DATABASE_URL"), pool_pre_ping=True, json_serializer=to_json)
SessionFactory = sessionmaker(bind=engine)


def session_scope():
    return SessionFactory.begin()
