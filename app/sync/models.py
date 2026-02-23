"""
Data models for sync operations.
"""

from dataclasses import dataclass, field
from typing import Optional, List
from datetime import datetime


@dataclass
class BookMatch:
    """Represents a matched book across services."""
    abs_book_id: str
    title: str
    author: Optional[str]
    isbn: Optional[str]
    asin: Optional[str]
    
    # External service IDs
    storygraph_book_id: Optional[str] = None
    hardcover_book_id: Optional[int] = None
    hardcover_user_book_id: Optional[int] = None
    
    # Match metadata
    match_confidence: float = 0.0
    match_method: str = ""  # isbn, asin, title_author


@dataclass
class SyncResult:
    """Result of a sync operation for a single book."""
    book_id: str
    title: str
    success: bool
    progress_percent: float
    
    # StoryGraph results
    sg_success: bool = False
    sg_error: Optional[str] = None
    
    # Hardcover results
    hc_success: bool = False
    hc_error: Optional[str] = None
    
    # Timing
    synced_at: datetime = None
    
    def __post_init__(self):
        if self.synced_at is None:
            self.synced_at = datetime.utcnow()


@dataclass
class SyncRunResult:
    """Result of a complete sync run."""
    run_id: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    
    # Counts
    books_processed: int = 0
    books_synced: int = 0
    books_skipped: int = 0
    books_failed: int = 0
    
    # Status
    success: bool = True
    error_message: Optional[str] = None
    
    # Individual results
    results: List[SyncResult] = field(default_factory=list)
