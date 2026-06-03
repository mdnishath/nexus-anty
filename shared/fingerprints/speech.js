(function () {
  const MASKED  = {{SPEECH_MASK}};
  const OS_TYPE = '{{OS_TYPE}}';

  if (!MASKED || typeof speechSynthesis === 'undefined') return;

  const VOICE_LISTS = {
    windows: [
      { name: 'Microsoft David Desktop - English (United States)', lang: 'en-US', voiceURI: 'Microsoft David Desktop - English (United States)', localService: true, default: true },
      { name: 'Microsoft Zira Desktop - English (United States)',  lang: 'en-US', voiceURI: 'Microsoft Zira Desktop - English (United States)',  localService: true, default: false },
      { name: 'Microsoft Mark Desktop - English (United States)',  lang: 'en-US', voiceURI: 'Microsoft Mark Desktop - English (United States)',  localService: true, default: false },
    ],
    macos: [
      { name: 'Samantha', lang: 'en-US', voiceURI: 'com.apple.speech.synthesis.voice.samantha', localService: true, default: true },
      { name: 'Alex',     lang: 'en-US', voiceURI: 'com.apple.speech.synthesis.voice.alex',     localService: true, default: false },
    ],
    linux:   [{ name: 'English', lang: 'en-US', voiceURI: 'English', localService: true, default: true }],
    android: [],
    ios:     [{ name: 'Samantha', lang: 'en-US', voiceURI: 'com.apple.ttsbundle.Samantha-compact', localService: true, default: true }],
  };

  const list = VOICE_LISTS[OS_TYPE] || VOICE_LISTS['windows'];

  Object.defineProperty(speechSynthesis, 'getVoices', {
    value: function () { return list.map(v => Object.assign(Object.create(SpeechSynthesisVoice.prototype), v)); },
    configurable: true,
  });
})();
