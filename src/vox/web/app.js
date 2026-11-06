const BUILT_IN_ID = '';
const SYNC_INTERVAL_MS = 4000;
const WAVE_BAR_COUNT = 64;
const INTERNAL_ERROR_MESSAGE = 'Something went wrong in Vox. Check the terminal running `vox init`.';

const state = {
  voices: [],
  invalid: [],
  librarySignature: null,
  selectedVoiceId: readSetting('vox.voice') ?? BUILT_IN_ID,
  reviewingVoiceId: null,
  reviewPlayer: null,
  resultPlayer: null,
  deletingVoiceId: null,
};

// ── Small helpers ──

function readSetting(key) {
  try {
    return localStorage.getItem(key);
  } catch (_error) {
    return null;
  }
}

function writeSetting(key, value) {
  try {
    localStorage.setItem(key, value);
  } catch (_error) {
    // Storage can be unavailable (private windows); the setting just won't persist.
  }
}

const $ = (id) => document.getElementById(id);

function setStatus(element, message, isError = false) {
  element.textContent = message;
  element.classList.toggle('error', isError);
}

// Unhandled server errors may come back as plain text, not JSON.
async function readError(response) {
  try {
    const data = await response.json();
    return data.detail || INTERNAL_ERROR_MESSAGE;
  } catch (_error) {
    return INTERNAL_ERROR_MESSAGE;
  }
}

async function request(url, options = {}) {
  const response = await fetch(url, options);

  if (!response.ok) {
    throw new Error(await readError(response));
  }

  return response;
}

function svg(markup) {
  const template = document.createElement('template');
  template.innerHTML = markup.trim();
  return template.content.firstChild;
}

const ICONS = {
  play: '<svg class="icon-play" viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5.5v13a1 1 0 0 0 1.5.86l10.6-6.5a1 1 0 0 0 0-1.72L9.5 4.64A1 1 0 0 0 8 5.5Z"/></svg>',
  pause: '<svg class="icon-pause" viewBox="0 0 24 24" aria-hidden="true"><rect x="6" y="5" width="4" height="14" rx="1.2"/><rect x="14" y="5" width="4" height="14" rx="1.2"/></svg>',
  download: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4v11M7 10l5 5 5-5M5 20h14"/></svg>',
  trash: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V4h6v3"/></svg>',
  check: '<svg class="picker-check" viewBox="0 0 24 24" aria-hidden="true"><path d="m5 12 5 5 9-10"/></svg>',
};

