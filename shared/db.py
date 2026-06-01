import time
import logging

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from trading_shared.config import DATABASE_URL

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionFactory = sessionmaker(bind=engine)

def session_scope():
    session = SessionFactory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()