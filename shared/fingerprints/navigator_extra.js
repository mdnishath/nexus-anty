// navigator_extra.js — Spoof navigator.connection, maxTouchPoints, pdfViewerEnabled
// These are checked by Google's anti-bot systems for consistency validation
(function() {
    'use strict';

    const OS_TYPE = '{{OS_TYPE}}';
    const isMobile = (OS_TYPE === 'android' || OS_TYPE === 'ios');

    // ── 1. navigator.connection (Network Information API) ──────────────
    // Google checks if this exists and has realistic values
    if (!navigator.connection) {
        const connData = {
            effectiveType: '4g',
            downlink: isMobile ? (Math.random() * 8 + 2).toFixed(1) : (Math.random() * 40 + 10).toFixed(1),
            rtt: isMobile ? Math.floor(Math.random() * 80 + 50) : Math.floor(Math.random() * 30 + 20),
            saveData: false,
            type: isMobile ? 'cellular' : 'wifi',
            onchange: null,
        };

        const conn = {};
        for (const [k, v] of Object.entries(connData)) {
            Object.defineProperty(conn, k, { get: () => v, enumerable: true, configurable: true });
        }
        conn.addEventListener = function() {};
        conn.removeEventListener = function() {};
        conn.dispatchEvent = function() { return true; };

        Object.defineProperty(navigator, 'connection', {
            get: () => conn,
            enumerable: true,
            configurable: true,
        });
    }

    // ── 2. navigator.maxTouchPoints ───────────────────────────────────
    // Desktop = 0, Mobile = 5 (most Android), iOS = 5
    const touchPoints = isMobile ? 5 : 0;
    Object.defineProperty(navigator, 'maxTouchPoints', {
        get: () => touchPoints,
        enumerable: true,
        configurable: true,
    });

    // ── 3. navigator.pdfViewerEnabled ─────────────────────────────────
    // Chrome always has this as true on desktop
    if (!isMobile) {
        Object.defineProperty(navigator, 'pdfViewerEnabled', {
            get: () => true,
            enumerable: true,
            configurable: true,
        });
    }

    // ── 4. navigator.webdriver = false (redundant safety) ─────────────
    Object.defineProperty(navigator, 'webdriver', {
        get: () => false,
        enumerable: true,
        configurable: true,
    });

    // ── 5. window.chrome object (must exist on real Chrome) ───────────
    if (!window.chrome) {
        window.chrome = { runtime: {}, loadTimes: function() {}, csi: function() {} };
    }
    if (!window.chrome.runtime) {
        window.chrome.runtime = {};
    }
})();
