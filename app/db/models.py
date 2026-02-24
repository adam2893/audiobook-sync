"""
SQLAlchemy database models for Audiobook Sync Service.
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, Text, JSON, Boolean
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class Config(Base):
    """Application configuration stored in database."""
    __tablename__ = 'config'
    
    id = Column(Integer, primary_key=True)
    abs_url = Column(String(500), nullable=True)
    abs_token = Column(String(500), nullable=True)
    sg_cookie = Column(String(2000), nullable=True)  # remember_user_token cookie
    sg_username = Column(String(255), nullable=True)  # StoryGraph username
    hc_api_key = Column(String(500), nullable=True)
    sync_interval_minutes = Column(Integer, default=60)
    min_listen_time_seconds = Column(Integer, default=600)  # 10 minutes
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SyncHistory(Base):
    """History of sync operations for each book."""
    __tablename__ = 'sync_history'
    
    id = Column(Integer, primary_key=True)
    abs_book_id = Column(String(100), index=True, nullable=False)
    book_title = Column(String(500), nullable=True)
    book_author = Column(String(500), nullable=True)
    isbn = Column(String(20), nullable=True)
    asin = Column(String(20), nullable=True)
    progress_percent = Column(Float, nullable=True)
    sg_book_id = Column(String(100), nullable=True)
    hc_book_id = Column(String(100), nullable=True)
    sg_status = Column(String(50), nullable=True)  # success, failed, skipped
    hc_status = Column(String(50), nullable=True)  # success, failed, skipped
    sg_error = Column(Text, nullable=True)
    hc_error = Column(Text, nullable=True)
    synced_at = Column(DateTime, default=datetime.utcnow, index=True)


class BookMapping(Base):
    """Cached mapping between Audiobookshelf books and external services."""
    __tablename__ = 'book_mapping'
    
    id = Column(Integer, primary_key=True)
    abs_book_id = Column(String(100), unique=True, index=True, nullable=False)
    sg_book_id = Column(String(100), nullable=True)
    hc_book_id = Column(String(100), nullable=True)
    isbn = Column(String(20), nullable=True)
    asin = Column(String(20), nullable=True)
    title = Column(String(500), nullable=True)
    author = Column(String(500), nullable=True)
    last_matched = Column(DateTime, default=datetime.utcnow)
    match_confidence = Column(Float, default=0.0)  # 0.0 to 1.0


class SyncLog(Base):
    """Detailed logs for sync operations."""
    __tablename__ = 'sync_log'
    
    id = Column(Integer, primary_key=True)
    level = Column(String(20), nullable=False)  # DEBUG, INFO, WARNING, ERROR
    message = Column(Text, nullable=False)
    details = Column(JSON, nullable=True)
    sync_run_id = Column(String(50), index=True, nullable=True)  # Group logs by sync run
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class SyncRun(Base):
    """Represents a single sync run (execution)."""
    __tablename__ = 'sync_run'
    
    id = Column(Integer, primary_key=True)
    run_id = Column(String(50), unique=True, index=True, nullable=False)
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    status = Column(String(20), default='running')  # running, completed, failed
    books_processed = Column(Integer, default=0)
    books_synced = Column(Integer, default=0)
    books_skipped = Column(Integer, default=0)
    books_failed = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