function formatTime(seconds) {
  if (!Number.isFinite(seconds)) {
    return '0:00';
  }

  const whole = Math.floor(seconds);
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, '0')}`;
}

// A stable gradient per voice, so each one is recognizable at a glance.
function avatarGradient(voiceId) {
  if (voiceId === BUILT_IN_ID) {
    return 'conic-gradient(from 210deg, #9ca3af, #e5e7eb, #6b7280, #9ca3af)';
  }

  let hash = 0;
  for (const character of voiceId) {
    hash = (hash * 31 + character.charCodeAt(0)) >>> 0;
  }

  const hue = hash % 360;
  return `linear-gradient(135deg, hsl(${hue} 85% 72%), hsl(${(hue + 55) % 360} 75% 52%))`;
}

function paintAvatar(element, voiceId) {
  element.style.setProperty('--avatar', avatarGradient(voiceId));
}

function isReviewed(voice) {
  return Boolean(voice.transcript_reviewed_at);
}

function createBadge(voice) {
  const badge = document.createElement('span');
  badge.className = `badge ${isReviewed(voice) ? 'reviewed' : 'needs-review'}`;
  badge.textContent = isReviewed(voice) ? 'Reviewed' : 'Needs review';
  return badge;
}

// While a modal is saving, lock its inputs and keep it from being dismissed.
function setModalBusy(dialog, busy) {
  dialog.classList.toggle('busy', busy);
  dialog.dataset.busy = busy ? 'true' : '';

  for (const control of dialog.querySelectorAll('input, textarea, button')) {
    control.disabled = busy;
  }
}

let toastTimer = null;

function showToast(message) {
  const toast = $('toast');
  toast.textContent = message;
  toast.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    toast.hidden = true;
  }, 3000);
}

function selectedVoice() {
  return state.voices.find((voice) => voice.id === state.selectedVoiceId) || null;
}

// ── Theme ──

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  $('theme-label').textContent = theme === 'dark' ? 'Light mode' : 'Dark mode';
}

function initTheme() {
  applyTheme(document.documentElement.dataset.theme);
  $('theme-toggle').addEventListener('click', () => {
    const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
    applyTheme(next);
    writeSetting('vox.theme', next);
  });
}

// ── Routing ──

function showRoute() {
  const requested = location.hash.replace('#/', '');
  const route = ['voices', 'help'].includes(requested) ? requested : 'studio';

  for (const page of document.querySelectorAll('[data-page]')) {
    page.hidden = page.dataset.page !== route;
  }

  for (const link of document.querySelectorAll('[data-route]')) {
    link.classList.toggle('active', link.dataset.route === route);
  }

  window.scrollTo(0, 0);
  closePicker();
}

// ── Waveform player ──

let audioContext = null;
let activeAudio = null;

async function computePeaks(blob, count) {
  audioContext ??= new AudioContext();
  const buffer = await audioContext.decodeAudioData(await blob.arrayBuffer());
  const samples = buffer.getChannelData(0);
  const bucketSize = Math.max(1, Math.floor(samples.length / count));
  const peaks = [];

  for (let bucket = 0; bucket < count; bucket += 1) {
    let peak = 0;
    const start = bucket * bucketSize;

    for (let index = start; index < start + bucketSize && index < samples.length; index += 1) {
      peak = Math.max(peak, Math.abs(samples[index]));
    }

    peaks.push(peak);
  }

  const loudest = Math.max(...peaks, 0.001);
  return peaks.map((peak) => peak / loudest);
}

function createPlayer(blob, { downloadName = null } = {}) {
  const url = URL.createObjectURL(blob);
  const audio = new Audio(url);
  const element = document.createElement('div');
  element.className = 'player';

  const toggle = document.createElement('button');
  toggle.type = 'button';
  toggle.className = 'player-toggle';
  toggle.setAttribute('aria-label', 'Play');
  toggle.append(svg(ICONS.play), svg(ICONS.pause));

  const wave = document.createElement('div');
  wave.className = 'player-wave';
  wave.setAttribute('role', 'slider');
  wave.setAttribute('aria-label', 'Seek');
  const bars = Array.from({ length: WAVE_BAR_COUNT }, () => {
    const bar = document.createElement('span');
    bar.style.height = '12%';
    wave.appendChild(bar);
    return bar;
  });

  const time = document.createElement('span');
  time.className = 'player-time';
  time.textContent = '0:00';

  element.append(toggle, wave, time);

  if (downloadName) {
    const download = document.createElement('a');
    download.className = 'icon-button';
    download.href = url;
    download.download = downloadName;
    download.setAttribute('aria-label', 'Download WAV');
    download.title = 'Download WAV';
    download.appendChild(svg(ICONS.download));
    element.appendChild(download);
  }

  computePeaks(blob, WAVE_BAR_COUNT)
    .then((peaks) => {
      peaks.forEach((peak, index) => {
        bars[index].style.height = `${Math.max(8, Math.round(peak * 100))}%`;
      });
    })
    .catch(() => {});

  let frame = null;

  function render() {
    const progress = audio.duration ? audio.currentTime / audio.duration : 0;
    const playedBars = Math.round(progress * bars.length);
    bars.forEach((bar, index) => bar.classList.toggle('played', index < playedBars));
    time.textContent = `${formatTime(audio.currentTime)} / ${formatTime(audio.duration)}`;
  }

  function loop() {
    render();
    frame = audio.paused ? null : requestAnimationFrame(loop);
  }

  audio.addEventListener('loadedmetadata', render);
  audio.addEventListener('play', () => {
    // Only one clip plays at a time.
    if (activeAudio && activeAudio !== audio) {
      activeAudio.pause();
    }
    activeAudio = audio;
    element.classList.add('playing');
    toggle.setAttribute('aria-label', 'Pause');
    loop();
  });
  audio.addEventListener('pause', () => {
    element.classList.remove('playing');
    toggle.setAttribute('aria-label', 'Play');
    render();
  });
  audio.addEventListener('ended', () => {
    audio.currentTime = 0;
    render();
  });

  toggle.addEventListener('click', () => {
    if (audio.paused) {
      audio.play().catch(() => {});
    } else {
      audio.pause();
    }
  });

  wave.addEventListener('click', (event) => {
    if (!audio.duration) {
      return;
    }
    const bounds = wave.getBoundingClientRect();
    audio.currentTime = ((event.clientX - bounds.left) / bounds.width) * audio.duration;
    render();
  });

  return {
    element,
    play: () => audio.play().catch(() => {}),
    destroy: () => {
      audio.pause();
      if (frame) {
        cancelAnimationFrame(frame);
      }
      URL.revokeObjectURL(url);
    },
  };
}

// ── Voice library, kept in sync with the CLI ──

async function refreshVoices() {
  try {
    const response = await request('/api/voices');
    const data = await response.json();
    const signature = JSON.stringify(data);

    // The CLI writes to the same library, so poll and re-render only on change.
    if (signature === state.librarySignature) {
      return;
    }

    state.librarySignature = signature;
    state.voices = data.voices;
    state.invalid = data.invalid;

    if (state.selectedVoiceId !== BUILT_IN_ID && !selectedVoice()) {
      selectVoice(BUILT_IN_ID);
    }

    renderPicker();
    renderVoiceGrid();
    $('nav-voice-count').textContent = state.voices.length || '';
    setStatus($('voices-status'), '');
  } catch (error) {
    setStatus($('voices-status'), error.message, true);
  }
}

function startSync() {
  refreshVoices();
  setInterval(() => {
    if (document.visibilityState === 'visible') {
      refreshVoices();
    }
  }, SYNC_INTERVAL_MS);
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') {
      refreshVoices();
    }
  });
}

// ── Voice picker ──

function pickerOption(voiceId, name, detail) {
  const option = document.createElement('button');
  option.type = 'button';
  option.className = 'picker-option';
  option.setAttribute('role', 'option');
  option.setAttribute('aria-selected', String(voiceId === state.selectedVoiceId));

  const avatar = document.createElement('span');
  avatar.className = 'avatar';
  paintAvatar(avatar, voiceId);

  const text = document.createElement('span');
  text.className = 'picker-option-text';
  const title = document.createElement('span');
  title.textContent = name;
  const small = document.createElement('small');
  small.textContent = detail;
  text.append(title, small);

  option.append(avatar, text, svg(ICONS.check));
  option.addEventListener('click', () => {
    selectVoice(voiceId);
    closePicker();
    $('picker-button').focus();
  });
  return option;
}

function pickerGroup(label) {
  const heading = document.createElement('div');
  heading.className = 'picker-group';
  heading.textContent = label;
  return heading;
}

function renderPicker() {
  const options = $('picker-options');
  options.innerHTML = '';
  options.append(
    pickerGroup('Built-in'),
    pickerOption(BUILT_IN_ID, 'Default voice', 'Kokoro · fast, not cloned'),
  );

  if (state.voices.length > 0) {
    options.appendChild(pickerGroup('Your voices'));

    for (const voice of state.voices) {
      const review = isReviewed(voice) ? '' : ' · needs review';
      options.appendChild(
        pickerOption(voice.id, voice.display_name, `Cloned · ${voice.duration_seconds.toFixed(1)} s clip${review}`),
      );
    }
  }

  const voice = selectedVoice();
  $('picker-name').textContent = voice ? voice.display_name : 'Default voice';
  paintAvatar($('picker-avatar'), state.selectedVoiceId);
  $('speak-text').placeholder = voice
    ? `Type something for ${voice.display_name} to say...`
    : 'Type something to say...';
}

function selectVoice(voiceId) {
  state.selectedVoiceId = voiceId;
  writeSetting('vox.voice', voiceId);
  renderPicker();
}

function openPicker() {
  $('picker-menu').hidden = false;
  $('picker-button').setAttribute('aria-expanded', 'true');
  const selected = $('picker-options').querySelector('[aria-selected="true"]');
  (selected || $('picker-options').querySelector('.picker-option'))?.focus();
}

function closePicker() {
  $('picker-menu').hidden = true;
  $('picker-button').setAttribute('aria-expanded', 'false');
}

function initPicker() {
  $('picker-button').addEventListener('click', () => {
    if ($('picker-menu').hidden) {
      openPicker();
    } else {
      closePicker();
    }
  });

  document.addEventListener('click', (event) => {
    if (!$('voice-picker').contains(event.target)) {
      closePicker();
    }
  });

  $('voice-picker').addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
      closePicker();
      $('picker-button').focus();
      return;
    }

    if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') {
      return;
    }

    event.preventDefault();
    const options = [...$('picker-options').querySelectorAll('.picker-option')];
    const current = options.indexOf(document.activeElement);
    const step = event.key === 'ArrowDown' ? 1 : -1;
    options[(current + step + options.length) % options.length]?.focus();
  });
}

// ── Studio ──

function updateCharCount() {
  $('char-count').textContent = `${$('speak-text').value.length} / 2000`;
}

async function generateSpeech(event) {
  event.preventDefault();

  const text = $('speak-text').value.trim();
  const button = $('generate-button');
  const status = $('speak-status');

  if (!text || button.classList.contains('busy')) {
    if (!text) {
      $('speak-text').focus();
    }
    return;
  }

  const voice = selectedVoice();
  const started = performance.now();
  const describe = () => {
    const seconds = Math.round((performance.now() - started) / 1000);
    return voice
      ? `Cloning ${voice.display_name}... ${seconds}s (loading the model takes about 20s)`
      : `Generating with the default voice... ${seconds}s`;
  };

  button.classList.add('busy');
  button.setAttribute('aria-label', 'Generating speech');
  setStatus(status, describe());
  const timer = setInterval(() => setStatus(status, describe()), 1000);

  try {
    const response = await request('/api/speech', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, voice_id: voice ? voice.id : null }),
    });
    const blob = await response.blob();

    state.resultPlayer?.destroy();
    state.resultPlayer = createPlayer(blob, {
      downloadName: `vox-${voice ? voice.id : 'default'}-${Date.now()}.wav`,
    });
    $('speak-result').replaceChildren(state.resultPlayer.element);
    $('speak-result').hidden = false;
    setStatus(status, '');
    state.resultPlayer.play();
  } catch (error) {
    setStatus(status, error.message, true);
  } finally {
    clearInterval(timer);
    button.classList.remove('busy');
    button.setAttribute('aria-label', 'Generate speech');
  }
}

function initStudio() {
  $('speak-form').addEventListener('submit', generateSpeech);
  $('speak-text').addEventListener('input', updateCharCount);
  $('speak-text').addEventListener('keydown', (event) => {
    if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
      $('speak-form').requestSubmit();
    }
  });
  updateCharCount();
}

// ── Voices page ──

function renderVoiceGrid() {
  const grid = $('voice-grid');
  grid.innerHTML = '';

  if (state.voices.length === 0 && state.invalid.length === 0) {
    const empty = document.createElement('div');
    empty.className = 'empty-state';
    empty.innerHTML = 'No voices yet. Add one here, or run <code>vox voices add</code>.';
    grid.appendChild(empty);
    return;
  }

  for (const voice of state.voices) {
    const card = document.createElement('article');
    card.className = 'voice-card';

    const head = document.createElement('div');
    head.className = 'voice-card-head';
    const avatar = document.createElement('span');
    avatar.className = 'avatar large';
    paintAvatar(avatar, voice.id);
    const text = document.createElement('div');
    const name = document.createElement('strong');
    name.textContent = voice.display_name;
    const meta = document.createElement('small');
    meta.textContent = `${voice.id} · ${voice.duration_seconds.toFixed(1)} s clip`;
    text.append(name, meta);
    head.append(avatar, text, deleteButton(voice.id, voice.display_name));

    const badges = document.createElement('p');
    badges.className = 'badge-row';
    badges.appendChild(createBadge(voice));
    if (voice.transcript_generated) {
      badges.append('Drafted by Whisper');
    }

    const actions = document.createElement('div');
    actions.className = 'voice-card-actions';
    const review = document.createElement('button');
    review.type = 'button';
    review.className = 'button ghost';
    review.textContent = 'Review';
    review.addEventListener('click', () => openReview(voice.id));
    const use = document.createElement('button');
    use.type = 'button';
    use.className = 'button primary';
    use.textContent = 'Use in Studio';
    use.addEventListener('click', () => {
      selectVoice(voice.id);
      location.hash = '#/studio';
      $('speak-text').focus();
    });
    actions.append(review, use);

    card.append(head, badges, actions);
    grid.appendChild(card);
  }

  for (const invalid of state.invalid) {
    const card = document.createElement('article');
    card.className = 'voice-card invalid';
    const head = document.createElement('div');
    head.className = 'voice-card-head';
    const name = document.createElement('strong');
    name.textContent = `${invalid.id} · unusable`;
    head.append(name, deleteButton(invalid.id, invalid.id));
    const reason = document.createElement('small');
    reason.textContent = invalid.reason;
    card.append(head, reason);
    grid.appendChild(card);
  }
}

function deleteButton(voiceId, displayName) {
  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'icon-button';
  button.title = 'Delete voice';
  button.setAttribute('aria-label', `Delete ${displayName}`);
  button.appendChild(svg(ICONS.trash));
  button.addEventListener('click', () => openDelete(voiceId, displayName));
  return button;
}

// ── Delete voice ──

function openDelete(voiceId, displayName) {
  state.deletingVoiceId = voiceId;
  $('delete-title').textContent = `Delete ${displayName}?`;
  paintAvatar($('delete-avatar'), voiceId);
  setStatus($('delete-status'), '');
  $('delete-dialog').showModal();
}

async function confirmDelete(event) {
  event.preventDefault();

  const dialog = $('delete-dialog');
  const voiceId = state.deletingVoiceId;
  setModalBusy(dialog, true);
  $('delete-button-label').textContent = 'Deleting...';
  setStatus($('delete-status'), '');

  try {
    await request(`/api/voices/${encodeURIComponent(voiceId)}`, { method: 'DELETE' });
    setModalBusy(dialog, false);
    dialog.close();
    showToast('Voice deleted.');

    if (state.reviewingVoiceId === voiceId) {
      $('review-dialog').close();
    }

    await refreshVoices();
  } catch (error) {
    setModalBusy(dialog, false);
    setStatus($('delete-status'), error.message, true);
  } finally {
    $('delete-button-label').textContent = 'Delete voice';
  }
}

function initDelete() {
  $('delete-form').addEventListener('submit', confirmDelete);
  $('delete-dialog').addEventListener('close', () => {
    state.deletingVoiceId = null;
  });
}

// ── Add voice ──

function showChosenFile() {
  const file = $('add-audio').files[0];
  $('dropzone').classList.toggle('has-file', Boolean(file));
  $('dropzone-title').textContent = file ? file.name : 'Drop a recording or click to choose';
  $('dropzone-hint').textContent = file
    ? `${(file.size / 1024 / 1024).toFixed(1)} MB · click to choose a different file`
    : 'About 15 seconds of one person speaking clearly. Any audio format.';
}

function resetAddForm() {
  $('add-form').reset();
  showChosenFile();
  setStatus($('add-status'), '');
}

async function addVoice(event) {
  event.preventDefault();

  const dialog = $('add-dialog');
  const formData = new FormData($('add-form'));
  const hasTranscript = String(formData.get('transcript') || '').trim() !== '';
  const started = performance.now();
  const describe = () => {
    const seconds = Math.round((performance.now() - started) / 1000);
    const work = hasTranscript
      ? 'Converting and saving the recording'
      : 'Converting the recording and drafting a transcript with Whisper';
    return `${work}... ${seconds}s`;
  };

  // Read the form before disabling it: disabled fields are left out of FormData.
  setModalBusy(dialog, true);
  $('add-button-label').textContent = 'Saving...';
  setStatus($('add-status'), describe());
  const timer = setInterval(() => setStatus($('add-status'), describe()), 1000);

  try {
    const response = await request('/api/voices', { method: 'POST', body: formData });
    const voice = await response.json();
    setModalBusy(dialog, false);
    dialog.close();
    resetAddForm();
    await refreshVoices();

    // Review is the quality gate: go straight to it for a Whisper draft.
    if (isReviewed(voice)) {
      showToast(`Added ${voice.display_name}.`);
    } else {
      openReview(voice.id);
    }
  } catch (error) {
    setModalBusy(dialog, false);
    setStatus($('add-status'), error.message, true);
  } finally {
    clearInterval(timer);
    $('add-button-label').textContent = 'Add voice';
  }
}

function initAddVoice() {
  const dropzone = $('dropzone');

  $('open-add-voice').addEventListener('click', () => {
    resetAddForm();
    $('add-dialog').showModal();
  });
  $('add-audio').addEventListener('change', showChosenFile);
  $('add-form').addEventListener('submit', addVoice);

  dropzone.addEventListener('dragover', (event) => {
    event.preventDefault();
    dropzone.classList.add('dragging');
  });
  dropzone.addEventListener('dragleave', () => dropzone.classList.remove('dragging'));
  dropzone.addEventListener('drop', (event) => {
    event.preventDefault();
    dropzone.classList.remove('dragging');
    if (event.dataTransfer.files.length > 0) {
      $('add-audio').files = event.dataTransfer.files;
      showChosenFile();
    }
  });
}

// ── Review transcript ──

async function openReview(voiceId) {
  const voice = state.voices.find((candidate) => candidate.id === voiceId);

  if (!voice) {
    return;
  }

  state.reviewingVoiceId = voiceId;
  $('review-title').textContent = voice.display_name;
  paintAvatar($('review-avatar'), voice.id);
  $('review-transcript').value = voice.transcript;
  setStatus($('review-status'), '');

  const source = $('review-source');
  source.replaceChildren(createBadge(voice));
  if (voice.transcript_generated) {
    source.append('Drafted by Whisper');
  }

  state.reviewPlayer?.destroy();
  state.reviewPlayer = null;
  $('review-player').replaceChildren();

  if (!$('review-dialog').open) {
    $('review-dialog').showModal();
  }

  try {
    const response = await request(voice.reference_url);
    state.reviewPlayer = createPlayer(await response.blob());
    $('review-player').replaceChildren(state.reviewPlayer.element);
  } catch (error) {
    setStatus($('review-status'), error.message, true);
  }
}

async function saveReview(event) {
  event.preventDefault();

  const dialog = $('review-dialog');
  const voiceId = state.reviewingVoiceId;
  const transcript = $('review-transcript').value;
  setModalBusy(dialog, true);
  setStatus($('review-status'), 'Saving...');

  try {
    const response = await request(`/api/voices/${encodeURIComponent(voiceId)}/transcript`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ transcript }),
    });
    const voice = await response.json();
    setModalBusy(dialog, false);
    dialog.close();
    showToast(`Saved ${voice.display_name}'s transcript.`);
    await refreshVoices();
  } catch (error) {
    setModalBusy(dialog, false);
    setStatus($('review-status'), error.message, true);
  }
}

