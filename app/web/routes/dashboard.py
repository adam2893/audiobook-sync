"""
Dashboard routes for Audiobook Sync Service.
"""

from datetime import datetime, timedelta
from flask import Blueprint, render_template

from app.db.database import get_db_session
from app.db.models import SyncHistory, SyncRun, SyncLog

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/dashboard')
def index():
    """Dashboard home page."""
    with get_db_session() as session:
        # Get latest sync run
        latest_run = session.query(SyncRun).order_by(
            SyncRun.started_at.desc()
        ).first()
        
        # Get recent sync history (last 24 hours)
        yesterday = datetime.utcnow() - timedelta(hours=24)
        recent_syncs = session.query(SyncHistory).filter(
            SyncHistory.synced_at >= yesterday
        ).order_by(SyncHistory.synced_at.desc()).limit(20).all()
        
        # Get statistics for last 24 hours
        stats = {
            'synced': session.query(SyncHistory).filter(
                SyncHistory.synced_at >= yesterday,
                SyncHistory.sg_status == 'success'
            ).count(),
            'failed': session.query(SyncHistory).filter(
                SyncHistory.synced_at >= yesterday,
                SyncHistory.sg_status == 'failed'
            ).count(),
            'skipped': session.query(SyncHistory).filter(
                SyncHistory.synced_at >= yesterday,
                SyncHistory.sg_status == 'skipped'
            ).count(),
        }
        
        # Get recent errors
        errors = session.query(SyncHistory).filter(
            SyncHistory.synced_at >= yesterday,
            SyncHistory.sg_status == 'failed'
        ).order_by(SyncHistory.synced_at.desc()).limit(5).all()
        
        # Get recent logs
        recent_logs = session.query(SyncLog).order_by(
            SyncLog.created_at.desc()
        ).limit(50).all()
    
    # Calculate next sync time
    next_sync = None
    if latest_run and latest_run.completed_at:
        from app.config import ConfigManager
        config = ConfigManager().get_config()
        next_sync = latest_run.completed_at + timedelta(
            minutes=config.sync_interval_minutes
        )
    
    return render_template(
        'dashboard.html',
        latest_run=latest_run,
        recent_syncs=recent_syncs,
        stats=stats,
        errors=errors,
        recent_logs=recent_logs,
        next_sync=next_sync,
    )


@dashboard_bp.route('/logs')
def logs():
    """Logs viewer page."""
    with get_db_session() as session:
        # Get logs from last 7 days
        week_ago = datetime.utcnow() - timedelta(days=7)
        logs = session.query(SyncLog).filter(
            SyncLog.created_at >= week_ago
        ).order_by(SyncLog.created_at.desc()).limit(500).all()
    
    return render_template('logs.html', logs=logs)


@dashboard_bp.route('/history')
def history():
    """Sync history page."""
    with get_db_session() as session:
        # Get all sync runs
        sync_runs = session.query(SyncRun).order_by(
            SyncRun.started_at.desc()
        ).limit(50).all()
        
        # Get all sync history
        history = session.query(SyncHistory).order_by(
            SyncHistory.synced_at.desc()
        ).limit(100).all()
    
    return render_template(
        'history.html',
        sync_runs=sync_runs,
        history=history,
    )
