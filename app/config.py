"""
Configuration management for Audiobook Sync Service.
Supports both environment variables and database-stored configuration.
"""

import os
import secrets
from typing import Optional
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()


class SyncConfig(BaseModel):
    """Configuration for the sync service."""
    
    # Audiobookshelf settings
    abs_url: Optional[str] = Field(default=None, description="Audiobookshelf server URL")
    abs_token: Optional[str] = Field(default=None, description="Audiobookshelf API token")
    
    # StoryGraph settings
    storygraph_email: Optional[str] = Field(default=None, description="StoryGraph email")
    storygraph_password: Optional[str] = Field(default=None, description="StoryGraph password")
    
    # Hardcover settings
    hardcover_api_key: Optional[str] = Field(default=None, description="Hardcover API key")
    
    # Sync settings
    sync_interval_minutes: int = Field(default=60, description="Sync interval in minutes")
    min_listen_minutes: int = Field(default=10, description="Minimum listen time in minutes before syncing")
    
    # Feature toggles
    enable_storygraph: bool = Field(default=True, description="Enable StoryGraph sync")
    enable_hardcover: bool = Field(default=True, description="Enable Hardcover sync")
    
    # Application settings
    database_url: str = Field(
        default="sqlite:///data/audiobook-sync.db",
        description="Database connection URL"
    )
    secret_key: str = Field(
        default_factory=lambda: os.getenv("SECRET_KEY", secrets.token_hex(32)),
        description="Secret key for Flask sessions"
    )
    log_level: str = Field(default="INFO", description="Logging level")


def get_config_from_env() -> SyncConfig:
    """Load configuration from environment variables."""
    return SyncConfig(
        abs_url=os.getenv("ABS_URL"),
        abs_token=os.getenv("ABS_TOKEN"),
        storygraph_email=os.getenv("STORYGRAPH_EMAIL"),
        storygraph_password=os.getenv("STORYGRAPH_PASSWORD"),
        hardcover_api_key=os.getenv("HARDCOVER_API_KEY"),
        sync_interval_minutes=int(os.getenv("SYNC_INTERVAL_MINUTES", "60")),
        min_listen_minutes=int(os.getenv("MIN_LISTEN_MINUTES", "10")),
        enable_storygraph=os.getenv("ENABLE_STORYGRAPH", "true").lower() == "true",
        enable_hardcover=os.getenv("ENABLE_HARDCOVER", "true").lower() == "true",
        database_url=os.getenv("DATABASE_URL", "sqlite:///data/audiobook-sync.db"),
        secret_key=os.getenv("SECRET_KEY", secrets.token_hex(32)),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
    )


class ConfigManager:
    """
    Manages configuration with fallback from database to environment variables.
    """
    
    def __init__(self, db_session=None):
        self.db_session = db_session
        self._env_config = get_config_from_env()
        self._db_config = None
    
    def load_from_db(self) -> Optional['ConfigModel']:
        """Load configuration from database if available."""
        if not self.db_session:
            return None
        
        from app.db.models import Config
        return self.db_session.query(Config).first()
    
    def get_config(self) -> SyncConfig:
        """
        Get configuration, merging database values with environment variables.
        Database values take precedence over environment variables.
        """
        db_config = self.load_from_db()
        
        if db_config:
            return SyncConfig(
                abs_url=db_config.abs_url or self._env_config.abs_url,
                abs_token=db_config.abs_token or self._env_config.abs_token,
                storygraph_email=db_config.sg_email or self._env_config.storygraph_email,
                storygraph_password=db_config.sg_password or self._env_config.storygraph_password,
                hardcover_api_key=db_config.hc_api_key or self._env_config.hardcover_api_key,
                sync_interval_minutes=db_config.sync_interval_minutes or self._env_config.sync_interval_minutes,
                min_listen_minutes=(db_config.min_listen_time_seconds // 60) if db_config.min_listen_time_seconds else self._env_config.min_listen_minutes,
                enable_storygraph=self._env_config.enable_storygraph,
                enable_hardcover=self._env_config.enable_hardcover,
                database_url=self._env_config.database_url,
                secret_key=self._env_config.secret_key,
                log_level=self._env_config.log_level,
            )
        
        return self._env_config
    
    def save_config(self, config: SyncConfig) -> None:
        """Save configuration to database."""
        if not self.db_session:
            raise RuntimeError("Database session not available")
        
        from app.db.models import Config
        
        db_config = self.load_from_db()
        if not db_config:
            db_config = Config()
            self.db_session.add(db_config)
        
        db_config.abs_url = config.abs_url
        db_config.abs_token = config.abs_token
        db_config.sg_email = config.storygraph_email
        db_config.sg_password = config.storygraph_password
        db_config.hc_api_key = config.hardcover_api_key
        db_config.sync_interval_minutes = config.sync_interval_minutes
        db_config.min_listen_time_seconds = config.min_listen_minutes * 60
        
        self.db_session.commit()
    
    def is_configured(self) -> bool:
        """Check if the minimum required configuration is present."""
        config = self.get_config()
        
        # At minimum, we need Audiobookshelf configured
        if not config.abs_url or not config.abs_token:
            return False
        
        # And at least one target service
        has_storygraph = config.storygraph_email and config.storygraph_password
        has_hardcover = config.hardcover_api_key
        
        return has_storygraph or has_hardcover
