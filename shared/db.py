from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from shared.config import DATABASE_URL

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionFactory = sessionmaker(bind=engine)
        
class session_scope:
    def __enter__(self):
        self.session = SessionFactory()
        return self.session

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.session.commit()
        else:
            self.session.rollback()
        self.session.close()
        return False