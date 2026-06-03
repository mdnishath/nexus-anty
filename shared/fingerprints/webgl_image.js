(function () {
  const MODE = '{{WEBGL_IMAGE_MODE}}'; // 'off' | 'noise'
  const SEED = {{NOISE_SEED}};

  if (MODE === 'off') return;

  let _s = SEED >>> 0;
  function rand() {
    _s = (_s + 0x6D2B79F5) >>> 0;
    let t = Math.imul(_s ^ (_s >>> 15), 1 | _s);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  }

  function patchPixels(pixels) {
    if (!pixels) return;
    for (let i = 0; i < pixels.length; i += 997) {
      if (rand() < 0.5) pixels[i] = pixels[i] ^ 1;
    }
  }

  function wrapReadPixels(proto) {
    const orig = proto.readPixels;
    proto.readPixels = function (x, y, w, h, fmt, type, pixels, ...rest) {
      orig.call(this, x, y, w, h, fmt, type, pixels, ...rest);
      patchPixels(pixels);
    };
  }

  wrapReadPixels(WebGLRenderingContext.prototype);
  if (typeof WebGL2RenderingContext !== 'undefined')
    wrapReadPixels(WebGL2RenderingContext.prototype);
})();
