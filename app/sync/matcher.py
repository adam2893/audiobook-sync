"""
Book matching logic for Audiobook Sync Service.

Handles matching books between Audiobookshelf and external services
using ISBN, ASIN, and title/author combinations.
"""

from typing import Optional, Tuple
from datetime import datetime

from app.api.audiobookshelf import AudiobookProgress
from app.api.hardcover import HardcoverClient, HardcoverBook
from app.api.storygraph import StoryGraphClient, StoryGraphBook
from app.db.database import get_db_session
from app.db.models import BookMapping
from app.sync.models import BookMatch
from app.utils.logging import get_logger

logger = get_logger(__name__)


class BookMatcher:
    """
    Matches books between Audiobookshelf and external services.
    
    Matching priority:
    1. Cached mapping in database
    2. ISBN match
    3. ASIN match
    4. Title + Author match (fuzzy)
    """
    
    def __init__(
        self,
        hardcover_client: Optional[HardcoverClient] = None,
        storygraph_client: Optional[StoryGraphClient] = None,
    ):
        self.hardcover_client = hardcover_client
        self.storygraph_client = storygraph_client
    
    def get_cached_mapping(self, abs_book_id: str) -> Optional[BookMapping]:
        """
        Get cached book mapping from database.
        
        Args:
            abs_book_id: Audiobookshelf book ID
            
        Returns:
            BookMapping if found, None otherwise
        """
        try:
            with get_db_session() as session:
                return session.query(BookMapping).filter(
                    BookMapping.abs_book_id == abs_book_id
                ).first()
        except Exception as e:
            logger.error(
                "Failed to get cached mapping",
                abs_book_id=abs_book_id,
                error=str(e)
            )
            return None
    
    def save_mapping(self, match: BookMatch) -> None:
        """
        Save book mapping to database.
        
        Args:
            match: BookMatch object to save
        """
        try:
            with get_db_session() as session:
                # Check for existing mapping
                existing = session.query(BookMapping).filter(
                    BookMapping.abs_book_id == match.abs_book_id
                ).first()
                
                if existing:
                    # Update existing
                    existing.sg_book_id = match.storygraph_book_id
                    existing.hc_book_id = str(match.hardcover_book_id) if match.hardcover_book_id else None
                    existing.isbn = match.isbn
                    existing.asin = match.asin
                    existing.title = match.title
                    existing.author = match.author
                    existing.last_matched = datetime.utcnow()
                    existing.match_confidence = match.match_confidence
                else:
                    # Create new
                    mapping = BookMapping(
                        abs_book_id=match.abs_book_id,
                        sg_book_id=match.storygraph_book_id,
                        hc_book_id=str(match.hardcover_book_id) if match.hardcover_book_id else None,
                        isbn=match.isbn,
                        asin=match.asin,
                        title=match.title,
                        author=match.author,
                        match_confidence=match.match_confidence,
                    )
                    session.add(mapping)
                    
        except Exception as e:
            logger.error(
                "Failed to save mapping",
                abs_book_id=match.abs_book_id,
                error=str(e)
            )
    
    def match_book(
        self,
        book: AudiobookProgress,
        use_cache: bool = True
    ) -> BookMatch:
        """
        Match an Audiobookshelf book to external services.
        
        Args:
            book: AudiobookProgress from Audiobookshelf
            use_cache: Whether to use cached mappings
            
        Returns:
            BookMatch with external service IDs
        """
        match = BookMatch(
            abs_book_id=book.book_id,
            title=book.title,
            author=book.author,
            isbn=book.isbn,
            asin=book.asin,
        )
        
        # Check cache first
        if use_cache:
            cached = self.get_cached_mapping(book.book_id)
            if cached:
                match.storygraph_book_id = cached.sg_book_id
                match.hardcover_book_id = int(cached.hc_book_id) if cached.hc_book_id else None
                match.match_confidence = cached.match_confidence
                match.match_method = "cache"
                
                logger.debug(
                    "Using cached mapping",
                    title=book.title,
                    sg_id=cached.sg_book_id,
                    hc_id=cached.hc_book_id
                )
                
                return match
        
        # Match with external services
        sg_book = None
        hc_book = None
        
        # Try StoryGraph matching
        if self.storygraph_client:
            sg_book = self._match_storygraph(book)
            if sg_book:
                match.storygraph_book_id = sg_book.id
                match.match_method = "storygraph"
        
        # Try Hardcover matching
        if self.hardcover_client:
            hc_book = self._match_hardcover(book)
            if hc_book:
                match.hardcover_book_id = hc_book.id
                match.hardcover_user_book_id = hc_book.user_book_id
                if not match.match_method:
                    match.match_method = "hardcover"
        
        # Calculate match confidence
        match.match_confidence = self._calculate_confidence(
            book, sg_book, hc_book
        )
        
        # Save mapping if we found any matches
        if match.storygraph_book_id or match.hardcover_book_id:
            self.save_mapping(match)
        
        return match
    
    def _match_storygraph(
        self,
        book: AudiobookProgress
    ) -> Optional[StoryGraphBook]:
        """
        Match book with StoryGraph.
        
        Args:
            book: AudiobookProgress to match
            
        Returns:
            StoryGraphBook if found, None otherwise
        """
        # Try ISBN first
        if book.isbn:
            sg_book = self.storygraph_client.search_by_isbn(book.isbn)
            if sg_book:
                logger.debug(
                    "Matched by ISBN in StoryGraph",
                    title=book.title,
                    isbn=book.isbn
                )
                return sg_book
        
        # Try ASIN
        if book.asin:
            sg_book = self.storygraph_client.search_by_asin(book.asin)
            if sg_book:
                logger.debug(
                    "Matched by ASIN in StoryGraph",
                    title=book.title,
                    asin=book.asin
                )
                return sg_book
        
        # Try title/author
        sg_book = self.storygraph_client.search_by_title_author(
            book.title,
            book.author
        )
        if sg_book:
            logger.debug(
                "Matched by title/author in StoryGraph",
                title=book.title,
                author=book.author
            )
            return sg_book
        
        logger.debug(
            "No match found in StoryGraph",
            title=book.title
        )
        return None
    
    def _match_hardcover(
        self,
        book: AudiobookProgress
    ) -> Optional[HardcoverBook]:
        """
        Match book with Hardcover.
        
        Args:
            book: AudiobookProgress to match
            
        Returns:
            HardcoverBook if found, None otherwise
        """
        # First check if book is already in user's library
        hc_book = self.hardcover_client.find_book_in_library(
            isbn=book.isbn,
            asin=book.asin,
            title=book.title,
            author=book.author,
        )
        
        if hc_book:
            logger.debug(
                "Found book in Hardcover library",
                title=book.title,
                hc_id=hc_book.id
            )
            return hc_book
        
        # Search for book in Hardcover database
        # Try ISBN first
        if book.isbn:
            hc_book = self.hardcover_client.search_by_isbn(book.isbn)
            if hc_book:
                logger.debug(
                    "Matched by ISBN in Hardcover",
                    title=book.title,
                    isbn=book.isbn
                )
                return hc_book
        
        # Try ASIN
        if book.asin:
            hc_book = self.hardcover_client.search_by_asin(book.asin)
            if hc_book:
                logger.debug(
                    "Matched by ASIN in Hardcover",
                    title=book.title,
                    asin=book.asin
                )
                return hc_book
        
        # Try title/author
        hc_book = self.hardcover_client.search_by_title_author(
            book.title,
            book.author
        )
        if hc_book:
            logger.debug(
                "Matched by title/author in Hardcover",
                title=book.title,
                author=book.author
            )
            return hc_book
        
        logger.debug(
            "No match found in Hardcover",
            title=book.title
        )
        return None
    
    def _calculate_confidence(
        self,
        book: AudiobookProgress,
        sg_book: Optional[StoryGraphBook],
        hc_book: Optional[HardcoverBook],
    ) -> float:
        """
        Calculate match confidence score.
        
        Args:
            book: Original AudiobookProgress
            sg_book: Matched StoryGraph book
            hc_book: Matched Hardcover book
            
        Returns:
            Confidence score (0.0 to 1.0)
        """
        confidence = 0.0
        
        # ISBN match is highest confidence
        if book.isbn:
            if sg_book and sg_book.isbn == book.isbn:
                confidence = max(confidence, 0.95)
            if hc_book and hc_book.isbn == book.isbn:
                confidence = max(confidence, 0.95)
        
        # ASIN match is also high confidence
        if book.asin:
            if sg_book and sg_book.asin == book.asin:
                confidence = max(confidence, 0.9)
            if hc_book and hc_book.asin == book.asin:
                confidence = max(confidence, 0.9)
        
        # Title/author match is lower confidence
        if confidence == 0.0:
            if sg_book or hc_book:
                confidence = 0.7
        
        return confidence
