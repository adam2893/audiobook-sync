"""
Hardcover API client for Audiobook Sync Service.

Documentation: https://hardcover.app/api
Hardcover uses a GraphQL API.
"""

from typing import Optional, List, Dict, Any
from dataclasses import dataclass
import requests
from gql import gql, Client
from gql.transport.requests import RequestsHTTPTransport

from app.api.base import APIError
from app.utils.logging import get_logger

logger = get_logger(__name__)

HARDCOVER_API_URL = "https://api.hardcover.app/v1/graphql"


@dataclass
class HardcoverBook:
    """Represents a book in Hardcover."""
    id: int
    user_book_id: int
    title: str
    author: Optional[str]
    isbn: Optional[str]
    asin: Optional[str]
    status: Optional[str]
    progress: Optional[int]


class HardcoverClient:
    """
    Client for Hardcover GraphQL API.
    
    Provides methods to search for books and update reading progress.
    """
    
    def __init__(self, api_key: str):
        """
        Initialize Hardcover client.
        
        Args:
            api_key: Hardcover API key
        """
        self.api_key = api_key
        self._client = None
    
    @property
    def client(self) -> Client:
        """Get or create GraphQL client."""
        if self._client is None:
            transport = RequestsHTTPTransport(
                url=HARDCOVER_API_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=30,
            )
            self._client = Client(transport=transport, fetch_schema_from_transport=False)
        return self._client
    
    def test_connection(self) -> bool:
        """
        Test connection to Hardcover API.
        
        Returns:
            True if connection successful, False otherwise
        """
        query = gql("""
            query TestConnection {
                me {
                    id
                }
            }
        """)
        
        try:
            result = self.client.execute(query)
            return "me" in result and result["me"] is not None
        except Exception as e:
            logger.error("Failed to connect to Hardcover", error=str(e))
            return False
    
    def search_by_isbn(self, isbn: str) -> Optional[HardcoverBook]:
        """
        Search for a book by ISBN.
        
        Args:
            isbn: ISBN to search for
            
        Returns:
            HardcoverBook if found, None otherwise
        """
        query = gql("""
            query SearchByISBN($isbn: String!) {
                books(where: {
                    _or: [
                        {isbn_10: {_eq: $isbn}},
                        {isbn_13: {_eq: $isbn}}
                    ]
                }) {
                    id
                    title
                    isbn_10
                    isbn_13
                    asin
                    contributions {
                        author {
                            name
                        }
                    }
                }
            }
        """)
        
        try:
            result = self.client.execute(query, variable_values={"isbn": isbn})
            books = result.get("books", [])
            
            if not books:
                return None
            
            book = books[0]
            author = None
            if book.get("contributions"):
                author = book["contributions"][0].get("author", {}).get("name")
            
            return HardcoverBook(
                id=book["id"],
                user_book_id=0,  # Will be set when we get user books
                title=book.get("title", ""),
                author=author,
                isbn=book.get("isbn_10") or book.get("isbn_13"),
                asin=book.get("asin"),
                status=None,
                progress=None,
            )
            
        except Exception as e:
            logger.error("Failed to search by ISBN", isbn=isbn, error=str(e))
            return None
    
    def search_by_asin(self, asin: str) -> Optional[HardcoverBook]:
        """
        Search for a book by ASIN (Audible ID).
        
        Args:
            asin: ASIN to search for
            
        Returns:
            HardcoverBook if found, None otherwise
        """
        query = gql("""
            query SearchByASIN($asin: String!) {
                books(where: {asin: {_eq: $asin}}) {
                    id
                    title
                    isbn_10
                    isbn_13
                    asin
                    contributions {
                        author {
                            name
                        }
                    }
                }
            }
        """)
        
        try:
            result = self.client.execute(query, variable_values={"asin": asin})
            books = result.get("books", [])
            
            if not books:
                return None
            
            book = books[0]
            author = None
            if book.get("contributions"):
                author = book["contributions"][0].get("author", {}).get("name")
            
            return HardcoverBook(
                id=book["id"],
                user_book_id=0,
                title=book.get("title", ""),
                author=author,
                isbn=book.get("isbn_10") or book.get("isbn_13"),
                asin=book.get("asin"),
                status=None,
                progress=None,
            )
            
        except Exception as e:
            logger.error("Failed to search by ASIN", asin=asin, error=str(e))
            return None
    
    def search_by_title_author(
        self,
        title: str,
        author: Optional[str] = None
    ) -> Optional[HardcoverBook]:
        """
        Search for a book by title and optionally author.
        
        Args:
            title: Book title
            author: Author name (optional)
            
        Returns:
            HardcoverBook if found, None otherwise
        """
        query = gql("""
            query SearchByTitle($title: String!, $author: String) {
                books(
                    where: {
                        title: {_ilike: $title}
                    }
                    limit: 5
                ) {
                    id
                    title
                    isbn_10
                    isbn_13
                    asin
                    contributions {
                        author {
                            name
                        }
                    }
                }
            }
        """)
        
        try:
            # Use fuzzy matching for title
            search_title = f"%{title}%"
            result = self.client.execute(
                query,
                variable_values={"title": search_title}
            )
            books = result.get("books", [])
            
            if not books:
                return None
            
            # If author provided, try to match
            if author:
                author_lower = author.lower()
                for book in books:
                    if book.get("contributions"):
                        book_author = book["contributions"][0].get("author", {}).get("name", "")
                        if author_lower in book_author.lower():
                            return HardcoverBook(
                                id=book["id"],
                                user_book_id=0,
                                title=book.get("title", ""),
                                author=book_author,
                                isbn=book.get("isbn_10") or book.get("isbn_13"),
                                asin=book.get("asin"),
                                status=None,
                                progress=None,
                            )
            
            # Return first result if no author match
            book = books[0]
            book_author = None
            if book.get("contributions"):
                book_author = book["contributions"][0].get("author", {}).get("name")
            
            return HardcoverBook(
                id=book["id"],
                user_book_id=0,
                title=book.get("title", ""),
                author=book_author,
                isbn=book.get("isbn_10") or book.get("isbn_13"),
                asin=book.get("asin"),
                status=None,
                progress=None,
            )
            
        except Exception as e:
            logger.error(
                "Failed to search by title/author",
                title=title,
                author=author,
                error=str(e)
            )
            return None
    
    def get_user_books(self) -> List[HardcoverBook]:
        """
        Get all books in user's library.
        
        Returns:
            List of HardcoverBook objects
        """
        query = gql("""
            query GetUserBooks {
                me {
                    user_books {
                        id
                        book_id
                        status_id
                        progress
                        book {
                            id
                            title
                            isbn_10
                            isbn_13
                            asin
                            contributions {
                                author {
                                    name
                                }
                            }
                        }
                    }
                }
            }
        """)
        
        try:
            result = self.client.execute(query)
            me = result.get("me", [])
            
            if not me:
                return []
            
            user_books = me[0].get("user_books", [])
            books = []
            
            # Status mapping
            status_map = {
                1: "want_to_read",
                2: "currently_reading",
                3: "finished",
                4: "did_not_finish",
            }
            
            for ub in user_books:
                book = ub.get("book", {})
                author = None
                if book.get("contributions"):
                    author = book["contributions"][0].get("author", {}).get("name")
                
                status_id = ub.get("status_id")
                status = status_map.get(status_id) if status_id else None
                
                books.append(HardcoverBook(
                    id=book.get("id", 0),
                    user_book_id=ub.get("id", 0),
                    title=book.get("title", ""),
                    author=author,
                    isbn=book.get("isbn_10") or book.get("isbn_13"),
                    asin=book.get("asin"),
                    status=status,
                    progress=ub.get("progress"),
                ))
            
            return books
            
        except Exception as e:
            logger.error("Failed to get user books", error=str(e))
            return []
    
    def find_book_in_library(
        self,
        isbn: Optional[str] = None,
        asin: Optional[str] = None,
        title: Optional[str] = None,
        author: Optional[str] = None,
    ) -> Optional[HardcoverBook]:
        """
        Find a book in user's library by ISBN, ASIN, or title/author.
        
        Args:
            isbn: ISBN to search
            asin: ASIN to search
            title: Title to search
            author: Author to search
            
        Returns:
            HardcoverBook if found, None otherwise
        """
        user_books = self.get_user_books()
        
        # Try ISBN match first
        if isbn:
            for book in user_books:
                if book.isbn and book.isbn == isbn:
                    return book
        
        # Try ASIN match
        if asin:
            for book in user_books:
                if book.asin and book.asin == asin:
                    return book
        
        # Try title/author match
        if title:
            title_lower = title.lower()
            for book in user_books:
                if title_lower in book.title.lower():
                    if author and book.author:
                        if author.lower() in book.author.lower():
                            return book
                    else:
                        return book
        
        return None
    
    def update_progress(
        self,
        user_book_id: int,
        progress_percent: int,
        status: Optional[str] = None
    ) -> bool:
        """
        Update reading progress for a book.
        
        Args:
            user_book_id: User book ID
            progress_percent: Progress percentage (0-100)
            status: Reading status (optional)
            
        Returns:
            True if successful, False otherwise
        """
        # Status ID mapping
        status_id_map = {
            "want_to_read": 1,
            "currently_reading": 2,
            "finished": 3,
            "did_not_finish": 4,
        }
        
        mutation = gql("""
            mutation UpdateProgress($id: Int!, $progress: Int, $status_id: Int) {
                update_user_book(
                    where: {id: {_eq: $id}}
                    _set: {
                        progress: $progress
                        status_id: $status_id
                    }
                ) {
                    affected_rows
                }
            }
        """)
        
        try:
            variables = {
                "id": user_book_id,
                "progress": progress_percent,
            }
            
            if status and status in status_id_map:
                variables["status_id"] = status_id_map[status]
            elif progress_percent >= 100:
                variables["status_id"] = 3  # finished
            elif progress_percent > 0:
                variables["status_id"] = 2  # currently_reading
            
            result = self.client.execute(mutation, variable_values=variables)
            affected = result.get("update_user_book", {}).get("affected_rows", 0)
            
            return affected > 0
            
        except Exception as e:
            logger.error(
                "Failed to update progress",
                user_book_id=user_book_id,
                progress=progress_percent,
                error=str(e)
            )
            return False
    
    def add_book_to_library(
        self,
        book_id: int,
        status: str = "currently_reading"
    ) -> Optional[int]:
        """
        Add a book to user's library.
        
        Args:
            book_id: Book ID
            status: Initial reading status
            
        Returns:
            User book ID if successful, None otherwise
        """
        status_id_map = {
            "want_to_read": 1,
            "currently_reading": 2,
            "finished": 3,
        }
        
        mutation = gql("""
            mutation AddBookToLibrary($book_id: Int!, $status_id: Int!) {
                insert_user_book_one(
                    object: {
                        book_id: $book_id
                        status_id: $status_id
                    }
                ) {
                    id
                }
            }
        """)
        
        try:
            status_id = status_id_map.get(status, 2)  # Default to currently_reading
            
            result = self.client.execute(
                mutation,
                variable_values={
                    "book_id": book_id,
                    "status_id": status_id,
                }
            )
            
            return result.get("insert_user_book_one", {}).get("id")
            
        except Exception as e:
            logger.error(
                "Failed to add book to library",
                book_id=book_id,
                error=str(e)
            )
            return None
