(function () {
  const MASKED  = {{FONTS_MASK}};
  const OS_TYPE = '{{OS_TYPE}}';
  const SEED    = {{NOISE_SEED}};

  if (!MASKED) return;

  let _s = SEED >>> 0;
  function rand() {
    _s = (_s + 0x6D2B79F5) >>> 0;
    let t = Math.imul(_s ^ (_s >>> 15), 1 | _s);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  }
  const noise = () => (rand() - 0.5) * 0.0003;

  const _measureText = CanvasRenderingContext2D.prototype.measureText;
  CanvasRenderingContext2D.prototype.measureText = function (text) {
    const m = _measureText.call(this, text);
    const n = noise();
    return Object.assign(Object.create(Object.getPrototypeOf(m)), m, {
      width: m.width + n,
    });
  };
})();
