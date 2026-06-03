(function () {
  const MODE = '{{AUDIO_MODE}}'; // 'off' | 'noise'
  const SEED = {{AUDIO_SEED}};

  if (MODE === 'off') return;

  let _s = SEED >>> 0;
  function rand() {
    _s = (_s + 0x6D2B79F5) >>> 0;
    let t = Math.imul(_s ^ (_s >>> 15), 1 | _s);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  }
  const noise = () => (rand() - 0.5) * 0.0001;

  const _getFloat = AnalyserNode.prototype.getFloatFrequencyData;
  AnalyserNode.prototype.getFloatFrequencyData = function (array) {
    _getFloat.call(this, array);
    for (let i = 0; i < array.length; i++) array[i] += noise();
  };

  const _getByte = AnalyserNode.prototype.getByteFrequencyData;
  AnalyserNode.prototype.getByteFrequencyData = function (array) {
    _getByte.call(this, array);
    for (let i = 0; i < array.length; i++)
      array[i] = Math.max(0, Math.min(255, array[i] + Math.round(noise() * 200)));
  };

  if (AudioBuffer && AudioBuffer.prototype.copyFromChannel) {
    const _copy = AudioBuffer.prototype.copyFromChannel;
    AudioBuffer.prototype.copyFromChannel = function (dest, ch, off) {
      _copy.call(this, dest, ch, off);
      for (let i = 0; i < dest.length; i++) dest[i] += noise() * 0.005;
    };
  }
})();
