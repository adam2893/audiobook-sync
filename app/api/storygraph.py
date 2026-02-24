"""
StoryGraph API client for Audiobook Sync Service.

StoryGraph does not have an official API, so this client uses
web scraping based on the reverse-engineered API from:
https://github.com/ym496/storygraph-api

Note: This implementation may break if StoryGraph changes their site.
"""

from typing import Optional, List, Dict, Any
from dataclasses import dataclass
import re
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from app.api.base import APIError
from app.utils.logging import get_logger

logger = get_logger(__name__)

STORYGRAPH_BASE_URL = "https://app.thestorygraph.com"


@dataclass
class StoryGraphBook:
    """Represents a book in StoryGraph."""
    id: str
    title: str
    author: Optional[str]
    isbn: Optional[str]
    asin: Optional[str]
    status: Optional[str]
    progress: Optional[int]


class StoryGraphClient:
    """
    Client for StoryGraph (unofficial API via web scraping).
    
    Provides methods to authenticate, search for books, and update progress.
    Uses session-based authentication.
    """
    
    def __init__(self, email: str, password: str):
        """
        Initialize StoryGraph client.
        
        Args:
            email: StoryGraph email
            password: StoryGraph password
        """
        self.email = email
        self.password = password
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        self._authenticated = False
        self._csrf_token = None
    
    def _get_csrf_token(self, html: str) -> Optional[str]:
        """Extract CSRF token from HTML."""
        # Look for csrf-token in meta tag
        match = re.search(r'<meta name="csrf-token" content="([^"]+)"', html)
        if match:
            return match.group(1)
        
        # Look for authenticity_token in form
        match = re.search(r'name="authenticity_token" value="([^"]+)"', html)
        if match:
            return match.group(1)
        
        return None
    
    def _update_csrf_from_response(self, response: requests.Response) -> None:
        """Update CSRF token from response."""
        self._csrf_token = self._get_csrf_token(response.text)
        if self._csrf_token:
            self.session.headers.update({
                "X-CSRF-Token": self._csrf_token
            })
    
    def login(self) -> bool:
        """
        Authenticate with StoryGraph.
        
        Returns:
            True if login successful, False otherwise
        """
        try:
            # Get login page to extract CSRF token
            login_page = self.session.get(f"{STORYGRAPH_BASE_URL}/sign_in")
            self._update_csrf_from_response(login_page)
            
            # Parse form data
            soup = BeautifulSoup(login_page.text, 'html.parser')
            
            # Try multiple form detection strategies
            form = None
            
            # Strategy 1: Look for form with action containing sign_in
            form = soup.find('form', {'action': re.compile(r'sign_in')})
            
            # Strategy 2: Look for form with id or class containing sign_in or login
            if not form:
                form = soup.find('form', id=re.compile(r'(sign_in|login|session)', re.I))
            
            # Strategy 3: Look for any form with email and password fields
            if not form:
                for f in soup.find_all('form'):
                    email_field = f.find('input', {'name': re.compile(r'email', re.I)})
                    password_field = f.find('input', {'name': re.compile(r'password', re.I)})
                    if email_field and password_field:
                        form = f
                        break
            
            # Strategy 4: Look for form inside a div with session/sign_in class
            if not form:
                form_container = soup.find('div', class_=re.compile(r'(session|sign_in|login)', re.I))
                if form_container:
                    form = form_container.find('form')
            
            if not form:
                logger.error("Could not find login form")
                return False
            
            # Prepare login data - extract all hidden fields from form
            login_data = {}
            for input_elem in form.find_all('input'):
                name = input_elem.get('name')
                value = input_elem.get('value', '')
                if name:
                    login_data[name] = value
            
            # Override with credentials
            login_data["user[email]"] = self.email
            login_data["user[password]"] = self.password
            
            # Get form action
            action = form.get('action')
            if action:
                if action.startswith('/'):
                    submit_url = f"{STORYGRAPH_BASE_URL}{action}"
                elif action.startswith('http'):
                    submit_url = action
                else:
                    submit_url = f"{STORYGRAPH_BASE_URL}/sign_in"
            else:
                submit_url = f"{STORYGRAPH_BASE_URL}/sign_in"
            
            # Submit login form
            response = self.session.post(
                submit_url,
                data=login_data,
                allow_redirects=True
            )
            
            # Check if login successful
            if response.status_code == 200 and "sign_in" not in response.url:
                self._authenticated = True
                self._update_csrf_from_response(response)
                logger.info("Successfully logged into StoryGraph")
                return True
            
            logger.error(
                "StoryGraph login failed",
                status_code=response.status_code,
                url=response.url
            )
            return False
            
        except Exception as e:
            logger.error("StoryGraph login error", error=str(e))
            return False
    
    def test_connection(self) -> bool:
        """
        Test connection to StoryGraph.
        
        Returns:
            True if connection successful, False otherwise
        """
        if not self._authenticated:
            return self.login()
        return self._authenticated
    
    def search_by_isbn(self, isbn: str) -> Optional[StoryGraphBook]:
        """
        Search for a book by ISBN.
        
        Args:
            isbn: ISBN to search for
            
        Returns:
            StoryGraphBook if found, None otherwise
        """
        try:
            # Search for book
            search_url = f"{STORYGRAPH_BASE_URL}/books"
            params = {"q": isbn}
            
            response = self.session.get(search_url, params=params)
            
            if response.status_code != 200:
                return None
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find first book result
            book_link = soup.find('a', href=re.compile(r'/books/\d+'))
            
            if not book_link:
                return None
            
            # Extract book ID from URL
            href = book_link.get('href', '')
            match = re.search(r'/books/(\d+)', href)
            
            if not match:
                return None
            
            book_id = match.group(1)
            
            # Get book details
            return self.get_book(book_id)
            
        except Exception as e:
            logger.error("Failed to search by ISBN", isbn=isbn, error=str(e))
            return None
    
    def search_by_asin(self, asin: str) -> Optional[StoryGraphBook]:
        """
        Search for a book by ASIN.
        
        Args:
            asin: ASIN to search for
            
        Returns:
            StoryGraphBook if found, None otherwise
        """
        # StoryGraph doesn't directly support ASIN search
        # Try searching by ASIN as a general query
        return self.search_by_title_author(asin)
    
    def search_by_title_author(
        self,
        title: str,
        author: Optional[str] = None
    ) -> Optional[StoryGraphBook]:
        """
        Search for a book by title and optionally author.
        
        Args:
            title: Book title
            author: Author name (optional)
            
        Returns:
            StoryGraphBook if found, None otherwise
        """
        try:
            # Build search query
            query = title
            if author:
                query = f"{title} {author}"
            
            search_url = f"{STORYGRAPH_BASE_URL}/books"
            params = {"q": query}
            
            response = self.session.get(search_url, params=params)
            
            if response.status_code != 200:
                return None
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find book results
            book_links = soup.find_all('a', href=re.compile(r'/books/\d+'))
            
            if not book_links:
                return None
            
            # Get first book
            book_link = book_links[0]
            href = book_link.get('href', '')
            match = re.search(r'/books/(\d+)', href)
            
            if not match:
                return None
            
            book_id = match.group(1)
            return self.get_book(book_id)
            
        except Exception as e:
            logger.error(
                "Failed to search by title/author",
                title=title,
                author=author,
                error=str(e)
            )
            return None
    
    def get_book(self, book_id: str) -> Optional[StoryGraphBook]:
        """
        Get book details by ID.
        
        Args:
            book_id: StoryGraph book ID
            
        Returns:
            StoryGraphBook if found, None otherwise
        """
        try:
            response = self.session.get(f"{STORYGRAPH_BASE_URL}/books/{book_id}")
            
            if response.status_code != 200:
                return None
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract title
            title_elem = soup.find('h1') or soup.find('h2', class_='book-title')
            title = title_elem.get_text(strip=True) if title_elem else "Unknown"
            
            # Extract author
            author_elem = soup.find('a', href=re.compile(r'/authors/'))
            author = author_elem.get_text(strip=True) if author_elem else None
            
            # Extract ISBN
            isbn = None
            isbn_elem = soup.find(string=re.compile(r'ISBN'))
            if isbn_elem:
                isbn_match = re.search(r'(\d{10}|\d{13})', isbn_elem)
                if isbn_match:
                    isbn = isbn_match.group(1)
            
            return StoryGraphBook(
                id=book_id,
                title=title,
                author=author,
                isbn=isbn,
                asin=None,  # StoryGraph doesn't expose ASIN
                status=None,
                progress=None,
            )
            
        except Exception as e:
            logger.error("Failed to get book", book_id=book_id, error=str(e))
            return None
    
    def get_currently_reading(self) -> List[StoryGraphBook]:
        """
        Get books currently being read.
        
        Returns:
            List of StoryGraphBook objects
        """
        try:
            response = self.session.get(f"{STORYGRAPH_BASE_URL}/currently-reading")
            
            if response.status_code != 200:
                return []
            
            soup = BeautifulSoup(response.text, 'html.parser')
            books = []
            
            # Find book entries
            book_entries = soup.find_all('div', class_=re.compile(r'book'))
            
            for entry in book_entries:
                book_link = entry.find('a', href=re.compile(r'/books/\d+'))
                if not book_link:
                    continue
                
                href = book_link.get('href', '')
                match = re.search(r'/books/(\d+)', href)
                
                if not match:
                    continue
                
                book_id = match.group(1)
                title = book_link.get_text(strip=True)
                
                # Try to find progress
                progress_elem = entry.find(string=re.compile(r'\d+%\s*complete'))
                progress = None
                if progress_elem:
                    progress_match = re.search(r'(\d+)%', progress_elem)
                    if progress_match:
                        progress = int(progress_match.group(1))
                
                books.append(StoryGraphBook(
                    id=book_id,
                    title=title,
                    author=None,
                    isbn=None,
                    asin=None,
                    status="currently_reading",
                    progress=progress,
                ))
            
            return books
            
        except Exception as e:
            logger.error("Failed to get currently reading", error=str(e))
            return []
    
    def find_book_in_library(
        self,
        isbn: Optional[str] = None,
        asin: Optional[str] = None,
        title: Optional[str] = None,
        author: Optional[str] = None,
    ) -> Optional[StoryGraphBook]:
        """
        Find a book in user's library.
        
        Args:
            isbn: ISBN to search
            asin: ASIN to search
            title: Title to search
            author: Author to search
            
        Returns:
            StoryGraphBook if found, None otherwise
        """
        # Try ISBN first
        if isbn:
            book = self.search_by_isbn(isbn)
            if book:
                return book
        
        # Try title/author
        if title:
            book = self.search_by_title_author(title, author)
            if book:
                return book
        
        return None
    
    def update_progress(
        self,
        book_id: str,
        progress_percent: int,
        status: Optional[str] = None
    ) -> bool:
        """
        Update reading progress for a book.
        
        Args:
            book_id: StoryGraph book ID
            progress_percent: Progress percentage (0-100)
            status: Reading status (optional)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Get book page to find form
            response = self.session.get(f"{STORYGRAPH_BASE_URL}/books/{book_id}")
            
            if response.status_code != 200:
                logger.error("Failed to get book page for progress update", book_id=book_id)
                return False
            
            self._update_csrf_from_response(response)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find the progress update form
            # StoryGraph uses various forms for updating progress
            # This is a simplified implementation
            
            # Look for "Add to currently reading" or progress form
            form = soup.find('form', {'action': re.compile(r'progress|reading|status')})
            
            if not form:
                # Try to add to currently reading first
                return self._add_to_currently_reading(book_id, progress_percent)
            
            # Extract form action and inputs
            action = form.get('action', '')
            if not action.startswith('http'):
                action = urljoin(STORYGRAPH_BASE_URL, action)
            
            form_data = {}
            for input_elem in form.find_all('input'):
                name = input_elem.get('name')
                value = input_elem.get('value', '')
                if name:
                    form_data[name] = value
            
            # Update progress
            form_data['progress'] = progress_percent
            if status:
                form_data['status'] = status
            
            # Submit form
            submit_response = self.session.post(action, data=form_data)
            
            return submit_response.status_code in [200, 302]
            
        except Exception as e:
            logger.error(
                "Failed to update progress",
                book_id=book_id,
                progress=progress_percent,
                error=str(e)
            )
            return False
    
    def _add_to_currently_reading(self, book_id: str, progress: int = 0) -> bool:
        """
        Add a book to currently reading list.
        
        Args:
            book_id: StoryGraph book ID
            progress: Initial progress
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # This is a simplified implementation
            # The actual StoryGraph UI may require different endpoints
            
            response = self.session.post(
                f"{STORYGRAPH_BASE_URL}/books/{book_id}/read_statuses",
                json={
                    "status": "currently_reading",
                    "progress": progress,
                },
                headers={
                    "Content-Type": "application/json",
                    "X-CSRF-Token": self._csrf_token or "",
                }
            )
            
            return response.status_code in [200, 201, 302]
            
        except Exception as e:
            logger.error(
                "Failed to add to currently reading",
                book_id=book_id,
                error=str(e)
            )
            return False
    
    def mark_as_finished(self, book_id: str) -> bool:
        """
        Mark a book as finished.
        
        Args:
            book_id: StoryGraph book ID
            
        Returns:
            True if successful, False otherwise
        """
        return self.update_progress(book_id, 100, "finished")
    
    def close(self) -> None:
        """Close the session."""
        self.session.close()
