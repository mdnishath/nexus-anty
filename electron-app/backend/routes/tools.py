"""
routes/tools.py — Tools Blueprint

Handles:
  GET  /api/tools/screenshots          list PNG screenshots (paginated)
  GET  /api/tools/screenshot/<filename> serve a single screenshot image
  GET  /api/tools/auth-files           list authenticator/backup TXT files
  GET  /api/tools/auth-file/<filename> read content of a TXT file
  GET  /api/tools/storage-stats        disk usage summary
  POST /api/tools/cleanup              delete files by category

All routes previously lived inline in server.py.
They are extracted here and registered via create_tools_blueprint().
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from flask import Blueprint, jsonify, request, send_from_directory


def create_tools_blueprint(screenshots_path: Path) -> Blueprint:
    """Factory that returns the tools Blueprint.

    Args:
        screenshots_path: The server-level SCREENSHOTS_PATH (Path object).
    """
    bp = Blueprint('tools', __name__)

    # ── Screenshots ────────────────────────────────────────────────────────────

    @bp.route('/api/tools/screenshots', methods=['GET'])
    def tools_screenshots():
        """List .png screenshot files with pagination and optional search."""
        try:
            search   = request.args.get('search', '').lower()
            page_num = int(request.args.get('page', 1))
            per_page = int(request.args.get('per_page', 50))

            if not screenshots_path.exists():
                return jsonify({'success': True, 'files': [], 'total': 0, 'page': page_num})

            all_files = []
            for f in screenshots_path.iterdir():
                if f.suffix.lower() == '.png':
                    if search and search not in f.name.lower():
                        continue
                    stat = f.stat()
                    all_files.append({
                        'name':     f.name,
                        'size':     stat.st_size,
                        'modified': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M'),
                        '_sort':    stat.st_mtime,
                    })

            all_files.sort(key=lambda x: x['_sort'], reverse=True)
            for f in all_files:
                f.pop('_sort', None)
            total      = len(all_files)
            start      = (page_num - 1) * per_page
            page_files = all_files[start:start + per_page]
            total_pages = (total + per_page - 1) // per_page if total > 0 else 0

            return jsonify({
                'success': True, 'files': page_files, 'total': total,
                'page': page_num, 'per_page': per_page, 'total_pages': total_pages,
            })
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)})

    @bp.route('/api/tools/screenshot/<filename>', methods=['GET'])
    def tools_screenshot_image(filename):
        """Serve a single screenshot image file."""
        if '..' in filename or '/' in filename or '\\' in filename:
            return jsonify({'success': False, 'message': 'Invalid filename'}), 400
        if not filename.lower().endswith('.png'):
            return jsonify({'success': False, 'message': 'Only PNG files'}), 400
        filepath = screenshots_path / filename
        if not filepath.exists():
            return jsonify({'success': False, 'message': 'Not found'}), 404
        return send_from_directory(str(screenshots_path), filename, mimetype='image/png')

    # ── Auth / backup TXT files ────────────────────────────────────────────────

    @bp.route('/api/tools/auth-files', methods=['GET'])
    def tools_auth_files():
        """List authenticator_key_*.txt and backup_codes_*.txt files."""
        try:
            search   = request.args.get('search', '').lower()
            page_num = int(request.args.get('page', 1))
            per_page = int(request.args.get('per_page', 50))

            if not screenshots_path.exists():
                return jsonify({'success': True, 'files': [], 'total': 0, 'page': page_num})

            all_files = []
            for f in screenshots_path.iterdir():
                if f.suffix.lower() == '.txt' and (
                    f.name.startswith('authenticator_key_') or
                    f.name.startswith('backup_codes_')
                ):
                    if search and search not in f.name.lower():
                        continue
                    stat = f.stat()
                    all_files.append({
                        'name':     f.name,
                        'size':     stat.st_size,
                        'modified': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M'),
                        '_sort':    stat.st_mtime,
                        'type':     'authenticator' if f.name.startswith('authenticator_key_') else 'backup',
                    })

            all_files.sort(key=lambda x: x['_sort'], reverse=True)
            for f in all_files:
                f.pop('_sort', None)
            total       = len(all_files)
            start       = (page_num - 1) * per_page
            page_files  = all_files[start:start + per_page]
            total_pages = (total + per_page - 1) // per_page if total > 0 else 0

            return jsonify({
                'success': True, 'files': page_files, 'total': total,
                'page': page_num, 'per_page': per_page, 'total_pages': total_pages,
            })
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)})

    @bp.route('/api/tools/auth-file/<filename>', methods=['GET'])
    def tools_auth_file_content(filename):
        """Read and return content of an authenticator/backup text file."""
        if '..' in filename or '/' in filename or '\\' in filename:
            return jsonify({'success': False, 'message': 'Invalid filename'}), 400
        if not filename.lower().endswith('.txt'):
            return jsonify({'success': False, 'message': 'Only TXT files'}), 400
        filepath = screenshots_path / filename
        if not filepath.exists():
            return jsonify({'success': False, 'message': 'Not found'}), 404
        try:
            content = filepath.read_text(encoding='utf-8')
            return jsonify({'success': True, 'filename': filename, 'content': content})
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)})

    # ── Storage stats ──────────────────────────────────────────────────────────

    @bp.route('/api/tools/storage-stats', methods=['GET'])
    def tools_storage_stats():
        """Return storage statistics for screenshots, txt files, and backend log."""
        try:
            stats = {
                'screenshots':  {'count': 0, 'total_size': 0},
                'authenticator':{'count': 0, 'total_size': 0},
                'backup_codes': {'count': 0, 'total_size': 0},
                'log':          {'count': 0, 'total_size': 0},
            }

            if screenshots_path.exists():
                for f in screenshots_path.iterdir():
                    try:
                        sz = f.stat().st_size
                    except OSError:
                        continue
                    if f.suffix.lower() == '.png':
                        stats['screenshots']['count']      += 1
                        stats['screenshots']['total_size'] += sz
                    elif f.name.startswith('authenticator_key_') and f.suffix == '.txt':
                        stats['authenticator']['count']      += 1
                        stats['authenticator']['total_size'] += sz
                    elif f.name.startswith('backup_codes_') and f.suffix == '.txt':
                        stats['backup_codes']['count']      += 1
                        stats['backup_codes']['total_size'] += sz

            log_path = Path(os.environ.get('APPDATA', '')) / 'gmail-bot-pro' / 'backend.log'
            if log_path.exists():
                stats['log']['count']      = 1
                stats['log']['total_size'] = log_path.stat().st_size

            return jsonify({'success': True, 'stats': stats})
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)})

    # ── Cleanup ────────────────────────────────────────────────────────────────

    @bp.route('/api/tools/cleanup', methods=['POST'])
    def tools_cleanup():
        """Delete files by category: screenshots, authenticator, backup_codes, log."""
        try:
            data     = request.get_json(force=True, silent=True) or {}
            category = data.get('category', '')
            deleted  = 0
            freed    = 0

            if category == 'screenshots' and screenshots_path.exists():
                for f in list(screenshots_path.iterdir()):
                    if f.suffix.lower() == '.png':
                        freed += f.stat().st_size
                        f.unlink()
                        deleted += 1

            elif category == 'authenticator' and screenshots_path.exists():
                for f in list(screenshots_path.iterdir()):
                    if f.name.startswith('authenticator_key_') and f.suffix == '.txt':
                        freed += f.stat().st_size
                        f.unlink()
                        deleted += 1

            elif category == 'backup_codes' and screenshots_path.exists():
                for f in list(screenshots_path.iterdir()):
                    if f.name.startswith('backup_codes_') and f.suffix == '.txt':
                        freed += f.stat().st_size
                        f.unlink()
                        deleted += 1

            elif category == 'log':
                log_path = Path(os.environ.get('APPDATA', '')) / 'gmail-bot-pro' / 'backend.log'
                if log_path.exists():
                    freed += log_path.stat().st_size
                    log_path.unlink()
                    deleted += 1

            else:
                return jsonify({'success': False, 'message': f'Unknown category: {category}'})

            return jsonify({
                'success':     True,
                'message':     f'Deleted {deleted} file(s)',
                'deleted':     deleted,
                'freed_bytes': freed,
            })
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)})

    return bp
