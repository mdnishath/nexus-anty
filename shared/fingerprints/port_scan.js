(function () {
  const ENABLED = {{PORT_SCAN_PROTECTION}};

  if (!ENABLED) return;

  const LOCAL_RE = /^(?:https?|wss?):\/\/(?:localhost|127\.\d+\.\d+\.\d+|\[?::1\]?|0\.0\.0\.0)(?::\d+)?/i;

  const _WS = window.WebSocket;
  window.WebSocket = function (url, protos) {
    if (LOCAL_RE.test(String(url)))
      throw new DOMException('Connection blocked by port scan protection', 'SecurityError');
    return new _WS(url, protos);
  };
  Object.setPrototypeOf(window.WebSocket, _WS);
  window.WebSocket.prototype = _WS.prototype;

  const _fetch = window.fetch;
  window.fetch = function (input, init) {
    const url = String(input instanceof Request ? input.url : input);
    if (LOCAL_RE.test(url))
      return Promise.reject(new TypeError('fetch blocked by port scan protection'));
    return _fetch.call(this, input, init);
  };

  const _open = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function (method, url, ...rest) {
    if (LOCAL_RE.test(String(url)))
      throw new DOMException('XHR blocked by port scan protection', 'SecurityError');
    return _open.call(this, method, url, ...rest);
  };
})();