function initReview() {
  $('review-form').addEventListener('submit', saveReview);
  $('review-dialog').addEventListener('close', () => {
    state.reviewPlayer?.destroy();
    state.reviewPlayer = null;
    state.reviewingVoiceId = null;
  });
}

// ── Help ──

function initHelp() {
  // Section links scroll in place; changing the hash would switch pages.
  for (const link of document.querySelectorAll('.help-toc a')) {
    link.addEventListener('click', (event) => {
      event.preventDefault();
      document.querySelector(link.getAttribute('href'))?.scrollIntoView({ behavior: 'smooth' });
    });
  }

  for (const button of document.querySelectorAll('.try-example')) {
    button.addEventListener('click', () => {
      const example = button.closest('.example').querySelector('.example-pair > div:last-child p');
      $('speak-text').value = example.textContent;
      updateCharCount();
      location.hash = '#/studio';
      $('speak-text').focus();
    });
  }
}

// ── Start ──

document.addEventListener('DOMContentLoaded', () => {
  for (const closeButton of document.querySelectorAll('[data-close]')) {
    closeButton.addEventListener('click', () => closeButton.closest('dialog').close());
  }

  for (const dialog of document.querySelectorAll('dialog')) {
    // Escape would otherwise close a modal halfway through saving.
    dialog.addEventListener('cancel', (event) => {
      if (dialog.dataset.busy) {
        event.preventDefault();
      }
    });
  }

  initTheme();
  initPicker();
  initStudio();
  initAddVoice();
  initReview();
  initDelete();
  initHelp();
  renderPicker();
  window.addEventListener('hashchange', showRoute);
  showRoute();
  startSync();
});
