"""
Audiobookshelf API client for Audiobook Sync Service.

Documentation: https://www.audiobookshelf.org/docs/
"""

from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from datetime import datetime

from app.api.base import BaseClient, APIError
from app.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class AudiobookProgress:
    """Represents listening progress for an audiobook."""
    book_id: str
    title: str
    author: Optional[str]
    isbn: Optional[str]
    asin: Optional[str]
    duration_seconds: int
    current_time_seconds: float
    progress_percent: float
    is_finished: bool
    last_update: Optional[datetime]
    
    @property
    def listened_minutes(self) -> float:
        """Return listened time in minutes."""
        return self.current_time_seconds / 60


class AudiobookshelfClient(BaseClient):
    """
    Client for Audiobookshelf API.
    
    Provides methods to interact with Audiobookshelf server
    to retrieve audiobook progress information.
    """
    
    def __init__(self, base_url: str, token: str):
        """
        Initialize Audiobookshelf client.
        
        Args:
            base_url: Audiobookshelf server URL (e.g., http://localhost:13378)
            token: API token for authentication
        """
        super().__init__(base_url)
        self.token = token
        
        # Set default authorization header
        self.session.headers.update({
            "Authorization": f"Bearer {token}"
        })
    
    def test_connection(self) -> bool:
        """
        Test connection to Audiobookshelf server.
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            # Use /api/libraries endpoint which is available in Audiobookshelf
            response = self.get("/api/libraries")
            return "libraries" in response or isinstance(response, list)
        except APIError as e:
            logger.error("Failed to connect to Audiobookshelf", error=str(e))
            return False
    
    def get_libraries(self) -> List[Dict[str, Any]]:
        """
        Get all libraries from Audiobookshelf.
        
        Returns:
            List of library objects
        """
        response = self.get("/api/libraries")
        return response.get("libraries", [])
    
    def get_library_items(
        self,
        library_id: str,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Get items from a specific library.
        
        Args:
            library_id: Library ID
            limit: Maximum number of items to return
            
        Returns:
            List of library items
        """
        params = {}
        if limit:
            params["limit"] = limit
            
        response = self.get(f"/api/libraries/{library_id}/items", params=params)
        return response.get("results", [])
    
    def get_items_in_progress(self) -> List[Dict[str, Any]]:
        """
        Get all items currently in progress.
        
        Returns:
            List of items with progress information
        """
        response = self.get("/api/me/items-in-progress")
        return response.get("libraryItems", [])
    
    def get_item(self, item_id: str) -> Dict[str, Any]:
        """
        Get details for a specific item.
        
        Args:
            item_id: Item ID
            
        Returns:
            Item details
        """
        return self.get(f"/api/items/{item_id}")
    
    def get_user_progress(self, item_id: str) -> Optional[Dict[str, Any]]:
        """
        Get user's progress for a specific item.
        
        Args:
            item_id: Item ID
            
        Returns:
            Progress information or None
        """
        try:
            return self.get(f"/api/me/progress/{item_id}")
        except APIError as e:
            if e.status_code == 404:
                return None
            raise
    
    def parse_progress(self, item: Dict[str, Any]) -> Optional[AudiobookProgress]:
        """
        Parse an Audiobookshelf item into AudiobookProgress.
        
        Args:
            item: Raw item data from Audiobookshelf
            
        Returns:
            AudiobookProgress object or None if invalid
        """
        try:
            media = item.get("media", {})
            metadata = media.get("metadata", {})
            progress = item.get("progress", {})
            
            if not progress:
                return None
            
            # Get duration from media
            duration = media.get("duration", 0)
            if not duration:
                # Try to get from tracks
                tracks = media.get("tracks", [])
                duration = sum(t.get("duration", 0) for t in tracks)
            
            current_time = progress.get("currentTime", 0)
            
            # Calculate progress percentage
            if duration > 0:
                progress_percent = (current_time / duration) * 100
            else:
                progress_percent = 0
            
            # Parse last update timestamp
            last_update = None
            if progress.get("lastUpdate"):
                last_update = datetime.fromtimestamp(
                    progress["lastUpdate"] / 1000
                )
            
            return AudiobookProgress(
                book_id=item.get("id", ""),
                title=metadata.get("title", "Unknown"),
                author=metadata.get("authorName"),
                isbn=metadata.get("isbn"),
                asin=metadata.get("asin"),
                duration_seconds=duration,
                current_time_seconds=current_time,
                progress_percent=progress_percent,
                is_finished=progress.get("isFinished", False),
                last_update=last_update,
            )
            
        except Exception as e:
            logger.error(
                "Failed to parse audiobook progress",
                item_id=item.get("id"),
                error=str(e)
            )
            return None
    
    def get_books_in_progress(
        self,
        min_listen_seconds: int = 600
    ) -> List[AudiobookProgress]:
        """
        Get all books currently in progress with minimum listen time.
        
        Args:
            min_listen_seconds: Minimum listen time in seconds
            
        Returns:
            List of AudiobookProgress objects
        """
        items = self.get_items_in_progress()
        books = []
        
        for item in items:
            progress = self.parse_progress(item)
            
            if progress is None:
                continue
            
            # Filter by minimum listen time
            if progress.current_time_seconds < min_listen_seconds:
                logger.debug(
                    "Skipping book - below minimum listen time",
                    title=progress.title,
                    listened_minutes=progress.listened_minutes
                )
                continue
            
            books.append(progress)
        
        logger.info(
            "Retrieved books in progress",
            total=len(items),
            filtered=len(books),
            min_listen_minutes=min_listen_seconds / 60
        )
        
        return books
    
    def get_all_books_with_progress(
        self,
        min_listen_seconds: int = 600
    ) -> List[AudiobookProgress]:
        """
        Get all books that have any progress.
        
        This includes books that may not be "in progress" anymore
        but have listening history.
        
        Args:
            min_listen_seconds: Minimum listen time in seconds
            
        Returns:
            List of AudiobookProgress objects
        """
        # Get all libraries
        libraries = self.get_libraries()
        books = []
        seen_ids = set()
        
        for library in libraries:
            library_id = library.get("id")
            library_type = library.get("mediaType", "")
            
            # Only process audiobook libraries
            if library_type != "book":
                continue
            
            # Get items from library
            items = self.get_library_items(library_id)
            
            for item in items:
                item_id = item.get("id")
                
                # Skip duplicates
                if item_id in seen_ids:
                    continue
                seen_ids.add(item_id)
                
                # Get progress for this item
                progress_data = self.get_user_progress(item_id)
                
                if not progress_data:
                    continue
                
                # Add progress to item
                item["progress"] = progress_data
                
                # Parse progress
                progress = self.parse_progress(item)
                
                if progress is None:
                    continue
                
                # Filter by minimum listen time
                if progress.current_time_seconds < min_listen_seconds:
                    continue
                
                books.append(progress)
        
        logger.info(
            "Retrieved all books with progress",
            total_books=len(books),
            min_listen_minutes=min_listen_seconds / 60
        )
        
        return books
