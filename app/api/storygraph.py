"""
StoryGraph API client for Audiobook Sync Service.

StoryGraph does not have an official API, so this client uses
web scraping with Selenium based on the approach from:
https://github.com/ym496/storygraph-api

Note: This implementation may break if StoryGraph changes their site.
"""

from typing import Optional, List, Dict, Any
from dataclasses import dataclass
import re
import time
import os

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager

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
    Client for StoryGraph (unofficial API via web scraping with Selenium).
    
    Provides methods to authenticate using cookie, search for books, and update progress.
    Uses cookie-based authentication - users must extract the remember_user_token cookie
    from their browser after logging in.
    """
    
    def __init__(self, cookie: str, username: Optional[str] = None):
        """
        Initialize StoryGraph client.
        
        Args:
            cookie: The remember_user_token cookie value from browser
            username: StoryGraph username (optional, used for user-specific pages)
        """
        self.cookie = cookie
        self.username = username
        self._authenticated = False
        self._driver = None
    
    def _get_driver(self) -> webdriver.Chrome:
        """
        Get or create a Selenium WebDriver instance.
        
        Returns:
            Chrome WebDriver instance
        """
        if self._driver is None:
            options = Options()
            options.add_argument("--headless")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu")
            options.add_argument("--window-size=1920,1080")
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option('useAutomationExtension', False)
            
            # Set binary location for Chromium in Docker
            chromium_path = os.environ.get('CHROMIUM_BIN', '/usr/bin/chromium')
            if os.path.exists(chromium_path):
                options.binary_location = chromium_path
                logger.debug("Using Chromium binary", path=chromium_path)
            
            # Check if we're in a Docker environment (has chromium-driver)
            chromedriver_path = '/usr/bin/chromedriver'
            if os.path.exists(chromedriver_path):
                # Use system chromedriver (for Docker)
                logger.debug("Using system chromedriver", path=chromedriver_path)
                service = Service(chromedriver_path)
                self._driver = webdriver.Chrome(service=service, options=options)
            else:
                # Use ChromeDriverManager for local development
                logger.debug("Using ChromeDriverManager for local development")
                service = Service(ChromeDriverManager().install())
                self._driver = webdriver.Chrome(service=service, options=options)
            
            # Set page load timeout
            self._driver.set_page_load_timeout(30)
        
        return self._driver
    
    def _close_driver(self) -> None:
        """Close the Selenium WebDriver if it exists."""
        if self._driver:
            try:
                self._driver.quit()
            except Exception as e:
                logger.debug("Error closing driver", error=str(e))
            finally:
                self._driver = None
    
    def _add_cookie(self) -> None:
        """Add the authentication cookie to the current session."""
        driver = self._get_driver()
        # Navigate to the base URL first to set the cookie
        driver.get(STORYGRAPH_BASE_URL)
        time.sleep(1)  # Wait for page to load
        
        driver.add_cookie({
            'name': 'remember_user_token',
            'value': self.cookie,
            'domain': 'app.thestorygraph.com',
            'path': '/',
        })
    
    def _scroll_page(self) -> None:
        """Scroll the page to load all content (for infinite scroll pages)."""
        driver = self._get_driver()
        last_height = driver.execute_script("return document.body.scrollHeight")
        
        while True:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height
    
    def login(self) -> bool:
        """
        Authenticate with StoryGraph using the cookie.
        
        Returns:
            True if authentication successful, False otherwise
        """
        try:
            driver = self._get_driver()
            self._add_cookie()
            
            # Refresh to apply cookie
            driver.refresh()
            time.sleep(2)
            
            # Check if we're logged in by looking for user-specific elements
            # Navigate to currently-reading page which requires authentication
            if self.username:
                driver.get(f"{STORYGRAPH_BASE_URL}/currently-reading/{self.username}")
            else:
                driver.get(f"{STORYGRAPH_BASE_URL}/currently-reading")
            
            time.sleep(2)
            
            # Check if we're on a valid page (not redirected to login)
            current_url = driver.current_url
            if "sign_in" in current_url:
                logger.error("StoryGraph cookie authentication failed - redirected to login")
                return False
            
            self._authenticated = True
            logger.info("Successfully authenticated with StoryGraph using cookie")
            return True
            
        except WebDriverException as e:
            logger.error("StoryGraph authentication error", error=str(e))
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
            driver = self._get_driver()
            self._add_cookie()
            
            # Search for book
            search_url = f"{STORYGRAPH_BASE_URL}/browse?search_term={isbn}"
            driver.get(search_url)
            time.sleep(2)
            
            # Parse results
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            
            # Find first book result
            book_link = soup.find('a', href=re.compile(r'/books/[a-f0-9-]+'))
            
            if not book_link:
                return None
            
            # Extract book ID from URL
            href = book_link.get('href', '')
            match = re.search(r'/books/([a-f0-9-]+)', href)
            
            if not match:
                return None
            
            book_id = match.group(1)
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
            driver = self._get_driver()
            self._add_cookie()
            
            # Build search query
            query = title
            if author:
                query = f"{title} {author}"
            
            search_url = f"{STORYGRAPH_BASE_URL}/browse?search_term={query.replace(' ', '%20')}"
            driver.get(search_url)
            time.sleep(2)
            
            # Parse results
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            
            # Find book results
            book_links = soup.find_all('a', href=re.compile(r'/books/[a-f0-9-]+'))
            
            if not book_links:
                return None
            
            # Get first book
            book_link = book_links[0]
            href = book_link.get('href', '')
            match = re.search(r'/books/([a-f0-9-]+)', href)
            
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
            driver = self._get_driver()
            self._add_cookie()
            
            driver.get(f"{STORYGRAPH_BASE_URL}/books/{book_id}")
            time.sleep(2)
            
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            
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
                isbn_match = re.search(r'(\d{10}|\d{13})', str(isbn_elem))
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
            driver = self._get_driver()
            self._add_cookie()
            
            if self.username:
                url = f"{STORYGRAPH_BASE_URL}/currently-reading/{self.username}"
            else:
                url = f"{STORYGRAPH_BASE_URL}/currently-reading"
            
            driver.get(url)
            time.sleep(2)
            self._scroll_page()
            
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            books = []
            
            # Find book entries - StoryGraph uses various class names
            # Look for book cards or list items
            book_entries = soup.find_all(['div', 'li'], class_=re.compile(r'book|card|item'))
            
            for entry in book_entries:
                book_link = entry.find('a', href=re.compile(r'/books/[a-f0-9-]+'))
                if not book_link:
                    continue
                
                href = book_link.get('href', '')
                match = re.search(r'/books/([a-f0-9-]+)', href)
                
                if not match:
                    continue
                
                book_id = match.group(1)
                title = book_link.get_text(strip=True)
                
                # Try to find progress
                progress = None
                progress_elem = entry.find(string=re.compile(r'\d+%\s*(complete|read)?', re.IGNORECASE))
                if progress_elem:
                    progress_match = re.search(r'(\d+)%', str(progress_elem))
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
            
            logger.info("Retrieved currently reading books", count=len(books))
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
            driver = self._get_driver()
            self._add_cookie()
            
            # Navigate to book page
            driver.get(f"{STORYGRAPH_BASE_URL}/books/{book_id}")
            time.sleep(2)
            
            # Look for progress update button/form
            # StoryGraph UI has various ways to update progress
            # This is a simplified implementation
            
            # Try to find and click "Update Progress" or similar button
            try:
                # Look for progress input or button
                progress_input = driver.find_element(By.CSS_SELECTOR, "input[type='number'][name*='progress'], input[type='range']")
                if progress_input:
                    progress_input.clear()
                    progress_input.send_keys(str(progress_percent))
                    
                    # Find and click save/update button
                    save_button = driver.find_element(By.CSS_SELECTOR, "button[type='submit'], button:contains('Save'), button:contains('Update')")
                    if save_button:
                        save_button.click()
                        time.sleep(1)
                        logger.info("Updated progress via form", book_id=book_id, progress=progress_percent)
                        return True
            except Exception:
                pass
            
            # Alternative: Try to find "Add to currently reading" or status buttons
            try:
                # Look for status buttons
                status_buttons = driver.find_elements(By.CSS_SELECTOR, "button[data-status], a[data-status]")
                for button in status_buttons:
                    button_text = button.text.lower()
                    if "currently reading" in button_text or "reading" in button_text:
                        button.click()
                        time.sleep(1)
                        logger.info("Added to currently reading", book_id=book_id)
                        return True
            except Exception:
                pass
            
            # If we reach here, the UI structure may have changed
            logger.warning(
                "Could not find progress update UI elements - StoryGraph UI may have changed",
                book_id=book_id
            )
            return False
            
        except Exception as e:
            logger.error(
                "Failed to update progress",
                book_id=book_id,
                progress=progress_percent,
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
        try:
            driver = self._get_driver()
            self._add_cookie()
            
            # Navigate to book page
            driver.get(f"{STORYGRAPH_BASE_URL}/books/{book_id}")
            time.sleep(2)
            
            # Look for "Mark as finished" or "I've finished" button
            try:
                finish_buttons = driver.find_elements(By.CSS_SELECTOR, "button, a")
                for button in finish_buttons:
                    button_text = button.text.lower()
                    if "finished" in button_text or "done" in button_text or "complete" in button_text:
                        button.click()
                        time.sleep(1)
                        logger.info("Marked book as finished", book_id=book_id)
                        return True
            except Exception:
                pass
            
            # Fallback: update progress to 100%
            return self.update_progress(book_id, 100, "finished")
            
        except Exception as e:
            logger.error("Failed to mark as finished", book_id=book_id, error=str(e))
            return False
    
    def close(self) -> None:
        """Close the session and WebDriver."""
        self._close_driver()
