(function () {
  const MODE = '{{CANVAS_MODE}}'; // 'off' | 'noise' | 'block'
  const SEED = {{CANVAS_SEED}};

  if (MODE === 'off') return;

  // Mulberry32 seeded PRNG — deterministic, fast
  let _s = SEED >>> 0;
  function rand() {
    _s = (_s + 0x6D2B79F5) >>> 0;
    let t = Math.imul(_s ^ (_s >>> 15), 1 | _s);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  }

  function noiseData(data) {
    for (let i = 0; i < data.length; i += 4) {
      if (rand() < 0.003) {
        const delta = Math.floor(rand() * 4) - 2;
        data[i]     = Math.max(0, Math.min(255, data[i]     + delta));
        data[i + 1] = Math.max(0, Math.min(255, data[i + 1] + delta));
      }
    }
  }

  const _toDataURL = HTMLCanvasElement.prototype.toDataURL;
  HTMLCanvasElement.prototype.toDataURL = function (type, quality) {
    if (MODE === 'block') return 'data:image/png;base64,';
    const ctx = this.getContext && this.getContext('2d');
    if (ctx && this.width > 0 && this.height > 0) {
      try {
        const img = ctx.getImageData(0, 0, this.width, this.height);
        noiseData(img.data);
        ctx.putImageData(img, 0, 0);
      } catch (e) { /* cross-origin — skip */ }
    }
    return _toDataURL.call(this, type, quality);
  };

  const _getImageData = CanvasRenderingContext2D.prototype.getImageData;
  CanvasRenderingContext2D.prototype.getImageData = function (sx, sy, sw, sh) {
    const img = _getImageData.call(this, sx, sy, sw, sh);
    if (MODE === 'block') { img.data.fill(0); return img; }
    noiseData(img.data);
    return img;
  };
})();
