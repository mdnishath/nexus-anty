(function () {
  const MODE = '{{CLIENT_RECTS_MODE}}'; // 'off' | 'noise'
  const SEED = {{NOISE_SEED}};

  if (MODE === 'off') return;

  let _s = SEED >>> 0;
  function rand() {
    _s = (_s + 0x6D2B79F5) >>> 0;
    let t = Math.imul(_s ^ (_s >>> 15), 1 | _s);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  }
  const noise = () => (rand() - 0.5) * 0.0006;

  function patchRect(r) {
    return {
      top:    r.top    + noise(),
      left:   r.left   + noise(),
      right:  r.right  + noise(),
      bottom: r.bottom + noise(),
      width:  r.width  + noise(),
      height: r.height + noise(),
      x:      r.x      + noise(),
      y:      r.y      + noise(),
      toJSON() { return {top:this.top,left:this.left,right:this.right,bottom:this.bottom,width:this.width,height:this.height,x:this.x,y:this.y}; }
    };
  }

  const _getBCR = Element.prototype.getBoundingClientRect;
  Element.prototype.getBoundingClientRect = function () {
    return patchRect(_getBCR.call(this));
  };

  const _getCR = Element.prototype.getClientRects;
  Element.prototype.getClientRects = function () {
    return Array.from(_getCR.call(this)).map(patchRect);
  };
})();
