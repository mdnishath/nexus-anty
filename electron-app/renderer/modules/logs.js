/**
 * logs.js — Log DOM, escapeHtml, tag detection, appendLogDOM.
 * Loaded FIRST because other modules use App.log() and App.escapeHtml().
 */
(function (App) {
    'use strict';

    let _autoScroll = true;

    // Action-type tag detection — maps keyword patterns to badge classes
    const LOG_TAGS = [
        { pattern: /\[LOGIN\]/i,   badge: 'tag-login',   label: 'LOGIN'   },
        { pattern: /\[BROWSER\]/i, badge: 'tag-browser', label: 'BROWSER' },
        { pattern: /\[EXCEL\]/i,   badge: 'tag-excel',   label: 'EXCEL'   },
        { pattern: /\[OP\]/i,      badge: 'tag-op',      label: 'OP'      },
        { pattern: /\[SIGNOUT\]/i, badge: 'tag-signout', label: 'SIGNOUT' },
        // Fallback keyword detection for older messages without explicit tags
        { pattern: /login|sign.?in|password/i, badge: 'tag-login',   label: 'LOGIN'   },
        { pattern: /browser|page|navigat/i,    badge: 'tag-browser', label: 'BROWSER' },
        { pattern: /excel|xlsx|sheet|row/i,    badge: 'tag-excel',   label: 'EXCEL'   },
        { pattern: /op[1-8]|operation|change|recovery|authenticat|backup/i, badge: 'tag-op', label: 'OP' },
        { pattern: /sign.?out|logout/i,        badge: 'tag-signout', label: 'SIGNOUT' },
    ];

    function detectTag(msg) {
        for (const t of LOG_TAGS) {
            if (t.pattern.test(msg)) return t;
        }
        return null;
    }

    function escapeHtml(unsafe) {
        return unsafe
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function parseTime() {
        const d = new Date();
        return `[${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}:${d.getSeconds().toString().padStart(2, '0')}]`;
    }

    function appendLogDOM(msg, level) {
        const liveLog = document.getElementById('liveLog');
        if (!liveLog) return;

        const div = document.createElement('div');
        div.className = `log-entry ${level}`;

        const tag = detectTag(msg);
        const badgeHtml = tag
            ? `<span class="log-badge ${tag.badge}">${tag.label}</span>`
            : '';

        const msgEsc = escapeHtml(msg).replace(/'/g, "\\'");
        div.innerHTML = `<span class="time">${parseTime()}</span>${badgeHtml} <span class="msg" style="flex:1;">${escapeHtml(msg)}</span>
                        <button class="btn btn-sm copy-log-btn" style="opacity:0; padding:2px; background:none; border:none; color:#64748b; cursor:pointer;" title="Copy to clipboard" data-log-text="${msgEsc}"><i class="fas fa-copy"></i></button>`;
        
        // Add hover CSS dynamically if not present
        if (!document.getElementById('logCopyStyle')) {
            const s = document.createElement('style');
            s.id = 'logCopyStyle';
            s.innerHTML = `.log-entry:hover .copy-log-btn { opacity: 1 !important; transition: opacity 0.2s; }`;
            document.head.appendChild(s);
        }

        liveLog.appendChild(div);

        // Prevent memory leaks
        while (liveLog.children.length > 500) {
            liveLog.removeChild(liveLog.firstChild);
        }
    }

    function logMessage(msg, level) {
        appendLogDOM(msg, level || 'info');
        if (_autoScroll) {
            const liveLog = document.getElementById('liveLog');
            if (liveLog) liveLog.scrollTop = liveLog.scrollHeight;
        }
    }

    // ── Toast Notifications ─────────────────────────────────────────────

    function toast(message, type) {
        type = type || 'info';
        const container = document.getElementById('toastContainer');
        if (!container) return;

        const el = document.createElement('div');
        el.className = `toast ${type}`;
        el.textContent = message;
        container.appendChild(el);

        // Auto-remove after 4 seconds
        setTimeout(() => {
            el.classList.add('removing');
            el.addEventListener('animationend', () => el.remove());
        }, 4000);
    }

    App.setupLogsPanel = function() {
        const toggleBtn = document.getElementById('toggleAutoScrollBtn');
        const txt = document.getElementById('autoScrollText');
        const icon = toggleBtn ? toggleBtn.querySelector('i') : null;
        
        if (toggleBtn) {
            toggleBtn.addEventListener('click', () => {
                _autoScroll = !_autoScroll;
                if (_autoScroll) {
                    if (txt) txt.textContent = 'Auto-scroll: ON';
                    if (icon) icon.className = 'fas fa-lock';
                    const liveLog = document.getElementById('liveLog');
                    if (liveLog) liveLog.scrollTop = liveLog.scrollHeight;
                } else {
                    if (txt) txt.textContent = 'Auto-scroll: OFF';
                    if (icon) icon.className = 'fas fa-unlock';
                }
            });
        }
    };

    // Exports
    App.escapeHtml = escapeHtml;
    App.appendLogDOM = appendLogDOM;
    App.log = logMessage;
    App.toast = toast;

})(window.App || (window.App = {}));
