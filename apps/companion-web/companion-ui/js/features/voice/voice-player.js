const icons = {
  play: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m8 5 11 7-11 7Z"/></svg>',
  pause: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 5v14M15 5v14"/></svg>',
};

export function initVoicePlayer(dialogueStream, { api, announce = () => {}, dependencies = {} }) {
  const AudioImpl = dependencies.Audio ?? globalThis.Audio;
  const createUrl = dependencies.createObjectURL ?? URL.createObjectURL.bind(URL);
  const revokeUrl = dependencies.revokeObjectURL ?? URL.revokeObjectURL.bind(URL);
  let audio = null;
  let url = '';
  let activeId = '';
  let controller = null;
  let settings = { voiceEnabled: true, autoPlay: false, voiceId: 'alloy', speakingRate: 1, outputVolume: 1 };

  const release = () => {
    controller?.abort(); controller = null;
    if (audio) { audio.pause(); audio.src = ''; audio = null; }
    if (url) revokeUrl(url);
    url = ''; activeId = '';
  };

  const updateButtons = (id, playing) => {
    dialogueStream?.querySelectorAll('[data-voice-action="play"]').forEach((button) => {
      const current = button.closest('[data-message-id]')?.dataset.messageId === id;
      button.innerHTML = current && playing ? icons.pause : icons.play;
      button.setAttribute('aria-label', current && playing ? '暂停' : '播放语音');
    });
  };

  const play = async (id, text, { restart = false } = {}) => {
    if (!settings.voiceEnabled || !text) return;
    if (audio && activeId === id && !restart) {
      if (audio.paused) { await audio.play(); updateButtons(id, true); } else { audio.pause(); updateButtons(id, false); }
      return;
    }
    release();
    controller = new AbortController();
    try {
      const blob = await api.synthesize(text, {
        voiceId: settings.voiceId, speakingRate: settings.speakingRate, signal: controller.signal,
      });
      controller = null;
      url = createUrl(blob); activeId = id;
      audio = new AudioImpl(url); audio.volume = settings.outputVolume;
      audio.addEventListener('ended', () => updateButtons(id, false));
      audio.addEventListener('error', () => { announce('语音播放失败，文字回复不受影响。'); release(); });
      await audio.play(); updateButtons(id, true);
    } catch (error) { announce('语音暂时不可用，文字回复已经保留。'); release(); throw error; }
  };

  const click = (event) => {
    const button = event.target.closest('[data-voice-action]');
    const message = button?.closest('[data-message-id]');
    if (!button || !message) return;
    const text = message.querySelector('p')?.textContent ?? '';
    if (button.dataset.voiceAction === 'play') play(message.dataset.messageId, text).catch(() => {});
    if (button.dataset.voiceAction === 'replay') play(message.dataset.messageId, text, { restart: true }).catch(() => {});
    if (button.dataset.voiceAction === 'mute' && audio) {
      audio.muted = !audio.muted;
      button.setAttribute('aria-label', audio.muted ? '取消静音' : '静音');
    }
  };
  dialogueStream?.addEventListener('click', click);

  return Object.freeze({
    setSettings(next) { settings = { ...settings, ...next }; document.body.dataset.voiceEnabled = String(settings.voiceEnabled); if (!settings.voiceEnabled) release(); if (audio) audio.volume = settings.outputVolume; },
    maybeAutoPlay(message) { if (settings.autoPlay && message?.role === 'assistant') play(message.id, message.text).catch(() => {}); },
    async testVoice(next) {
      const previous = settings;
      settings = { ...settings, ...next };
      try { await play('__voice-test__', '你好，我在这里。', { restart: true }); }
      finally { settings = previous; }
    },
    destroy() { dialogueStream?.removeEventListener('click', click); release(); },
  });
}
