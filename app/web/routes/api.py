"""
API routes for Audiobook Sync Service.
"""

from datetime import datetime, timedelta
from flask import Blueprint, jsonify, request

from app.db.database import get_db_session
from app.db.models import SyncHistory, SyncRun, SyncLog, BookMapping
from app.sync.engine import create_sync_engine_from_config

api_bp = Blueprint('api', __name__, url_prefix='/api')


@api_bp.route('/status')
def status():
    """Get current sync status."""
    with get_db_session() as session:
        latest_run = session.query(SyncRun).order_by(
            SyncRun.started_at.desc()
        ).first()
        
        return jsonify({
            'last_sync': latest_run.started_at.isoformat() if latest_run else None,
            'last_sync_status': latest_run.status if latest_run else None,
            'books_processed': latest_run.books_processed if latest_run else 0,
            'books_synced': latest_run.books_synced if latest_run else 0,
        })


@api_bp.route('/sync', methods=['POST'])
def trigger_sync():
    """Manually trigger a sync."""
    try:
        engine = create_sync_engine_from_config()
        
        if not engine:
            return jsonify({
                'success': False,
                'error': 'Sync engine not configured'
            }), 400
        
        result = engine.sync()
        engine.close()
        
        return jsonify({
            'success': result.success,
            'run_id': result.run_id,
            'processed': result.books_processed,
            'synced': result.books_synced,
            'failed': result.books_failed,
            'error': result.error_message,
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@api_bp.route('/history')
def get_history():
    """Get sync history."""
    limit = request.args.get('limit', 50, type=int)
    
    with get_db_session() as session:
        history = session.query(SyncHistory).order_by(
            SyncHistory.synced_at.desc()
        ).limit(limit).all()
        
        return jsonify([{
            'id': h.id,
            'book_title': h.book_title,
            'book_author': h.book_author,
            'progress_percent': h.progress_percent,
            'sg_status': h.sg_status,
            'hc_status': h.hc_status,
            'synced_at': h.synced_at.isoformat() if h.synced_at else None,
        } for h in history])


@api_bp.route('/runs')
def get_runs():
    """Get sync runs."""
    limit = request.args.get('limit', 20, type=int)
    
    with get_db_session() as session:
        runs = session.query(SyncRun).order_by(
            SyncRun.started_at.desc()
        ).limit(limit).all()
        
        return jsonify([{
            'run_id': r.run_id,
            'started_at': r.started_at.isoformat() if r.started_at else None,
            'completed_at': r.completed_at.isoformat() if r.completed_at else None,
            'status': r.status,
            'books_processed': r.books_processed,
            'books_synced': r.books_synced,
            'books_failed': r.books_failed,
        } for r in runs])


@api_bp.route('/logs')
def get_logs():
    """Get recent logs."""
    limit = request.args.get('limit', 100, type=int)
    level = request.args.get('level')
    
    with get_db_session() as session:
        query = session.query(SyncLog)
        
        if level:
            query = query.filter(SyncLog.level == level.upper())
        
        logs = query.order_by(SyncLog.created_at.desc()).limit(limit).all()
        
        return jsonify([{
            'id': l.id,
            'level': l.level,
            'message': l.message,
            'details': l.details,
            'created_at': l.created_at.isoformat() if l.created_at else None,
        } for l in logs])


@api_bp.route('/mappings')
def get_mappings():
    """Get book mappings."""
    limit = request.args.get('limit', 100, type=int)
    
    with get_db_session() as session:
        mappings = session.query(BookMapping).order_by(
            BookMapping.last_matched.desc()
        ).limit(limit).all()
        
        return jsonify([{
            'abs_book_id': m.abs_book_id,
            'title': m.title,
            'author': m.author,
            'isbn': m.isbn,
            'asin': m.asin,
            'sg_book_id': m.sg_book_id,
            'hc_book_id': m.hc_book_id,
            'match_confidence': m.match_confidence,
            'last_matched': m.last_matched.isoformat() if m.last_matched else None,
        } for m in mappings])


@api_bp.route('/stats')
def get_stats():
    """Get sync statistics."""
    with get_db_session() as session:
        # Last 24 hours
        yesterday = datetime.utcnow() - timedelta(hours=24)
        
        total_synced = session.query(SyncHistory).filter(
            SyncHistory.synced_at >= yesterday,
            SyncHistory.sg_status == 'success'
        ).count()
        
        total_failed = session.query(SyncHistory).filter(
            SyncHistory.synced_at >= yesterday,
            SyncHistory.sg_status == 'failed'
        ).count()
        
        total_books = session.query(BookMapping).count()
        
        return jsonify({
            'last_24h': {
                'synced': total_synced,
                'failed': total_failed,
            },
            'total_mapped_books': total_books,
        })
