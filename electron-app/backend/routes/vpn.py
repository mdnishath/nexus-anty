"""
routes/vpn.py — VPN Control Blueprint

Handles:
  GET  /api/vpn/status        check if kill-task is set up + current IP
  POST /api/vpn/setup         create the admin scheduled task (shows UAC)
  POST /api/vpn/test-kill     disconnect VPN via scheduled task
  POST /api/vpn/test-connect  connect VPN and verify

All routes previously lived inline in server.py.
Registered via create_vpn_blueprint().
"""

from __future__ import annotations

from flask import Blueprint, jsonify, request


def create_vpn_blueprint() -> Blueprint:
    """Factory that returns the VPN Blueprint."""
    bp = Blueprint('vpn', __name__)

    @bp.route('/api/vpn/status', methods=['GET'])
    def vpn_status():
        """Check if VPN kill task is set up and current public IP."""
        try:
            from shared.vpn_controller import is_vpn_task_setup, get_public_ip
            task_ready = is_vpn_task_setup()
            current_ip = get_public_ip()
            return jsonify({
                'success':    True,
                'task_setup': task_ready,
                'current_ip': current_ip or 'unknown',
            })
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)}), 500

    @bp.route('/api/vpn/setup', methods=['POST'])
    def vpn_setup():
        """Create the admin scheduled task for VPN kill (one-time, shows UAC)."""
        try:
            from shared.vpn_controller import setup_vpn_task
            result = setup_vpn_task()
            return jsonify(result)
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)}), 500

    @bp.route('/api/vpn/test-kill', methods=['POST'])
    def vpn_test_kill():
        """Test VPN kill (disconnect) using the scheduled task."""
        try:
            from shared.vpn_controller import disconnect_vpn
            result = disconnect_vpn()
            return jsonify({'success': True, **result})
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)}), 500

    @bp.route('/api/vpn/test-connect', methods=['POST'])
    def vpn_test_connect():
        """Test VPN connect cycle."""
        try:
            vpn_path = (request.get_json(force=True, silent=True) or {}).get(
                'vpn_path', r'C:\Program Files\Privax\HMA VPN\Vpn.exe'
            )
            from shared.vpn_controller import connect_vpn
            result = connect_vpn(vpn_path=vpn_path, max_retries=3)
            return jsonify({'success': result['connected'], **result})
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)}), 500

    return bp
