(function () {
  const MASKED       = {{MEDIA_DEVICES_MASK}};
  const VIDEO_INPUTS = {{VIDEO_INPUTS}};
  const AUDIO_INPUTS = {{AUDIO_INPUTS}};
  const AUDIO_OUTPUTS= {{AUDIO_OUTPUTS}};

  if (!MASKED) return;
  if (!navigator.mediaDevices) return;

  Object.defineProperty(navigator.mediaDevices, 'enumerateDevices', {
    value: async function () {
      const devices = [];
      for (let i = 0; i < VIDEO_INPUTS; i++)
        devices.push({ kind: 'videoinput',  deviceId: 'v'+i, groupId: 'g'+i,      label: '' });
      for (let i = 0; i < AUDIO_INPUTS; i++)
        devices.push({ kind: 'audioinput',  deviceId: 'ai'+i, groupId: 'g'+(i+10), label: '' });
      for (let i = 0; i < AUDIO_OUTPUTS; i++)
        devices.push({ kind: 'audiooutput', deviceId: 'ao'+i, groupId: 'g'+(i+20), label: '' });
      return devices;
    },
    writable: true, configurable: true,
  });

  if (VIDEO_INPUTS === 0 && AUDIO_INPUTS === 0) {
    const _gum = navigator.mediaDevices.getUserMedia;
    if (_gum) {
      Object.defineProperty(navigator.mediaDevices, 'getUserMedia', {
        value: function (constraints) {
          if (constraints.video && VIDEO_INPUTS === 0)
            return Promise.reject(new DOMException('No video devices', 'NotFoundError'));
          if (constraints.audio && AUDIO_INPUTS === 0)
            return Promise.reject(new DOMException('No audio devices', 'NotFoundError'));
          return _gum.call(this, constraints);
        },
        writable: true, configurable: true,
      });
    }
  }
})();
