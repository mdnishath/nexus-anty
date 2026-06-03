"""
Shared logging setup.

Each module that needs enhanced logging should import:
    from shared.logger import print, _log
"""

import builtins
import logging
from logging.handlers import RotatingFileHandler
import os
from datetime import datetime
from pathlib import Path

# ── Resolve a safe absolute path for the log file ────────────────────────────
# Priority:
#   1. RESOURCES_PATH env var (set by Electron in packaged builds)
#   2. %LOCALAPPDATA%\MailNexusPro\logs\ (preferred — out of project root)
#   3. Project root (fallback for dev mode without env var)
_res = os.environ.get('RESOURCES_PATH')
if _res:
    _log_dir = Path(_res)
else:
    # Prefer AppData so logs don't pollute the project root / git index
    _appdata = os.environ.get('LOCALAPPDATA', '')
    if _appdata:
        _log_dir = Path(_appdata) / 'MailNexusPro' / 'logs'
        try:
            _log_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            _log_dir = Path(__file__).resolve().parent.parent  # fallback
    else:
        _log_dir = Path(__file__).resolve().parent.parent

_log_file = _log_dir / 'debug.log'

# ── Log rotation: 5 MB max, 2 backups (debug.log.1, .2) ──────────────────
# Total max: 15 MB (down from 40 MB). Plenty for debugging while saving disk.
try:
    _handler = RotatingFileHandler(
        str(_log_file), maxBytes=5 * 1024 * 1024, backupCount=2, encoding='utf-8',
    )
    _handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
    _logger = logging.getLogger()
    _logger.setLevel(logging.DEBUG)
    _logger.addHandler(_handler)
except Exception:
    # If even the absolute path fails, fall back to no-file logging
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(message)s')

original_print = builtins.print


def print(*args, **kwargs):
    """Enhanced print: logs to file and flushes stdout immediately."""
    msg = " ".join(str(a) for a in args)
    try:
        logging.info(msg)
    except Exception:
        pass  # never crash on log-file write failures
    kwargs.setdefault('flush', True)
    try:
        original_print(*args, **kwargs)
    except Exception:
        # Windows stdout pipe may be broken/non-UTF-8 — swallow silently.
        # The message is already persisted via logging.info() above.
        pass


def _log(worker_id, msg):
    """Timestamped log line for a worker."""
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}][WORKER {worker_id}] {msg}")


def _log_tag(worker_id, tag, msg):
    """Log with an action-type tag prefix for UI color coding.

    Tags: LOGIN, BROWSER, EXCEL, OP, SIGNOUT
    """
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}][WORKER {worker_id}][{tag}] {msg}")


def _log_login(worker_id, msg):
    _log_tag(worker_id, "LOGIN", msg)


def _log_browser(worker_id, msg):
    _log_tag(worker_id, "BROWSER", msg)


def _log_excel(worker_id, msg):
    _log_tag(worker_id, "EXCEL", msg)


def _log_op(worker_id, msg):
    _log_tag(worker_id, "OP", msg)


def _log_signout(worker_id, msg):
    _log_tag(worker_id, "SIGNOUT", msg)
