"""
Configuration routes for Audiobook Sync Service.
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash

from app.config import ConfigManager, SyncConfig
from app.db.database import get_db_session
from app.db.models import Config

config_bp = Blueprint('config', __name__)


@config_bp.route('/config', methods=['GET', 'POST'])
def index():
    """Configuration page."""
    
    if request.method == 'POST':
        # Save configuration
        try:
            config = SyncConfig(
                abs_url=request.form.get('abs_url') or None,
                abs_token=request.form.get('abs_token') or None,
                storygraph_cookie=request.form.get('storygraph_cookie') or None,
                storygraph_username=request.form.get('storygraph_username') or None,
                hardcover_api_key=request.form.get('hardcover_api_key') or None,
                sync_interval_minutes=int(request.form.get('sync_interval_minutes', 60)),
                min_listen_minutes=int(request.form.get('min_listen_minutes', 10)),
                enable_storygraph=request.form.get('enable_storygraph') == 'on',
                enable_hardcover=request.form.get('enable_hardcover') == 'on',
            )
            
            # Save to database
            with get_db_session() as session:
                db_config = session.query(Config).first()
                
                if not db_config:
                    db_config = Config()
                    session.add(db_config)
                
                db_config.abs_url = config.abs_url
                db_config.abs_token = config.abs_token
                db_config.sg_cookie = config.storygraph_cookie
                db_config.sg_username = config.storygraph_username
                db_config.hc_api_key = config.hardcover_api_key
                db_config.sync_interval_minutes = config.sync_interval_minutes
                db_config.min_listen_time_seconds = config.min_listen_minutes * 60
            
            flash('Configuration saved successfully!', 'success')
            
        except Exception as e:
            flash(f'Error saving configuration: {str(e)}', 'error')
        
        return redirect(url_for('config.index'))
    
    # GET request - show configuration form
    # Load config from database
    with get_db_session() as session:
        config_manager = ConfigManager(db_session=session)
        current_config = config_manager.get_config()
    
    return render_template(
        'config.html',
        config=current_config,
    )


@config_bp.route('/config/test', methods=['POST'])
def test_connection():
    """Test connection to a service."""
    service = request.form.get('service')
    
    if service == 'audiobookshelf':
        from app.api.audiobookshelf import AudiobookshelfClient
        
        url = request.form.get('url')
        token = request.form.get('token')
        
        if not url or not token:
            return {'success': False, 'error': 'URL and token are required'}
        
        try:
            client = AudiobookshelfClient(url, token)
            success = client.test_connection()
            client.close()
            
            return {'success': success}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    elif service == 'hardcover':
        from app.api.hardcover import HardcoverClient
        
        api_key = request.form.get('api_key')
        
        if not api_key:
            return {'success': False, 'error': 'API key is required'}
        
        try:
            client = HardcoverClient(api_key)
            success = client.test_connection()
            
            return {'success': success}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    elif service == 'storygraph':
        from app.api.storygraph import StoryGraphClient
        
        cookie = request.form.get('cookie')
        username = request.form.get('username')
        
        if not cookie:
            return {'success': False, 'error': 'Cookie is required'}
        
        try:
            client = StoryGraphClient(cookie, username)
            success = client.login()
            client.close()
            
            return {'success': success}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    return {'success': False, 'error': 'Unknown service'}
