(function () {
  const SCREEN_W    = {{SCREEN_WIDTH}};
  const SCREEN_H    = {{SCREEN_HEIGHT}};
  const CPU_THREADS = {{CPU_THREADS}};
  const RAM_GB      = {{RAM_GB}};
  const OS_TYPE     = '{{OS_TYPE}}';

  const _is_mobile = OS_TYPE === 'android' || OS_TYPE === 'ios';

  // ── Screen resolution ────────────────────────────────────────────────────
  if (SCREEN_W > 0 && SCREEN_H > 0) {
    const _def = (obj, prop, val) => {
      try {
        Object.defineProperty(obj, prop, { get: () => val, configurable: true });
      } catch (e) {}
    };
    _def(screen, 'width',       SCREEN_W);
    _def(screen, 'height',      SCREEN_H);
    _def(screen, 'availWidth',  SCREEN_W);
    _def(screen, 'availHeight', SCREEN_H - (_is_mobile ? 0 : 40));
    _def(screen, 'colorDepth',  24);
    _def(screen, 'pixelDepth',  24);
    _def(window, 'outerWidth',  SCREEN_W);
    _def(window, 'outerHeight', SCREEN_H);
    _def(window, 'screenX', 0);
    _def(window, 'screenY', 0);
  }

  // ── CPU threads ───────────────────────────────────────────────────────────
  if (CPU_THREADS > 0) {
    try {
      Object.defineProperty(navigator, 'hardwareConcurrency', {
        get: () => CPU_THREADS, configurable: true,
      });
    } catch (e) {}
  }

  // ── RAM (deviceMemory — nearest allowed value) ────────────────────────────
  if (RAM_GB > 0) {
    const ALLOWED = [0.25, 0.5, 1, 2, 4, 8];
    const clamped = ALLOWED.reduce((a, b) => Math.abs(b - RAM_GB) < Math.abs(a - RAM_GB) ? b : a);
    try {
      Object.defineProperty(navigator, 'deviceMemory', {
        get: () => clamped, configurable: true,
      });
    } catch (e) {}
  }

  // ── NOTE: navigator.language / navigator.languages are set natively via   ──
  // ── Chrome's --lang and --accept-lang flags. Do NOT override with          ──
  // ── Object.defineProperty — fingerprinting sites check property            ──
  // ── descriptors and detect the custom getter.                              ──

  // ── Mobile-specific APIs ──────────────────────────────────────────────────
  if (_is_mobile) {
    // Touch support — Android/iOS always have ≥5 touch points
    try {
      Object.defineProperty(navigator, 'maxTouchPoints', {
        get: () => 5, configurable: true,
      });
    } catch (e) {}

    // Screen orientation — portrait-primary for phones
    try {
      if (screen.orientation) {
        Object.defineProperty(screen.orientation, 'type', {
          get: () => 'portrait-primary', configurable: true,
        });
        Object.defineProperty(screen.orientation, 'angle', {
          get: () => 0, configurable: true,
        });
      }
    } catch (e) {}

    // window.orientation — deprecated but still checked by some sites
    try {
      Object.defineProperty(window, 'orientation', {
        get: () => 0, configurable: true,
      });
    } catch (e) {}

    // Network connection — mobile devices report 4G
    try {
      const conn = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
      if (conn) {
        Object.defineProperty(conn, 'effectiveType', { get: () => '4g', configurable: true });
        Object.defineProperty(conn, 'type',          { get: () => 'cellular', configurable: true });
        Object.defineProperty(conn, 'rtt',           { get: () => 100, configurable: true });
        Object.defineProperty(conn, 'downlink',      { get: () => 10, configurable: true });
      }
    } catch (e) {}
  }
})();
