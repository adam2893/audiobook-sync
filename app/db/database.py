"""
Database connection and session management.
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from contextlib import contextmanager

from app.db.models import Base


def get_database_url() -> str:
    """Get database URL from environment or use default."""
    return os.getenv("DATABASE_URL", "sqlite:///data/audiobook-sync.db")


def ensure_data_directory():
    """Ensure the data directory exists for SQLite database."""
    db_url = get_database_url()
    if db_url.startswith("sqlite:///"):
        db_path = db_url.replace("sqlite:///", "")
        os.makedirs(os.path.dirname(db_path), exist_ok=True)


# Create engine
engine = None
SessionLocal = None


def init_db():
    """Initialize the database engine and create tables."""
    global engine, SessionLocal
    
    ensure_data_directory()
    
    db_url = get_database_url()
    engine = create_engine(
        db_url,
        connect_args={"check_same_thread": False} if db_url.startswith("sqlite") else {},
        echo=False
    )
    
    SessionLocal = scoped_session(
        sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)
    )
    
    # Create all tables
    Base.metadata.create_all(bind=engine)
    
    return engine


def get_session():
    """Get a database session."""
    if SessionLocal is None:
        init_db()
    return SessionLocal()


@contextmanager
def get_db_session():
    """Context manager for database sessions."""
    session = get_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def close_db():
    """Close the database connection."""
    global engine, SessionLocal
    if SessionLocal:
        SessionLocal.remove()
    if engine:
        engine.dispose()
