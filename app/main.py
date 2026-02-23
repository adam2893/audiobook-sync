"""
Main entry point for Audiobook Sync Service.

Starts the Flask web server and the sync scheduler.
"""

import os
import atexit
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from flask import Flask, redirect, url_for

from app.config import ConfigManager, get_config_from_env
from app.db.database import init_db, close_db
from app.sync.engine import SyncEngine, create_sync_engine_from_config
from app.utils.logging import get_logger, setup_logging, init_db_logging

logger = get_logger(__name__)

# Global scheduler
scheduler = BackgroundScheduler()

# Global sync engine
sync_engine: SyncEngine = None


def create_app() -> Flask:
    """
    Create and configure the Flask application.
    
    Returns:
        Configured Flask app
    """
    app = Flask(__name__)
    
    # Load configuration
    config_manager = ConfigManager()
    config = config_manager.get_config()
    
    app.secret_key = config.secret_key
    
    # Register blueprints
    from app.web.routes.config import config_bp
    from app.web.routes.dashboard import dashboard_bp
    from app.web.routes.api import api_bp
    
    app.register_blueprint(config_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(api_bp)
    
    # Root route
    @app.route('/')
    def index():
        return redirect(url_for('dashboard.index'))
    
    # Health check
    @app.route('/health')
    def health():
        return {'status': 'ok', 'timestamp': datetime.utcnow().isoformat()}
    
    return app


def run_sync():
    """Run a sync operation."""
    global sync_engine
    
    logger.info("Starting scheduled sync")
    
    try:
        if sync_engine is None:
            sync_engine = create_sync_engine_from_config()
        
        if sync_engine:
            result = sync_engine.sync()
            logger.info(
                "Sync completed",
                run_id=result.run_id,
                processed=result.books_processed,
                synced=result.books_synced,
                failed=result.books_failed
            )
        else:
            logger.warning("Sync engine not configured, skipping sync")
            
    except Exception as e:
        logger.exception("Sync failed", error=str(e))


def start_scheduler(interval_minutes: int = 60):
    """
    Start the sync scheduler.
    
    Args:
        interval_minutes: Sync interval in minutes
    """
    scheduler.add_job(
        run_sync,
        trigger=IntervalTrigger(minutes=interval_minutes),
        id='sync_job',
        name='Audiobook Sync',
        replace_existing=True,
    )
    
    scheduler.start()
    logger.info(f"Scheduler started with {interval_minutes} minute interval")
    
    # Run initial sync after a short delay
    scheduler.add_job(
        run_sync,
        trigger='date',
        id='initial_sync',
    )


def shutdown_scheduler():
    """Shutdown the scheduler gracefully."""
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Scheduler shutdown")
    
    global sync_engine
    if sync_engine:
        sync_engine.close()


def main():
    """Main entry point."""
    # Setup logging
    setup_logging()
    
    # Initialize database
    init_db()
    
    # Initialize database logging (must be after init_db)
    init_db_logging()
    
    # Load configuration
    config = get_config_from_env()
    
    logger.info(
        "Starting Audiobook Sync Service",
        version="0.1.0",
        sync_interval=config.sync_interval_minutes
    )
    
    # Create Flask app
    app = create_app()
    
    # Start scheduler
    start_scheduler(config.sync_interval_minutes)
    
    # Register shutdown handler
    atexit.register(shutdown_scheduler)
    atexit.register(close_db)
    
    # Get port from environment
    port = int(os.getenv("PORT", "5000"))
    
    # Run Flask app with waitress
    from waitress import serve
    serve(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
