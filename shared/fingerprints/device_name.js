(function () {
  const DNT = {{DNT}};

  Object.defineProperty(navigator, 'doNotTrack', {
    get: () => DNT ? '1' : null,
    configurable: true,
  });

  if ('getBattery' in navigator) {
    Object.defineProperty(navigator, 'getBattery', {
      value: undefined, configurable: true,
    });
  }
})();
