"""
Main sync engine for Audiobook Sync Service.

Orchestrates the sync process between Audiobookshelf and external services.
"""

import uuid
from datetime import datetime
from typing import Optional, List

from app.api.audiobookshelf import AudiobookshelfClient, AudiobookProgress
from app.api.hardcover import HardcoverClient
from app.api.storygraph import StoryGraphClient
from app.config import ConfigManager, SyncConfig
from app.db.database import get_db_session
from app.db.models import SyncHistory, SyncRun
from app.sync.matcher import BookMatcher
from app.sync.models import BookMatch, SyncResult, SyncRunResult
from app.utils.logging import get_logger, SyncLogger

logger = get_logger(__name__)


class SyncEngine:
    """
    Main sync engine that coordinates the sync process.
    
    Responsibilities:
    - Fetch books in progress from Audiobookshelf
    - Match books with external services
    - Update progress in external services
    - Track sync history
    """
    
    def __init__(self, config: SyncConfig):
        """
        Initialize sync engine.
        
        Args:
            config: Sync configuration
        """
        self.config = config
        
        # Initialize clients
        self.abs_client: Optional[AudiobookshelfClient] = None
        self.hc_client: Optional[HardcoverClient] = None
        self.sg_client: Optional[StoryGraphClient] = None
        
        # Initialize matcher
        self.matcher: Optional[BookMatcher] = None
        
        # State
        self._initialized = False
    
    def initialize(self) -> bool:
        """
        Initialize API clients.
        
        Returns:
            True if initialization successful, False otherwise
        """
        try:
            # Initialize Audiobookshelf client
            if self.config.abs_url and self.config.abs_token:
                self.abs_client = AudiobookshelfClient(
                    self.config.abs_url,
                    self.config.abs_token
                )
                logger.info(
                    "Initialized Audiobookshelf client",
                    url=self.config.abs_url
                )
            
            # Initialize Hardcover client
            if self.config.enable_hardcover and self.config.hardcover_api_key:
                self.hc_client = HardcoverClient(self.config.hardcover_api_key)
                logger.info("Initialized Hardcover client")
            
            # Initialize StoryGraph client
            if self.config.enable_storygraph and self.config.storygraph_cookie:
                self.sg_client = StoryGraphClient(
                    self.config.storygraph_cookie,
                    self.config.storygraph_username
                )
                # Login to StoryGraph (validates cookie)
                if not self.sg_client.login():
                    logger.error("Failed to login to StoryGraph")
                    self.sg_client = None
                else:
                    logger.info("Initialized StoryGraph client")
            
            # Initialize matcher
            self.matcher = BookMatcher(
                hardcover_client=self.hc_client,
                storygraph_client=self.sg_client,
            )
            
            self._initialized = True
            return True
            
        except Exception as e:
            logger.error("Failed to initialize sync engine", error=str(e))
            return False
    
    def test_connections(self) -> dict:
        """
        Test connections to all configured services.
        
        Returns:
            Dict with connection status for each service
        """
        results = {
            "audiobookshelf": None,
            "hardcover": None,
            "storygraph": None,
        }
        
        if self.abs_client:
            results["audiobookshelf"] = self.abs_client.test_connection()
        
        if self.hc_client:
            results["hardcover"] = self.hc_client.test_connection()
        
        if self.sg_client:
            results["storygraph"] = self.sg_client.test_connection()
        
        return results
    
    def sync(self, run_id: Optional[str] = None) -> SyncRunResult:
        """
        Run a full sync operation.
        
        Args:
            run_id: Optional run ID (auto-generated if not provided)
            
        Returns:
            SyncRunResult with sync details
        """
        if not self._initialized:
            if not self.initialize():
                return SyncRunResult(
                    run_id=run_id or str(uuid.uuid4())[:8],
                    started_at=datetime.utcnow(),
                    completed_at=datetime.utcnow(),
                    success=False,
                    error_message="Failed to initialize sync engine",
                )
        
        # Check if Audiobookshelf client is available
        if not self.abs_client:
            return SyncRunResult(
                run_id=run_id or str(uuid.uuid4())[:8],
                started_at=datetime.utcnow(),
                completed_at=datetime.utcnow(),
                success=False,
                error_message="Audiobookshelf is not configured. Please set ABS_URL and ABS_TOKEN.",
            )
        
        run_id = run_id or str(uuid.uuid4())[:8]
        sync_logger = SyncLogger(run_id)
        
        result = SyncRunResult(
            run_id=run_id,
            started_at=datetime.utcnow(),
        )
        
        # Create sync run record
        with get_db_session() as session:
            sync_run = SyncRun(
                run_id=run_id,
                started_at=result.started_at,
                status="running",
            )
            session.add(sync_run)
        
        sync_logger.info("Starting sync run", run_id=run_id)
        
        try:
            # Get books in progress from Audiobookshelf
            min_listen_seconds = self.config.min_listen_minutes * 60
            books = self.abs_client.get_books_in_progress(min_listen_seconds)
            
            sync_logger.info(
                "Retrieved books in progress",
                count=len(books),
                min_listen_minutes=self.config.min_listen_minutes
            )
            
            result.books_processed = len(books)
            
            # Process each book
            for book in books:
                sync_result = self._sync_book(book, sync_logger)
                result.results.append(sync_result)
                
                if sync_result.success:
                    result.books_synced += 1
                elif sync_result.sg_error or sync_result.hc_error:
                    result.books_failed += 1
                else:
                    result.books_skipped += 1
            
            # Update sync run record
            with get_db_session() as session:
                sync_run = session.query(SyncRun).filter(
                    SyncRun.run_id == run_id
                ).first()
                
                if sync_run:
                    sync_run.completed_at = datetime.utcnow()
                    sync_run.status = "completed"
                    sync_run.books_processed = result.books_processed
                    sync_run.books_synced = result.books_synced
                    sync_run.books_skipped = result.books_skipped
                    sync_run.books_failed = result.books_failed
            
            sync_logger.info(
                "Sync run completed",
                run_id=run_id,
                processed=result.books_processed,
                synced=result.books_synced,
                skipped=result.books_skipped,
                failed=result.books_failed
            )
            
        except Exception as e:
            sync_logger.exception("Sync run failed", error=str(e))
            result.success = False
            result.error_message = str(e)
            
            # Update sync run record
            with get_db_session() as session:
                sync_run = session.query(SyncRun).filter(
                    SyncRun.run_id == run_id
                ).first()
                
                if sync_run:
                    sync_run.completed_at = datetime.utcnow()
                    sync_run.status = "failed"
                    sync_run.error_message = str(e)
        
        result.completed_at = datetime.utcnow()
        return result
    
    def _sync_book(
        self,
        book: AudiobookProgress,
        sync_logger: SyncLogger
    ) -> SyncResult:
        """
        Sync a single book.
        
        Args:
            book: AudiobookProgress to sync
            sync_logger: Logger for this sync run
            
        Returns:
            SyncResult with sync details
        """
        result = SyncResult(
            book_id=book.book_id,
            title=book.title,
            success=False,
            progress_percent=book.progress_percent,
        )
        
        sync_logger.debug(
            "Processing book",
            title=book.title,
            progress=book.progress_percent
        )
        
        # Match book with external services
        match = self.matcher.match_book(book)
        
        # Check if we have any matches
        if not match.storygraph_book_id and not match.hardcover_book_id:
            sync_logger.warning(
                "No match found for book",
                title=book.title,
                isbn=book.isbn,
                asin=book.asin
            )
            
            # Save to history
            self._save_sync_history(book, match, result)
            return result
        
        # Sync to StoryGraph
        if self.sg_client and match.storygraph_book_id:
            result.sg_success = self._sync_to_storygraph(
                match.storygraph_book_id,
                book.progress_percent,
                book.is_finished
            )
            if not result.sg_success:
                result.sg_error = "Failed to update progress"
        
        # Sync to Hardcover
        if self.hc_client and match.hardcover_book_id:
            result.hc_success = self._sync_to_hardcover(
                match.hardcover_book_id,
                match.hardcover_user_book_id,
                book.progress_percent,
                book.is_finished
            )
            if not result.hc_success:
                result.hc_error = "Failed to update progress"
        
        # Determine overall success
        result.success = result.sg_success or result.hc_success
        
        # Save to history
        self._save_sync_history(book, match, result)
        
        if result.success:
            sync_logger.info(
                "Synced book",
                title=book.title,
                progress=book.progress_percent,
                sg_success=result.sg_success,
                hc_success=result.hc_success
            )
        
        return result
    
    def _sync_to_storygraph(
        self,
        book_id: str,
        progress_percent: float,
        is_finished: bool
    ) -> bool:
        """
        Sync progress to StoryGraph.
        
        Args:
            book_id: StoryGraph book ID
            progress_percent: Progress percentage
            is_finished: Whether book is finished
            
        Returns:
            True if successful, False otherwise
        """
        try:
            progress = int(progress_percent)
            
            if is_finished:
                return self.sg_client.mark_as_finished(book_id)
            else:
                return self.sg_client.update_progress(book_id, progress)
                
        except Exception as e:
            logger.error(
                "Failed to sync to StoryGraph",
                book_id=book_id,
                error=str(e)
            )
            return False
    
    def _sync_to_hardcover(
        self,
        book_id: int,
        user_book_id: Optional[int],
        progress_percent: float,
        is_finished: bool
    ) -> bool:
        """
        Sync progress to Hardcover.
        
        Args:
            book_id: Hardcover book ID
            user_book_id: User book ID (if in library)
            progress_percent: Progress percentage
            is_finished: Whether book is finished
            
        Returns:
            True if successful, False otherwise
        """
        try:
            progress = int(progress_percent)
            
            # Determine status
            if is_finished:
                status = "finished"
            elif progress > 0:
                status = "currently_reading"
            else:
                status = None
            
            # If not in library, add it first
            if not user_book_id:
                user_book_id = self.hc_client.add_book_to_library(
                    book_id,
                    status or "currently_reading"
                )
                if not user_book_id:
                    logger.error(
                        "Failed to add book to Hardcover library",
                        book_id=book_id
                    )
                    return False
            
            # Update progress
            return self.hc_client.update_progress(
                user_book_id,
                progress,
                status
            )
            
        except Exception as e:
            logger.error(
                "Failed to sync to Hardcover",
                book_id=book_id,
                error=str(e)
            )
            return False
    
    def _save_sync_history(
        self,
        book: AudiobookProgress,
        match: BookMatch,
        result: SyncResult
    ) -> None:
        """
        Save sync result to history.
        
        Args:
            book: AudiobookProgress
            match: BookMatch
            result: SyncResult
        """
        try:
            with get_db_session() as session:
                history = SyncHistory(
                    abs_book_id=book.book_id,
                    book_title=book.title,
                    book_author=book.author,
                    isbn=book.isbn,
                    asin=book.asin,
                    progress_percent=book.progress_percent,
                    sg_book_id=match.storygraph_book_id,
                    hc_book_id=str(match.hardcover_book_id) if match.hardcover_book_id else None,
                    sg_status="success" if result.sg_success else ("failed" if result.sg_error else "skipped"),
                    hc_status="success" if result.hc_success else ("failed" if result.hc_error else "skipped"),
                    sg_error=result.sg_error,
                    hc_error=result.hc_error,
                )
                session.add(history)
                
        except Exception as e:
            logger.error(
                "Failed to save sync history",
                book_id=book.book_id,
                error=str(e)
            )
    
    def close(self) -> None:
        """Close all clients."""
        if self.abs_client:
            self.abs_client.close()
        if self.sg_client:
            self.sg_client.close()


def create_sync_engine_from_config() -> Optional[SyncEngine]:
    """
    Create a sync engine from the current configuration.
    
    Returns:
        SyncEngine if configured, None otherwise
    """
    from app.db.database import get_db_session
    
    # Get database session for ConfigManager using context manager
    with get_db_session() as db_session:
        config_manager = ConfigManager(db_session=db_session)
        config = config_manager.get_config()
        
        if not config_manager.is_configured():
            logger.warning("Sync engine not configured")
            return None
        
        engine = SyncEngine(config)
        if engine.initialize():
            return engine
        
        return None
