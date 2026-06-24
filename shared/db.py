from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from shared.config import DATABASE_URL
from shared.serialization import to_json

# json_serializer so JSONB columns can hold Decimal/UUID/datetime (e.g. market
# data raw_payload), serialised consistently with the rest of the stack.
engine = create_engine(DATABASE_URL, pool_pre_ping=True, json_serializer=to_json)
SessionFactory = sessionmaker(bind=engine)
        
class session_scope:
    def __enter__(self):
        self.session = SessionFactory()
        return self.session

    def __exit__(self, exc_type, exc, tb):
        try:
            if exc_type is None:
                self.session.commit()
            else:
                self.session.rollback()
        finally:
            self.session.close()
        return False