(function () {
  const MODE     = '{{WEBGL_META_MODE}}'; // 'off' | 'custom' | 'real'
  const VENDOR   = '{{WEBGL_VENDOR}}';
  const RENDERER = '{{WEBGL_RENDERER}}';

  if (MODE === 'real' || MODE === 'off') return;

  const UNMASKED_VENDOR_WEBGL   = 0x9245;
  const UNMASKED_RENDERER_WEBGL = 0x9246;
  const GL_VENDOR   = 0x1F00;
  const GL_RENDERER = 0x1F01;

  function patchProto(proto) {
    const _getParam = proto.getParameter;
    proto.getParameter = function (param) {
      if (param === UNMASKED_VENDOR_WEBGL   || param === GL_VENDOR)   return VENDOR;
      if (param === UNMASKED_RENDERER_WEBGL || param === GL_RENDERER) return RENDERER;
      return _getParam.call(this, param);
    };

    const _getExt = proto.getExtension;
    proto.getExtension = function (name) {
      const ext = _getExt.call(this, name);
      if (name === 'WEBGL_debug_renderer_info' && ext) {
        return new Proxy(ext, {
          get(t, p) {
            if (p === 'UNMASKED_VENDOR_WEBGL')   return UNMASKED_VENDOR_WEBGL;
            if (p === 'UNMASKED_RENDERER_WEBGL') return UNMASKED_RENDERER_WEBGL;
            return t[p];
          }
        });
      }
      return ext;
    };
  }

  patchProto(WebGLRenderingContext.prototype);
  if (typeof WebGL2RenderingContext !== 'undefined')
    patchProto(WebGL2RenderingContext.prototype);
})();
