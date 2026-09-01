let wavesurfer = null;
let wsRegions = null;
let currentRegion = null;
let regionTimeUpdateHandler = null;

let currentPresets = {};
let activeCharId = "";
let selectedCharId = null;

let isRecording = false;
let mediaRecorder = null;
let audioChunks = [];
let recordInterval = null;
let recordSeconds = 0;

let stitcherFiles = [];
let draftVoiceBlob = null;
let originalRawFileBlob = null;
let currentDraftAvatarBase64 = "";

let isDirty = false;
let isLoadingPreset = false;
let dynamicPreviewTimers = [];
let statusPollInterval = null;

let sidebarAudioPlayer = new Audio();

function setDirty(val = true) {
  if (isLoadingPreset) return;
  isDirty = val;
}

function clearDynamicTimers() {
  dynamicPreviewTimers.forEach(t => clearTimeout(t));
  dynamicPreviewTimers = [];
}

function hexToRgba(hex, alpha) {
  let r = parseInt(hex.slice(1, 3), 16) || 0;
  let g = parseInt(hex.slice(3, 5), 16) || 0;
  let b = parseInt(hex.slice(5, 7), 16) || 0;
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

function copySnippetText(text) {
  navigator.clipboard.writeText(text);
  alert('Скрипт скопирован в буфер обмена!');
}

function switchToCharactersTab() {
  const tabChars = document.getElementById('tab-btn-characters');
  const tabSettings = document.getElementById('tab-btn-settings');
  const viewChars = document.getElementById('view-characters');
  const viewSettings = document.getElementById('view-settings');

  if (tabChars && tabSettings && viewChars && viewSettings) {
    tabChars.classList.add('active');
    tabSettings.classList.remove('active');
    viewChars.classList.remove('hidden');
    viewSettings.classList.add('hidden');
  }
}

// ==================== КОНВЕРТЕР AUDIOBUFFER -> WAV BLOB ====================
function audioBufferToWav(buffer) {
  const numChannels = buffer.numberOfChannels;
  const sampleRate = buffer.sampleRate;
  const format = 1; // PCM
  const bitDepth = 16;
  
  let result;
  if (numChannels === 2) {
    const channel1 = buffer.getChannelData(0);
    const channel2 = buffer.getChannelData(1);
    const length = channel1.length + channel2.length;
    result = new Float32Array(length);
    let index = 0;
    let inputIndex = 0;
    while (index < length) {
      result[index++] = channel1[inputIndex];
      result[index++] = channel2[inputIndex];
      inputIndex++;
    }
  } else {
    result = buffer.getChannelData(0);
  }

  const bytesPerSample = bitDepth / 8;
  const blockAlign = numChannels * bytesPerSample;
  const bufferLength = result.length * bytesPerSample;
  const wavBuffer = new ArrayBuffer(44 + bufferLength);
  const view = new DataView(wavBuffer);

  function writeString(view, offset, string) {
    for (let i = 0; i < string.length; i++) {
      view.setUint8(offset + i, string.charCodeAt(i));
    }
  }

  writeString(view, 0, 'RIFF');
  view.setUint32(4, 36 + bufferLength, true);
  writeString(view, 8, 'WAVE');
  writeString(view, 12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, format, true);
  view.setUint16(22, numChannels, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * blockAlign, true);
  view.setUint16(32, blockAlign, true);
  view.setUint16(34, bitDepth, true);
  writeString(view, 36, 'data');
  view.setUint32(40, bufferLength, true);

  let offset = 44;
  for (let i = 0; i < result.length; i++, offset += 2) {
    const s = Math.max(-1, Math.min(1, result[i]));
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
  }

  return new Blob([wavBuffer], { type: 'audio/wav' });
}

function getDraftTheme() {
  let avatarUrl = "";
  const staticAvatarBox = document.getElementById('static-avatar-box');

  if (staticAvatarBox && !staticAvatarBox.classList.contains('hidden')) {
    if (currentDraftAvatarBase64) {
      avatarUrl = currentDraftAvatarBase64;
    } else if (selectedCharId) {
      avatarUrl = `/char_files/${selectedCharId}/avatar.png?_t=${Date.now()}`;
    }
  }

  return {
    name: document.getElementById('char-name').value.trim() || 'Персонаж',
    avatar: avatarUrl,
    theme: {
      border_color: document.getElementById('border-color').value,
      bg_color: document.getElementById('bg-color').value,
      text_color: document.getElementById('text-color').value,
      name_bg_color: document.getElementById('name-bg-color').value,
      name_text_color: document.getElementById('name-text-color').value,
      bg_opacity: parseFloat(document.getElementById('bg-opacity-slider').value),
      hide_delay: parseFloat(document.getElementById('hide-delay-slider').value),
      avatar_position: document.getElementById('avatar-position').value,
      box_shape: document.getElementById('box-shape').value,
      border_fx: document.getElementById('border-fx').value,
      font_family: document.getElementById('font-family').value,
      font_size: parseInt(document.getElementById('font-size-slider').value, 10),
      entrance_animation: document.getElementById('entrance-animation').value,
      exit_animation: document.getElementById('exit-animation').value,
      text_animation: document.getElementById('text-animation').value
    }
  };
}

// ==================== ИНИЦИАЛИЗАЦИЯ И НАСТРОЙКИ ====================

async function initCustomFonts() {
  try {
    const res = await fetch('/api/fonts');
    const data = await res.json();
    const optgroup = document.getElementById('custom-fonts-optgroup');
    if (!optgroup) return;
    optgroup.innerHTML = '';

    if (data.custom_fonts && data.custom_fonts.length > 0) {
      let fontStyles = '';
      data.custom_fonts.forEach(font => {
        fontStyles += `
          @font-face {
            font-family: '${font.name}';
            src: url('${font.url}') format('truetype');
          }
        `;
        const opt = document.createElement('option');
        opt.value = font.name;
        opt.textContent = `📁 ${font.name}`;
        optgroup.appendChild(opt);
      });

      const styleEl = document.createElement('style');
      styleEl.textContent = fontStyles;
      document.head.appendChild(styleEl);
      await document.fonts.ready;
    }
  } catch (e) {}
}

async function uploadCustomFont(file) {
  const fd = new FormData();
  fd.append('file', file);
  try {
    const res = await fetch('/api/upload_font', { method: 'POST', body: fd });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Ошибка загрузки шрифта');
    await initCustomFonts();
    document.getElementById('font-family').value = data.name;
    updatePreviews();
    setDirty(true);
  } catch (e) {
    alert(e.message);
  }
}

async function loadSystemConfig() {
  try {
    const res = await fetch('/api/system_config');
    const data = await res.json();
    const cfg = data.config || {};

    document.getElementById('cfg-host').value = cfg.host || '127.0.0.1';
    document.getElementById('cfg-port').value = cfg.port || 8765;
    document.getElementById('cfg-timesteps').value = cfg.n_timesteps || 6;
    document.getElementById('cfg-timesteps-val').innerText = `${cfg.n_timesteps || 6} шагов`;
    document.getElementById('cfg-auto-open').checked = cfg.auto_open_browser !== false;

    updateObsStatusBadge(data.obs_connected);
  } catch (e) {}
}

async function loadDonationAlertsConfig() {
  try {
    const res = await fetch('/api/da/config');
    const data = await res.json();
    const cfg = data.config || {};

    document.getElementById('da-cfg-enabled').checked = cfg.enabled === true;
    document.getElementById('da-cfg-client-id').value = cfg.client_id || '';
    document.getElementById('da-cfg-client-secret').value = cfg.client_secret || '';
    document.getElementById('da-cfg-sb-url').value = cfg.streamerbot_url || 'http://127.0.0.1:7474/DoAction';
    document.getElementById('da-cfg-sb-action').value = cfg.streamerbot_action || 'Donation';
    document.getElementById('da-redirect-uri').value = data.redirect_uri || '';

    updateDaStatusBadge(data.is_connected, data.authorized_user, data.last_error);
  } catch (e) {}
}

function updateObsStatusBadge(connected) {
  const badge = document.getElementById('obs-status-badge');
  if (!badge) return;
  if (connected) {
    badge.className = 'badge-online';
    badge.innerText = '🟢 OBS подключен';
  } else {
    badge.className = 'badge-offline';
    badge.innerText = '⚫ Ожидание подключения';
  }
}

function updateDaStatusBadge(connected, user, lastError) {
  const badge = document.getElementById('da-status-badge');
  const userBadge = document.getElementById('da-user-badge');
  if (!badge || !userBadge) return;

  if (user) {
    userBadge.innerText = user;
    userBadge.style.color = '#10b981';
  } else {
    userBadge.innerText = 'Не авторизован';
    userBadge.style.color = '#9d99ab';
  }

  if (connected) {
    badge.className = 'badge-online';
    badge.innerText = '🟢 Активен (WS Connected)';
  } else {
    badge.className = 'badge-offline';
    badge.innerText = lastError ? `⚫ Ошибка (${lastError})` : '⚫ Отключен';
  }
}

async function pollSystemStatus() {
  try {
    const res = await fetch('/api/system_config');
    const data = await res.json();
    updateObsStatusBadge(data.obs_connected);

    const resDa = await fetch('/api/da/config');
    const dataDa = await resDa.json();
    updateDaStatusBadge(dataDa.is_connected, dataDa.authorized_user, dataDa.last_error);
  } catch (e) {}
}

async function saveSystemConfig() {
  const payload = {
    host: document.getElementById('cfg-host').value,
    port: parseInt(document.getElementById('cfg-port').value, 10) || 8765,
    n_timesteps: parseInt(document.getElementById('cfg-timesteps').value, 10) || 6,
    auto_open_browser: document.getElementById('cfg-auto-open').checked
  };

  try {
    const res = await fetch('/api/system_config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    if (!res.ok) throw new Error('Ошибка сохранения настроек');
    alert('Системные настройки успешно сохранены!\n(Смена порта вступит в силу при перезапуске сервера)');
  } catch (e) {
    alert(e.message);
  }
}

async function saveDaConfig() {
  const payload = {
    enabled: document.getElementById('da-cfg-enabled').checked,
    client_id: document.getElementById('da-cfg-client-id').value.trim(),
    client_secret: document.getElementById('da-cfg-client-secret').value.trim(),
    streamerbot_url: document.getElementById('da-cfg-sb-url').value.trim(),
    streamerbot_action: document.getElementById('da-cfg-sb-action').value.trim()
  };

  try {
    const res = await fetch('/api/da/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    if (!res.ok) throw new Error('Ошибка сохранения настроек DonationAlerts');
    alert('Настройки DonationAlerts сохранены!');
    await loadDonationAlertsConfig();
  } catch (e) {
    alert(e.message);
  }
}

// ==================== WAVESURFER ====================

function initWavesurfer() {
  if (wavesurfer) return;

  wavesurfer = WaveSurfer.create({
    container: '#waveform',
    waveColor: '#4f46e5',
    progressColor: '#818cf8',
    cursorColor: '#ffffff',
    cursorWidth: 2,
    height: 75,
    normalize: false
  });

  wsRegions = wavesurfer.registerPlugin(WaveSurfer.Regions.create());

  wsRegions.on('region-updated', (region) => {
    currentRegion = region;
    updateRegionTimeInfo();
  });

  wsRegions.on('region-clicked', (region, e) => {
    e.stopPropagation();
    currentRegion = region;
    togglePlayRegion();
  });

  wavesurfer.on('pause', () => {
    const playBtn = document.getElementById('btn-play-region');
    if (playBtn) playBtn.innerText = '▶ Слушать';
    if (regionTimeUpdateHandler) {
      wavesurfer.un('timeupdate', regionTimeUpdateHandler);
      regionTimeUpdateHandler = null;
    }
  });

  wavesurfer.on('interaction', () => {
    togglePlayRegion();
  });
}

function updateRegionTimeInfo() {
  const info = document.getElementById('region-time-info');
  if (!info) return;
  if (currentRegion) {
    const dur = currentRegion.end - currentRegion.start;
    let badgeColor = '#10b981';
    let badgeText = 'Оптимально';

    if (dur < 2.0) {
      badgeColor = '#ef4444';
      badgeText = 'Слишком коротко (<2с)';
    } else if (dur >= 2.0 && dur < 3.0) {
      badgeColor = '#f59e0b';
      badgeText = 'Короткий сэмпл';
    } else if (dur > 10.0 && dur <= 14.0) {
      badgeColor = '#f59e0b';
      badgeText = 'Длинный сэмпл';
    } else if (dur > 14.0) {
      badgeColor = '#ef4444';
      badgeText = 'Слишком длинно (>14с)';
    }

    info.innerHTML = `${currentRegion.start.toFixed(1)}с - ${currentRegion.end.toFixed(1)}с (${dur.toFixed(1)}с) <span style="color:${badgeColor}; font-weight:700; margin-left:6px;">[${badgeText}]</span>`;
  } else {
    info.innerText = 'Выделите область для обрезки';
  }
}

function togglePlayRegion() {
  if (!wavesurfer) return;

  const playBtn = document.getElementById('btn-play-region');

  if (wavesurfer.isPlaying()) {
    wavesurfer.pause();
    if (playBtn) playBtn.innerText = '▶ Слушать';
    if (regionTimeUpdateHandler) {
      wavesurfer.un('timeupdate', regionTimeUpdateHandler);
      regionTimeUpdateHandler = null;
    }
    return;
  }

  if (!currentRegion) {
    wavesurfer.play();
    if (playBtn) playBtn.innerText = '⏸ Пауза';
    return;
  }

  if (regionTimeUpdateHandler) {
    wavesurfer.un('timeupdate', regionTimeUpdateHandler);
  }

  wavesurfer.setTime(currentRegion.start);
  wavesurfer.play();
  if (playBtn) playBtn.innerText = '⏸ Пауза';

  regionTimeUpdateHandler = () => {
    if (wavesurfer.getCurrentTime() >= currentRegion.end) {
      wavesurfer.pause();
      wavesurfer.setTime(currentRegion.start);
      if (playBtn) playBtn.innerText = '▶ Слушать';
      wavesurfer.un('timeupdate', regionTimeUpdateHandler);
      regionTimeUpdateHandler = null;
    }
  };

  wavesurfer.on('timeupdate', regionTimeUpdateHandler);
}

function loadAudioToWaveSurfer(blobOrUrl) {
  initWavesurfer();
  document.getElementById('waveform-container').classList.remove('hidden');

  wavesurfer.load(blobOrUrl);
  wavesurfer.once('ready', () => {
    wsRegions.clearRegions();
    const duration = wavesurfer.getDuration();
    const regEnd = Math.min(duration, 5.5);
    currentRegion = wsRegions.addRegion({
      start: 0,
      end: regEnd,
      color: 'rgba(99, 102, 241, 0.3)',
      drag: true,
      resize: true
    });
    updateRegionTimeInfo();
  });
}

// ==================== ЗАГРУЗКА И РЕНДЕР ПРЕСЕТОВ ====================

async function loadPresetsList() {
  try {
    const res = await fetch('/api/presets');
    const data = await res.json();
    currentPresets = data.presets || {};
    activeCharId = data.active || "";

    renderSidebar();
    if (typeof updateGeneratorCharacterDropdown === 'function') {
      updateGeneratorCharacterDropdown();
    }

    if (!selectedCharId || !currentPresets[selectedCharId]) {
      if (activeCharId && currentPresets[activeCharId]) {
        selectCharacter(activeCharId);
      } else {
        const keys = Object.keys(currentPresets);
        if (keys.length > 0) selectCharacter(keys[0]);
        else createNewCharacter();
      }
    } else {
      selectCharacter(selectedCharId);
    }
  } catch (e) {
    console.error(e);
  }
}

function renderSidebar() {
  const container = document.getElementById('character-list');
  if (!container) return;
  container.innerHTML = '';

  Object.keys(currentPresets).forEach(id => {
    const item = currentPresets[id];
    const el = document.createElement('div');
    el.className = `char-item ${id === activeCharId ? 'active-preset' : ''} ${id === selectedCharId ? 'selected' : ''}`;

    let avatarHtml = '';
    if (item.has_avatar && item.avatar_url) {
      avatarHtml = `<img src="${item.avatar_url}?_t=${Date.now()}" class="char-sidebar-avatar" alt="${item.name}">`;
    } else {
      avatarHtml = `<div class="char-sidebar-avatar-placeholder">👤</div>`;
    }

    el.innerHTML = `
      <div class="char-item-left">
        ${avatarHtml}
        <div class="char-item-info">
          <span class="char-item-name">${item.name || id}</span>
          <span class="char-badge">
            <span class="active-dot"></span>
            ${id === activeCharId ? 'Активен' : id}
          </span>
        </div>
      </div>
      <div class="char-actions-right">
        <button class="btn-quick-play" title="Прослушать сэмпл голоса" data-char-id="${id}">▶</button>
      </div>
    `;

    el.addEventListener('click', (e) => {
      if (e.target.classList.contains('btn-quick-play')) return;
      if (isDirty && selectedCharId !== id) {
        if (!confirm('У вас есть несохраненные изменения! Переключить персонажа?')) return;
      }
      selectCharacter(id);
    });

    const playBtn = el.querySelector('.btn-quick-play');
    playBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      const rawVoicePath = `/char_files/${id}/voice.wav`;
      
      document.querySelectorAll('.btn-quick-play').forEach(btn => {
        if (btn !== playBtn) btn.innerText = '▶';
      });

      if (sidebarAudioPlayer.dataset.charId === id && !sidebarAudioPlayer.paused) {
        sidebarAudioPlayer.pause();
        playBtn.innerText = '▶';
      } else if (sidebarAudioPlayer.dataset.charId === id && sidebarAudioPlayer.paused && sidebarAudioPlayer.src) {
        sidebarAudioPlayer.play();
        playBtn.innerText = '⏸';
      } else {
        sidebarAudioPlayer.dataset.charId = id;
        sidebarAudioPlayer.src = `${rawVoicePath}?_t=${Date.now()}`;
        sidebarAudioPlayer.play();
        playBtn.innerText = '⏸';
        
        sidebarAudioPlayer.onended = () => {
          playBtn.innerText = '▶';
          sidebarAudioPlayer.dataset.charId = "";
        };
        sidebarAudioPlayer.onpause = () => {
          playBtn.innerText = '▶';
        };
      }
    });

    container.appendChild(el);
  });
}

async function selectCharacter(id) {
  switchToCharactersTab();

  if (sidebarAudioPlayer && !sidebarAudioPlayer.paused) {
    sidebarAudioPlayer.pause();
    document.querySelectorAll('.btn-quick-play').forEach(btn => btn.innerText = '▶');
  }

  isLoadingPreset = true;
  selectedCharId = id;
  currentDraftAvatarBase64 = "";

  const data = currentPresets[id];
  if (!data) {
    isLoadingPreset = false;
    return;
  }

  document.getElementById('editor-title').innerText = `Настройка: ${data.name || id}`;
  document.getElementById('editor-mode-badge').innerText = 'Режим редактирования';
  document.getElementById('char-id').value = id;
  document.getElementById('char-id').disabled = true;
  document.getElementById('char-name').value = data.name || '';
  document.getElementById('ref-text').value = data.reference_text || '';
  document.getElementById('speed-slider').value = data.speed !== undefined ? data.speed : 1.0;
  document.getElementById('speed-val').innerText = `${document.getElementById('speed-slider').value}x`;

  const theme = data.theme || {};
  document.getElementById('border-color').value = theme.border_color || '#6366f1';
  document.getElementById('bg-color').value = theme.bg_color || '#0d0b14';
  document.getElementById('text-color').value = theme.text_color || '#fcebeb';
  document.getElementById('name-bg-color').value = theme.name_bg_color || '#6366f1';
  document.getElementById('name-text-color').value = theme.name_text_color || '#ffffff';
  document.getElementById('bg-opacity-slider').value = theme.bg_opacity !== undefined ? theme.bg_opacity : 0.9;
  document.getElementById('bg-opacity-val').innerText = `${Math.round(document.getElementById('bg-opacity-slider').value * 100)}%`;
  document.getElementById('hide-delay-slider').value = theme.hide_delay !== undefined ? theme.hide_delay : 2.0;
  document.getElementById('hide-delay-val').innerText = `${parseFloat(document.getElementById('hide-delay-slider').value).toFixed(1)}с`;

  document.getElementById('box-shape').value = theme.box_shape || 'shape-rounded';
  document.getElementById('border-fx').value = theme.border_fx || 'fx-neon';
  document.getElementById('font-family').value = theme.font_family || 'Comfortaa';
  document.getElementById('font-size-slider').value = theme.font_size || 22;
  document.getElementById('font-size-val').innerText = `${document.getElementById('font-size-slider').value}px`;
  document.getElementById('entrance-animation').value = theme.entrance_animation || 'slide-up';
  document.getElementById('exit-animation').value = theme.exit_animation || 'fade-out';
  document.getElementById('text-animation').value = theme.text_animation || 'typewriter';
  document.getElementById('avatar-position').value = theme.avatar_position || 'left';

  const btnSetActive = document.getElementById('btn-set-active');
  if (id === activeCharId) {
    btnSetActive.disabled = true;
    btnSetActive.innerText = '✓ Активен';
  } else {
    btnSetActive.disabled = false;
    btnSetActive.innerText = 'Сделать активным';
  }

  draftVoiceBlob = null;
  originalRawFileBlob = null;
  stitcherFiles = [];
  document.getElementById('stitcher-container').classList.add('hidden');
  document.getElementById('btn-restore-noise').classList.add('hidden');
  document.getElementById('voice-file-input').value = '';
  document.getElementById('avatar-file-input').value = '';

  const voiceUrl = `/char_files/${id}/voice.wav?_t=${Date.now()}`;
  loadAudioToWaveSurfer(voiceUrl);

  try {
    const resAudio = await fetch(voiceUrl);
    if (resAudio.ok) {
      originalRawFileBlob = await resAudio.blob();
    }
  } catch (e) {}

  const staticAvatar = document.getElementById('static-avatar');
  const dynamicAvatar = document.getElementById('dynamic-avatar');
  const staticAvatarBox = document.getElementById('static-avatar-box');
  const dynamicAvatarBox = document.getElementById('dynamic-avatar-box');

  if (data.has_avatar) {
    const avatarUrl = `/char_files/${id}/avatar.png?_t=${Date.now()}`;
    staticAvatar.src = avatarUrl;
    dynamicAvatar.src = avatarUrl;
    staticAvatarBox.classList.remove('hidden');
    dynamicAvatarBox.classList.remove('hidden');
  } else {
    staticAvatar.src = '';
    dynamicAvatar.src = '';
    staticAvatarBox.classList.add('hidden');
    dynamicAvatarBox.classList.add('hidden');
  }

  updatePreviews();
  renderSidebar();

  setTimeout(() => {
    isLoadingPreset = false;
    setDirty(false);
  }, 50);
}

function createNewCharacter() {
  if (isDirty) {
    if (!confirm('У вас есть несохраненные изменения! Создать нового?')) return;
  }

  switchToCharactersTab();

  isLoadingPreset = true;
  selectedCharId = null;
  currentDraftAvatarBase64 = "";

  document.getElementById('editor-title').innerText = 'Создание нового персонажа';
  document.getElementById('editor-mode-badge').innerText = 'Новый пресет';
  document.getElementById('char-id').value = '';
  document.getElementById('char-id').disabled = false;
  document.getElementById('char-name').value = '';
  document.getElementById('ref-text').value = '';
  document.getElementById('speed-slider').value = 1.0;
  document.getElementById('speed-val').innerText = '1.0x';

  document.getElementById('border-color').value = '#6366f1';
  document.getElementById('bg-color').value = '#0d0b14';
  document.getElementById('text-color').value = '#fcebeb';
  document.getElementById('name-bg-color').value = '#6366f1';
  document.getElementById('name-text-color').value = '#ffffff';
  document.getElementById('bg-opacity-slider').value = 0.9;
  document.getElementById('bg-opacity-val').innerText = '90%';
  document.getElementById('hide-delay-slider').value = 2.0;
  document.getElementById('hide-delay-val').innerText = '2.0с';

  document.getElementById('box-shape').value = 'shape-rounded';
  document.getElementById('border-fx').value = 'fx-neon';
  document.getElementById('font-family').value = 'Comfortaa';
  document.getElementById('font-size-slider').value = 22;
  document.getElementById('font-size-val').innerText = '22px';
  document.getElementById('entrance-animation').value = 'slide-up';
  document.getElementById('exit-animation').value = 'fade-out';
  document.getElementById('text-animation').value = 'typewriter';
  document.getElementById('avatar-position').value = 'left';

  const btnSetActive = document.getElementById('btn-set-active');
  btnSetActive.disabled = true;
  btnSetActive.innerText = 'Сделать активным';

  draftVoiceBlob = null;
  originalRawFileBlob = null;
  stitcherFiles = [];
  document.getElementById('stitcher-container').classList.add('hidden');
  document.getElementById('waveform-container').classList.add('hidden');
  document.getElementById('btn-restore-noise').classList.add('hidden');
  document.getElementById('voice-file-input').value = '';
  document.getElementById('avatar-file-input').value = '';

  document.getElementById('static-avatar-box').classList.add('hidden');
  document.getElementById('dynamic-avatar-box').classList.add('hidden');

  updatePreviews();
  renderSidebar();

  setTimeout(() => {
    isLoadingPreset = false;
    setDirty(false);
  }, 50);
}

// ==================== ПРЕВЬЮ И АНИМАЦИИ ====================

function updatePreviews() {
  const bColor = document.getElementById('border-color').value;
  const bgHex = document.getElementById('bg-color').value;
  const bgAlpha = parseFloat(document.getElementById('bg-opacity-slider').value);
  const bgRgba = hexToRgba(bgHex, bgAlpha);
  const tColor = document.getElementById('text-color').value;
  const nBgColor = document.getElementById('name-bg-color').value;
  const nTextColor = document.getElementById('name-text-color').value;
  const charName = document.getElementById('char-name').value || 'Персонаж';
  const shape = document.getElementById('box-shape').value;
  const fx = document.getElementById('border-fx').value;
  const fontFamily = document.getElementById('font-family').value;
  
  const rawFontSize = parseInt(document.getElementById('font-size-slider').value, 10) || 22;
  const previewFontSize = `${Math.round(rawFontSize * 0.62)}px`;
  const avatarPos = document.getElementById('avatar-position').value;

  const staticBox = document.getElementById('static-dialogue-box');
  const staticName = document.getElementById('static-name-tag');
  const staticText = document.getElementById('static-text');
  const staticContainer = document.getElementById('static-overlay-box');

  if (staticContainer) {
    staticContainer.className = `overlay-container-preview ${avatarPos === 'right' ? 'avatar-right' : ''}`;
    staticBox.className = `dialogue-box ${shape} ${fx}`;
    staticBox.style.setProperty('--border-color', bColor);
    staticBox.style.borderColor = bColor;
    staticBox.style.background = bgRgba;

    staticName.innerText = charName;
    staticName.style.background = nBgColor;
    staticName.style.color = nTextColor;

    staticText.style.color = tColor;
    staticText.style.fontSize = previewFontSize;
    staticText.style.fontFamily = `"${fontFamily}", sans-serif`;
  }

  const dynBox = document.getElementById('dynamic-dialogue-box');
  const dynName = document.getElementById('dynamic-name-tag');
  const dynText = document.getElementById('dynamic-text-target');
  const dynCursor = document.getElementById('dynamic-cursor');

  if (dynBox) {
    dynBox.className = `dialogue-box ${shape} ${fx}`;
    dynBox.style.setProperty('--border-color', bColor);
    dynBox.style.borderColor = bColor;
    dynBox.style.background = bgRgba;

    dynName.innerText = charName;
    dynName.style.background = nBgColor;
    dynName.style.color = nTextColor;

    dynText.style.color = tColor;
    dynText.style.fontSize = previewFontSize;
    dynText.style.fontFamily = `"${fontFamily}", sans-serif`;
    if (dynCursor) {
      dynCursor.style.backgroundColor = '';
      dynCursor.style.height = previewFontSize;
    }
  }
}

function runDynamicOverlayPreview(fullText, durationSec = 3.5) {
  clearDynamicTimers();

  const container = document.getElementById('dynamic-overlay-container');
  const textTarget = document.getElementById('dynamic-text-target');
  let cursor = document.getElementById('dynamic-cursor');
  if (!container || !textTarget) return;

  const entrance = document.getElementById('entrance-animation').value;
  const exitAnim = document.getElementById('exit-animation').value;
  const textAnim = document.getElementById('text-animation').value;
  const avatarPos = document.getElementById('avatar-position').value;

  if (!cursor) {
    cursor = document.createElement('span');
    cursor.className = 'cursor';
    cursor.id = 'dynamic-cursor';
  }

  container.className = `overlay-container-preview anim-container anim-${entrance} ${avatarPos === 'right' ? 'avatar-right' : ''}`;
  textTarget.innerHTML = '';
  textTarget.appendChild(cursor);
  cursor.style.display = 'none';

  dynamicPreviewTimers.push(setTimeout(() => {
    container.classList.add('active');
  }, 40));

  const audioDurationMs = durationSec * 1000;
  const speechMs = audioDurationMs * 0.85;

  if (textAnim === 'instant') {
    textTarget.textContent = fullText;
    cursor.style.display = 'none';
  } else if (textAnim === 'word-fade') {
    cursor.style.display = 'none';
    const words = fullText.split(' ');
    textTarget.innerHTML = words.map(w => `<span class="word-span">${w}</span>`).join(' ');
    const spans = textTarget.querySelectorAll('.word-span');
    const wordDelay = Math.max(40, speechMs / words.length);

    spans.forEach((span, idx) => {
      dynamicPreviewTimers.push(setTimeout(() => {
        span.classList.add('visible');
      }, idx * wordDelay));
    });
  } else if (textAnim === 'wavy-text') {
    cursor.style.display = 'none';
    textTarget.innerHTML = fullText.split('').map((c, i) =>
      c === ' ' ? ' ' : `<span class="wavy-char" style="animation-delay: ${(i * 0.08) % 1.4}s">${c}</span>`
    ).join('');
  } else if (textAnim === 'glitch-decode') {
    cursor.style.display = 'none';
    const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*';
    const totalChars = fullText.length;
    let iteration = 0;
    const interval = Math.max(25, speechMs / (totalChars * 2));

    const glitchTimer = setInterval(() => {
      textTarget.innerText = fullText
        .split('')
        .map((letter, index) => {
          if (index < iteration) return letter;
          if (letter === ' ') return ' ';
          return chars[Math.floor(Math.random() * chars.length)];
        })
        .join('');

      if (iteration >= totalChars) {
        clearInterval(glitchTimer);
      }
      iteration += 1 / 2;
    }, interval);
    dynamicPreviewTimers.push(glitchTimer);
  } else {
    textTarget.style.opacity = 1;
    textTarget.style.transition = 'none';
    textTarget.innerHTML = '';
    textTarget.appendChild(cursor);
    cursor.style.display = 'inline-block';

    const charDelay = Math.max(15, speechMs / fullText.length);
    let charIndex = 0;

    function typeChar() {
      if (charIndex < fullText.length) {
        const charNode = document.createTextNode(fullText.charAt(charIndex));
        textTarget.insertBefore(charNode, cursor);
        charIndex++;
        dynamicPreviewTimers.push(setTimeout(typeChar, charDelay));
      } else {
        cursor.style.display = 'none';
      }
    }
    typeChar();
  }

  const hideDelayMs = parseFloat(document.getElementById('hide-delay-slider').value) * 1000;

  dynamicPreviewTimers.push(setTimeout(() => {
    const exitClass = `anim-exit-${exitAnim}`;
    container.classList.remove('active');
    container.classList.add(exitClass);

    dynamicPreviewTimers.push(setTimeout(() => {
      container.className = `overlay-container-preview anim-container ${avatarPos === 'right' ? 'avatar-right' : ''}`;
      textTarget.innerHTML = '';
    }, 450));
  }, audioDurationMs + hideDelayMs));
}

// ==================== ОБРАБОТЧИКИ СОБЫТИЙ (DOM) ====================

document.addEventListener('DOMContentLoaded', async () => {
  await initCustomFonts();
  await loadPresetsList();
  await loadSystemConfig();
  await loadDonationAlertsConfig();
  if (typeof initScriptGenerator === 'function') {
    initScriptGenerator();
  }

  if (statusPollInterval) clearInterval(statusPollInterval);
  statusPollInterval = setInterval(pollSystemStatus, 4000);

  const tabChars = document.getElementById('tab-btn-characters');
  const tabSettings = document.getElementById('tab-btn-settings');
  const viewChars = document.getElementById('view-characters');
  const viewSettings = document.getElementById('view-settings');

  if (tabChars && tabSettings) {
    tabChars.addEventListener('click', () => {
      tabChars.classList.add('active');
      tabSettings.classList.remove('active');
      viewChars.classList.remove('hidden');
      viewSettings.classList.add('hidden');
    });

    tabSettings.addEventListener('click', async () => {
      tabSettings.classList.add('active');
      tabChars.classList.remove('active');
      viewSettings.classList.remove('hidden');
      viewChars.classList.add('hidden');
      await loadSystemConfig();
      await loadDonationAlertsConfig();
    });
  }

  document.getElementById('cfg-timesteps').addEventListener('input', (e) => {
    document.getElementById('cfg-timesteps-val').innerText = `${e.target.value} шагов`;
  });

  document.getElementById('btn-save-settings').addEventListener('click', () => {
    saveSystemConfig();
  });

  document.getElementById('btn-da-save').addEventListener('click', () => {
    saveDaConfig();
  });

  document.getElementById('btn-da-login').addEventListener('click', async () => {
    await saveDaConfig();
    try {
      const res = await fetch('/api/da/auth_url');
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Ошибка получения ссылки авторизации');
      window.open(data.auth_url, '_blank');
    } catch (e) {
      alert(e.message);
    }
  });

  document.getElementById('btn-da-test').addEventListener('click', async () => {
    try {
      const res = await fetch('/api/da/test_donation', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user: "Тестовый Донатер",
          amount: 250,
          currency: "RUB",
          message: "Привет! Это проверка работы донатов через DonationAlerts и Streamer.bot."
        })
      });
      if (!res.ok) throw new Error('Ошибка отправки тестового доната');
      alert('Тестовое событие отправлено в Streamer.bot! Проверьте очередь экшенов.');
    } catch (e) {
      alert(e.message);
    }
  });

  const btnCopyDaRedirect = document.getElementById('btn-copy-da-redirect');
  if (btnCopyDaRedirect) {
    btnCopyDaRedirect.addEventListener('click', () => {
      const val = document.getElementById('da-redirect-uri').value;
      navigator.clipboard.writeText(val);
      alert('URL перенаправления скопирован!');
    });
  }

  const btnToggleSecret = document.getElementById('btn-toggle-da-secret');
  if (btnToggleSecret) {
    btnToggleSecret.addEventListener('click', () => {
      const secretInp = document.getElementById('da-cfg-client-secret');
      if (secretInp.type === 'password') {
        secretInp.type = 'text';
        btnToggleSecret.innerText = '🔒';
      } else {
        secretInp.type = 'password';
        btnToggleSecret.innerText = '👁️';
      }
    });
  }

  const watchInputs = [
    'char-name', 'border-color', 'bg-color', 'text-color', 'name-bg-color',
    'name-text-color', 'bg-opacity-slider', 'hide-delay-slider', 'box-shape',
    'border-fx', 'font-family', 'font-size-slider', 'entrance-animation',
    'exit-animation', 'text-animation', 'avatar-position', 'ref-text', 'speed-slider'
  ];

  watchInputs.forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    el.addEventListener('input', () => {
      setDirty(true);
      if (id === 'bg-opacity-slider') {
        document.getElementById('bg-opacity-val').innerText = `${Math.round(el.value * 100)}%`;
      }
      if (id === 'hide-delay-slider') {
        document.getElementById('hide-delay-slider').value = el.value;
        document.getElementById('hide-delay-val').innerText = `${parseFloat(el.value).toFixed(1)}с`;
      }
      if (id === 'font-size-slider') {
        document.getElementById('font-size-val').innerText = `${el.value}px`;
      }
      if (id === 'speed-slider') {
        document.getElementById('speed-val').innerText = `${el.value}x`;
      }
      updatePreviews();
    });
  });

  document.getElementById('normalize-target').addEventListener('input', (e) => {
    document.getElementById('normalize-target-val').innerText = `${Math.round(e.target.value * 100)}%`;
  });

  document.getElementById('test-tts-text').addEventListener('input', (e) => {
    const len = e.target.value.length;
    document.getElementById('char-count-badge').innerText = `${len} / 600 симв. (реком. до 150)`;
  });

  document.getElementById('btn-upload-font').addEventListener('click', () => {
    document.getElementById('font-file-input').click();
  });
  document.getElementById('font-file-input').addEventListener('change', (e) => {
    if (e.target.files.length > 0) {
      uploadCustomFont(e.target.files[0]);
    }
  });

  document.getElementById('avatar-file-input').addEventListener('change', (e) => {
    if (e.target.files.length > 0) {
      const file = e.target.files[0];
      const reader = new FileReader();
      reader.onload = (ev) => {
        currentDraftAvatarBase64 = ev.target.result;
        document.getElementById('static-avatar').src = currentDraftAvatarBase64;
        document.getElementById('dynamic-avatar').src = currentDraftAvatarBase64;
        document.getElementById('static-avatar-box').classList.remove('hidden');
        document.getElementById('dynamic-avatar-box').classList.remove('hidden');
        setDirty(true);
      };
      reader.readAsDataURL(file);
    }
  });

  document.getElementById('btn-choose-files').addEventListener('click', () => {
    document.getElementById('voice-file-input').click();
  });

  document.getElementById('voice-file-input').addEventListener('change', async (e) => {
    const files = Array.from(e.target.files);
    if (files.length === 0) return;

    if (files.length === 1) {
      originalRawFileBlob = files[0];
      draftVoiceBlob = null;
      loadAudioToWaveSurfer(URL.createObjectURL(files[0]));
      document.getElementById('btn-restore-noise').classList.add('hidden');
      setDirty(true);
    } else {
      stitcherFiles = files;
      renderStitcherList();
      await stitchAudioFiles();
    }
  });

  async function renderStitcherList() {
    const box = document.getElementById('stitcher-container');
    const list = document.getElementById('stitcher-file-list');
    const countInfo = document.getElementById('stitcher-count-info');

    if (stitcherFiles.length === 0) {
      box.classList.add('hidden');
      return;
    }

    box.classList.remove('hidden');
    countInfo.innerText = `Фрагментов для склейки: ${stitcherFiles.length}`;
    list.innerHTML = '';

    stitcherFiles.forEach((f, idx) => {
      const item = document.createElement('div');
      item.className = 'stitcher-item';
      item.innerHTML = `
        <span class="stitcher-item-name">${idx + 1}. ${f.name}</span>
        <button class="btn-remove-item" data-idx="${idx}">✖</button>
      `;
      list.appendChild(item);
    });

    list.querySelectorAll('.btn-remove-item').forEach(btn => {
      btn.addEventListener('click', async (e) => {
        const idx = parseInt(e.target.getAttribute('data-idx'));
        stitcherFiles.splice(idx, 1);
        renderStitcherList();
        if (stitcherFiles.length > 0) {
          await stitchAudioFiles();
        } else {
          document.getElementById('waveform-container').classList.add('hidden');
        }
      });
    });
  }

  document.getElementById('btn-clear-stitcher').addEventListener('click', () => {
    stitcherFiles = [];
    renderStitcherList();
    document.getElementById('waveform-container').classList.add('hidden');
  });

  async function stitchAudioFiles() {
    if (stitcherFiles.length === 0) return;

    const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    const targetSampleRate = 24000;
    const buffers = [];

    for (const f of stitcherFiles) {
      const arr = await f.arrayBuffer();
      const buf = await audioCtx.decodeAudioData(arr);
      
      const offlineCtx = new OfflineAudioContext(1, Math.ceil(buf.duration * targetSampleRate), targetSampleRate);
      const src = offlineCtx.createBufferSource();
      src.buffer = buf;
      src.connect(offlineCtx.destination);
      src.start(0);
      const resampledBuf = await offlineCtx.startRendering();
      buffers.push(resampledBuf);
    }

    const totalLen = buffers.reduce((acc, b) => acc + b.length, 0);
    const outBuf = audioCtx.createBuffer(1, totalLen, targetSampleRate);
    const channel = outBuf.getChannelData(0);

    let offset = 0;
    for (const b of buffers) {
      channel.set(b.getChannelData(0), offset);
      offset += b.length;
    }

    const stitchedBlob = audioBufferToWav(outBuf);
    originalRawFileBlob = stitchedBlob;
    draftVoiceBlob = null;
    loadAudioToWaveSurfer(URL.createObjectURL(stitchedBlob));
    document.getElementById('btn-restore-noise').classList.add('hidden');
    setDirty(true);
  }

  const btnRecordMic = document.getElementById('btn-record-mic');
  const btnStopRecord = document.getElementById('btn-stop-record');
  const recBox = document.getElementById('recording-indicator');
  const recTimer = document.getElementById('recording-timer');

  if (btnRecordMic) {
    btnRecordMic.addEventListener('click', async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        mediaRecorder = new MediaRecorder(stream);
        audioChunks = [];
        recordSeconds = 0;

        mediaRecorder.ondataavailable = e => audioChunks.push(e.data);
        mediaRecorder.onstop = async () => {
          const blob = new Blob(audioChunks, { type: 'audio/wav' });
          originalRawFileBlob = blob;
          draftVoiceBlob = null;
          loadAudioToWaveSurfer(URL.createObjectURL(blob));
          document.getElementById('btn-restore-noise').classList.add('hidden');
          setDirty(true);
        };

        mediaRecorder.start();
        recBox.classList.remove('hidden');
        recordInterval = setInterval(() => {
          recordSeconds++;
          const mins = String(Math.floor(recordSeconds / 60)).padStart(2, '0');
          const secs = String(recordSeconds % 60).padStart(2, '0');
          recTimer.innerText = `Идет запись: ${mins}:${secs}`;
        }, 1000);
      } catch (e) {
        alert('Ошибка доступа к микрофону: ' + e.message);
      }
    });
  }

  if (btnStopRecord) {
    btnStopRecord.addEventListener('click', () => {
      if (mediaRecorder && mediaRecorder.state !== 'inactive') {
        mediaRecorder.stop();
        clearInterval(recordInterval);
        recBox.classList.add('hidden');
      }
    });
  }

  document.getElementById('btn-play-region').addEventListener('click', () => {
    togglePlayRegion();
  });

  document.getElementById('btn-apply-trim').addEventListener('click', async () => {
    if (!wavesurfer || !currentRegion) return;
    const btn = document.getElementById('btn-apply-trim');
    const origHtml = btn.innerHTML;
    btn.innerHTML = '⏳ Обрезка и Whisper...';
    btn.disabled = true;

    try {
      const activeFile = draftVoiceBlob || originalRawFileBlob;
      if (!activeFile) throw new Error('Сначала загрузите сэмпл');

      const fd = new FormData();
      fd.append('audio', activeFile, 'source.wav');
      fd.append('start', currentRegion.start);
      fd.append('end', currentRegion.end);

      const res = await fetch('/api/trim_and_transcribe', { method: 'POST', body: fd });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Ошибка сервера при обрезке');
      }

      const data = await res.json();
      const byteArray = Uint8Array.from(atob(data.audio_base64), c => c.charCodeAt(0));
      const trimmedBlob = new Blob([byteArray], { type: 'audio/wav' });

      draftVoiceBlob = trimmedBlob;
      loadAudioToWaveSurfer(URL.createObjectURL(trimmedBlob));

      if (data.text) {
        document.getElementById('ref-text').value = data.text;
      }
      document.getElementById('btn-restore-noise').classList.remove('hidden');
      setDirty(true);
    } catch (e) {
      alert('Ошибка: ' + e.message);
    } finally {
      btn.innerHTML = origHtml;
      btn.disabled = false;
    }
  });

  document.getElementById('btn-normalize').addEventListener('click', async () => {
    if (!wavesurfer) return;
    const btn = document.getElementById('btn-normalize');
    const origText = btn.innerText;
    btn.innerText = '⏳ Выравнивание...';
    btn.disabled = true;

    try {
      const targetGain = parseFloat(document.getElementById('normalize-target').value);
      const activeFile = draftVoiceBlob || originalRawFileBlob;
      if (!activeFile) throw new Error('Сначала загрузите сэмпл');

      const fd = new FormData();
      fd.append('audio', activeFile, 'norm.wav');
      fd.append('target_gain', targetGain);

      const res = await fetch('/api/normalize_audio', { method: 'POST', body: fd });
      if (!res.ok) throw new Error('Ошибка нормализации');

      const normBlob = await res.blob();
      draftVoiceBlob = normBlob;

      const curStart = currentRegion ? currentRegion.start : 0;
      const curEnd = currentRegion ? currentRegion.end : 5.5;

      wavesurfer.load(URL.createObjectURL(normBlob));
      wavesurfer.once('ready', () => {
        wsRegions.clearRegions();
        currentRegion = wsRegions.addRegion({
          start: curStart,
          end: Math.min(wavesurfer.getDuration(), curEnd),
          color: 'rgba(99, 102, 241, 0.3)',
          drag: true,
          resize: true
        });
        updateRegionTimeInfo();
      });

      document.getElementById('btn-restore-noise').classList.remove('hidden');
      setDirty(true);
    } catch (e) {
      alert(e.message);
    } finally {
      btn.innerText = origText;
      btn.disabled = false;
    }
  });

  document.getElementById('btn-isolate-vocal').addEventListener('click', async () => {
    if (!wavesurfer) return;
    const btn = document.getElementById('btn-isolate-vocal');
    const origHtml = btn.innerHTML;
    btn.innerHTML = '⏳ Нейросеть Demucs очищает...';
    btn.disabled = true;

    try {
      const activeFile = draftVoiceBlob || originalRawFileBlob;
      if (!activeFile) throw new Error('Сначала загрузите сэмпл');

      const shiftsVal = parseInt(document.getElementById('demucs-shifts').value, 10) || 2;

      const fd = new FormData();
      fd.append('audio', activeFile, 'demucs_in.wav');
      fd.append('shifts', shiftsVal);

      const res = await fetch('/api/isolate_vocal', { method: 'POST', body: fd });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Ошибка очистки Demucs');
      }

      const isolatedBlob = await res.blob();
      draftVoiceBlob = isolatedBlob;

      const curStart = currentRegion ? currentRegion.start : 0;
      const curEnd = currentRegion ? currentRegion.end : 5.5;

      wavesurfer.load(URL.createObjectURL(isolatedBlob));
      wavesurfer.once('ready', () => {
        wsRegions.clearRegions();
        currentRegion = wsRegions.addRegion({
          start: curStart,
          end: Math.min(wavesurfer.getDuration(), curEnd),
          color: 'rgba(99, 102, 241, 0.3)',
          drag: true,
          resize: true
        });
        updateRegionTimeInfo();
      });

      document.getElementById('btn-restore-noise').classList.remove('hidden');
      setDirty(true);
    } catch (e) {
      alert(e.message);
    } finally {
      btn.innerHTML = origHtml;
      btn.disabled = false;
    }
  });

  document.getElementById('btn-restore-noise').addEventListener('click', () => {
    if (originalRawFileBlob) {
      draftVoiceBlob = null;
      loadAudioToWaveSurfer(URL.createObjectURL(originalRawFileBlob));
      document.getElementById('btn-restore-noise').classList.add('hidden');
      setDirty(true);
    }
  });

  document.getElementById('btn-save-char').addEventListener('click', async () => {
    const charId = document.getElementById('char-id').value.trim();
    const charName = document.getElementById('char-name').value.trim();
    const refText = document.getElementById('ref-text').value.trim();
    const speed = parseFloat(document.getElementById('speed-slider').value);

    if (!charId) {
      alert('Укажите ID персонажа (латиница без пробелов)!');
      return;
    }

    if (!selectedCharId && currentPresets[charId]) {
      const confirmOverwrite = confirm(
        `Персонаж с ID "${charId}" уже существует!\n\nВы уверены, что хотите полностью перезаписать его?`
      );
      if (!confirmOverwrite) {
        return;
      }
    }

    const theme = {
      border_color: document.getElementById('border-color').value,
      bg_color: document.getElementById('bg-color').value,
      text_color: document.getElementById('text-color').value,
      name_bg_color: document.getElementById('name-bg-color').value,
      name_text_color: document.getElementById('name-text-color').value,
      bg_opacity: parseFloat(document.getElementById('bg-opacity-slider').value),
      hide_delay: parseFloat(document.getElementById('hide-delay-slider').value),
      avatar_position: document.getElementById('avatar-position').value,
      box_shape: document.getElementById('box-shape').value,
      border_fx: document.getElementById('border-fx').value,
      font_family: document.getElementById('font-family').value,
      font_size: parseInt(document.getElementById('font-size-slider').value),
      entrance_animation: document.getElementById('entrance-animation').value,
      exit_animation: document.getElementById('exit-animation').value,
      text_animation: document.getElementById('text-animation').value
    };

    const fd = new FormData();
    fd.append('char_id', charId);
    fd.append('name', charName);
    fd.append('reference_text', refText);
    fd.append('speed', speed);
    fd.append('theme_json', JSON.stringify(theme));

    if (draftVoiceBlob) {
      fd.append('voice_file', draftVoiceBlob, 'voice.wav');
    } else if (originalRawFileBlob) {
      fd.append('voice_file', originalRawFileBlob, 'voice.wav');
    }

    const avatarInput = document.getElementById('avatar-file-input');
    if (avatarInput.files.length > 0) {
      fd.append('avatar_file', avatarInput.files[0], 'avatar.png');
    }

    try {
      const res = await fetch('/api/characters/save', { method: 'POST', body: fd });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Ошибка сохранения');

      setDirty(false);
      await loadPresetsList();
      selectCharacter(charId);
      alert('Персонаж успешно сохранен!');
    } catch (e) {
      alert('Ошибка: ' + e.message);
    }
  });

  document.getElementById('btn-set-active').addEventListener('click', async () => {
    if (!selectedCharId) return;
    try {
      const res = await fetch('/api/presets/set_active', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: selectedCharId })
      });
      if (!res.ok) throw new Error('Ошибка активации');
      await loadPresetsList();
    } catch (e) {
      alert(e.message);
    }
  });

  document.getElementById('btn-delete-char').addEventListener('click', async () => {
    if (!selectedCharId) return;
    if (!confirm(`Вы действительно хотите удалить персонажа "${selectedCharId}"?`)) return;

    try {
      const res = await fetch(`/api/characters/${selectedCharId}`, { method: 'DELETE' });
      if (!res.ok) throw new Error('Ошибка удаления');
      selectedCharId = null;
      setDirty(false);
      await loadPresetsList();
    } catch (e) {
      alert(e.message);
    }
  });

  function copyObs(test = false) {
    const url = test ? `${window.location.origin}/overlay?test=1` : `${window.location.origin}/overlay`;
    navigator.clipboard.writeText(url);
    alert(`Ссылка скопирована:\n${url}`);
  }

  document.getElementById('btn-copy-obs-url').addEventListener('click', () => copyObs(false));
  document.getElementById('btn-copy-obs-test-url').addEventListener('click', () => copyObs(true));
  document.getElementById('btn-settings-copy-obs').addEventListener('click', () => copyObs(false));
  document.getElementById('btn-settings-copy-test').addEventListener('click', () => copyObs(true));

  document.getElementById('btn-new-char').addEventListener('click', () => {
    createNewCharacter();
  });

  async function generateTestTTS(triggerObs = false) {
    const text = document.getElementById('test-tts-text').value.trim();
    const refText = document.getElementById('ref-text').value.trim();
    const speed = parseFloat(document.getElementById('speed-slider').value);

    if (!text) {
      alert('Введите тестовый текст!');
      return null;
    }

    const fd = new FormData();
    fd.append('text', text);
    fd.append('ref_text', refText);
    fd.append('speed', speed);
    fd.append('trigger_obs', triggerObs);
    fd.append('draft_theme_json', JSON.stringify(getDraftTheme()));

    if (draftVoiceBlob) {
      fd.append('voice_file', draftVoiceBlob, 'draft.wav');
    } else if (originalRawFileBlob) {
      fd.append('voice_file', originalRawFileBlob, 'draft.wav');
    } else if (selectedCharId) {
      fd.append('char_id', selectedCharId);
    } else {
      alert('Загрузите или запишите сэмпл голоса!');
      return null;
    }

    const res = await fetch('/api/test_draft_tts', { method: 'POST', body: fd });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Ошибка генерации TTS');
    }

    const blob = await res.blob();
    return { blob, text };
  }

  document.getElementById('btn-test-tts-only').addEventListener('click', async () => {
    const btn = document.getElementById('btn-test-tts-only');
    const origText = btn.innerText;
    btn.innerText = '⏳ Синтез...';
    btn.disabled = true;

    try {
      const res = await generateTestTTS(false);
      if (!res) return;

      const playerBox = document.getElementById('tts-audio-container');
      const player = document.getElementById('tts-result-player');
      playerBox.classList.remove('hidden');

      const url = URL.createObjectURL(res.blob);
      player.src = url;
      player.play();

      document.getElementById('btn-download-wav').onclick = () => {
        const a = document.createElement('a');
        a.href = url;
        a.download = `test_${Date.now()}.wav`;
        a.click();
      };

      document.getElementById('btn-convert-telegram-ogg').onclick = async () => {
        const fd = new FormData();
        fd.append('audio', res.blob, 'to_ogg.wav');
        const oggRes = await fetch('/api/convert_to_telegram_ogg', { method: 'POST', body: fd });
        if (!oggRes.ok) throw new Error('Ошибка OGG конвертации');
        const oggBlob = await oggRes.blob();
        const oggUrl = URL.createObjectURL(oggBlob);

        const tgBox = document.getElementById('telegram-player-box');
        const tgPlayer = document.getElementById('telegram-result-player');
        tgBox.classList.remove('hidden');
        tgPlayer.src = oggUrl;
        tgPlayer.play();

        document.getElementById('btn-download-ogg').onclick = () => {
          const a = document.createElement('a');
          a.href = oggUrl;
          a.download = `voice_${Date.now()}.ogg`;
          a.click();
        };
      };
    } catch (e) {
      alert(e.message);
    } finally {
      btn.innerText = origText;
      btn.disabled = false;
    }
  });

  document.getElementById('btn-test-overlay-only').addEventListener('click', async () => {
    const text = document.getElementById('test-tts-text').value.trim();
    if (!text) return;
    const wordsCount = text.split(' ').length;
    const estDuration = Math.max(2.5, wordsCount * 0.35);

    runDynamicOverlayPreview(text, estDuration);

    try {
      const payload = {
        text: text,
        duration: estDuration,
        char_id: selectedCharId || document.getElementById('char-id').value.trim() || '',
        draft_theme: getDraftTheme()
      };

      await fetch('/api/trigger_overlay_preview', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
    } catch (e) {}
  });

  document.getElementById('btn-test-combo').addEventListener('click', async () => {
    const btn = document.getElementById('btn-test-combo');
    const origText = btn.innerText;
    btn.innerText = '⏳ Синтез...';
    btn.disabled = true;

    try {
      const res = await generateTestTTS(true);
      if (!res) return;

      const playerBox = document.getElementById('tts-audio-container');
      const player = document.getElementById('tts-result-player');
      playerBox.classList.remove('hidden');

      const url = URL.createObjectURL(res.blob);
      player.src = url;

      player.onloadedmetadata = () => {
        const dur = player.duration || 3.5;
        player.play();
        runDynamicOverlayPreview(res.text, dur);
        player.onloadedmetadata = null;
      };
    } catch (e) {
      alert(e.message);
    } finally {
      btn.innerText = origText;
      btn.disabled = false;
    }
  });
});