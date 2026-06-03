(function () {
  const MODE = '{{WEBGPU_MODE}}'; // 'disabled' | 'real'

  if (MODE === 'real') return;

  Object.defineProperty(navigator, 'gpu', {
    get: () => undefined,
    configurable: true,
  });
})();
