"""
Logging configuration for Audiobook Sync Service.
Provides both console logging and database logging.
"""

import logging
import sys
import os
from datetime import datetime
from typing import Optional, Any, Dict
import structlog
from structlog.types import Processor

from app.db.models import SyncLog
from app.db.database import get_db_session


def get_log_level() -> str:
    """Get log level from environment."""
    return os.getenv("LOG_LEVEL", "INFO").upper()


def setup_logging() -> None:
    """Configure structured logging for the application."""
    
    # Shared processors for both console and structlog
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.ExtraAdder(),
    ]
    
    # Configure structlog
    structlog.configure(
        processors=shared_processors + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    
    # Configure standard library logging
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.dev.ConsoleRenderer(colors=True),
        ],
    )
    
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    root_logger.setLevel(getattr(logging, get_log_level()))
    
    # Reduce noise from third-party libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)


class DatabaseLogHandler(logging.Handler):
    """
    Custom log handler that writes logs to the database.
    Used for displaying logs in the web UI.
    """
    
    def __init__(self, max_logs: int = 1000):
        super().__init__()
        self.max_logs = max_logs
    
    def emit(self, record: logging.LogRecord) -> None:
        """Write log record to database."""
        try:
            with get_db_session() as session:
                # Create log entry
                log_entry = SyncLog(
                    level=record.levelname,
                    message=self.format(record),
                    details=getattr(record, 'details', None),
                    sync_run_id=getattr(record, 'sync_run_id', None),
                )
                session.add(log_entry)
                
                # Clean up old logs if we exceed max
                count = session.query(SyncLog).count()
                if count > self.max_logs:
                    # Delete oldest logs
                    oldest = session.query(SyncLog)\
                        .order_by(SyncLog.created_at.asc())\
                        .limit(count - self.max_logs)\
                        .all()
                    for log in oldest:
                        session.delete(log)
                        
        except Exception:
            # Don't raise exceptions from logging
            pass


def get_logger(name: str = __name__) -> structlog.stdlib.BoundLogger:
    """Get a configured logger instance."""
    return structlog.get_logger(name)


class SyncLogger:
    """
    Logger specifically for sync operations.
    Logs to both console and database with sync run context.
    """
    
    def __init__(self, sync_run_id: Optional[str] = None):
        self.logger = get_logger("sync")
        self.sync_run_id = sync_run_id
    
    def _log(self, level: str, message: str, **kwargs: Any) -> None:
        """Internal logging method."""
        log_method = getattr(self.logger, level.lower())
        
        # Add sync run ID to context
        if self.sync_run_id:
            structlog.contextvars.bind_contextvars(sync_run_id=self.sync_run_id)
        
        log_method(message, **kwargs)
        
        # Clear context
        structlog.contextvars.unbind_contextvars("sync_run_id")
    
    def info(self, message: str, **kwargs: Any) -> None:
        self._log("INFO", message, **kwargs)
    
    def warning(self, message: str, **kwargs: Any) -> None:
        self._log("WARNING", message, **kwargs)
    
    def error(self, message: str, **kwargs: Any) -> None:
        self._log("ERROR", message, **kwargs)
    
    def debug(self, message: str, **kwargs: Any) -> None:
        self._log("DEBUG", message, **kwargs)
    
    def exception(self, message: str, **kwargs: Any) -> None:
        """Log an exception with traceback."""
        self._log("ERROR", message, exc_info=True, **kwargs)


# Initialize logging on module import
setup_logging()

# Add database handler
db_handler = DatabaseLogHandler()
db_handler.setLevel(logging.INFO)
logging.getLogger().addHandler(db_handler)
