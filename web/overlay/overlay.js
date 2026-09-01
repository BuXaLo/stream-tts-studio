const container = document.getElementById('mita-container');
const avatarBox = document.querySelector('.avatar-box');
const avatarImg = document.getElementById('mita-avatar');
const nameTag = document.getElementById('name-tag');
const dialogueBox = document.getElementById('dialogue-box');
const textTarget = document.getElementById('text-target');
let cursor = document.getElementById('cursor');

let overlayTimers = [];
let currentTheme = {};
const loadedCustomFonts = new Set();

const urlParams = new URLSearchParams(window.location.search);
const isTestMode = urlParams.has('test') || urlParams.has('align') || urlParams.has('static');

function clearOverlayTimers() {
  overlayTimers.forEach(t => clearTimeout(t));
  overlayTimers = [];
}

function hexToRgba(hex, alpha) {
  let r = parseInt(hex.slice(1, 3), 16) || 0;
  let g = parseInt(hex.slice(3, 5), 16) || 0;
  let b = parseInt(hex.slice(5, 7), 16) || 0;
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

async function registerCustomFonts() {
  try {
    const res = await fetch('/api/fonts');
    const data = await res.json();
    if (data.custom_fonts && data.custom_fonts.length > 0) {
      let fontStyles = '';
      for (const font of data.custom_fonts) {
        if (!loadedCustomFonts.has(font.name)) {
          fontStyles += `
            @font-face {
              font-family: '${font.name}';
              src: url('${font.url}') format('truetype');
            }
          `;
          loadedCustomFonts.add(font.name);
        }
      }
      if (fontStyles) {
        const styleEl = document.createElement('style');
        styleEl.textContent = fontStyles;
        document.head.appendChild(styleEl);
      }
      await document.fonts.ready;
    }
  } catch (e) {}
}

async function loadActiveTheme(charId = null, draftTheme = null) {
  try {
    await registerCustomFonts();

    let data;
    if (draftTheme) {
      data = draftTheme;
    } else {
      const url = charId ? `/api/active_overlay_config?char_id=${encodeURIComponent(charId)}` : '/api/active_overlay_config';
      const res = await fetch(url);
      data = await res.json();
    }

    nameTag.innerText = data.name || "Персонаж";

    if (data.avatar) {
      avatarImg.src = data.avatar.startsWith('data:') ? data.avatar : data.avatar + '?_t=' + Date.now();
      avatarBox.classList.remove('hidden');
    } else {
      avatarImg.src = '';
      avatarBox.classList.add('hidden');
    }

    const theme = data.theme || {};
    currentTheme = theme;

    const bColor = theme.border_color || '#6366f1';
    const bgRgba = hexToRgba(theme.bg_color || '#0d0b14', theme.bg_opacity !== undefined ? theme.bg_opacity : 0.9);
    const tColor = theme.text_color || '#fcebeb';
    const nBgColor = theme.name_bg_color || '#6366f1';
    const nTextColor = theme.name_text_color || '#ffffff';
    const shape = theme.box_shape || 'shape-rounded';
    const fx = theme.border_fx || 'fx-neon';
    const fontSize = theme.font_size ? `${theme.font_size}px` : '22px';
    const avatarPos = theme.avatar_position || 'left';

    if (avatarPos === 'right') {
      container.classList.add('avatar-right');
    } else {
      container.classList.remove('avatar-right');
    }

    nameTag.style.background = nBgColor;
    nameTag.style.color = nTextColor;

    dialogueBox.className = `dialogue-box ${shape} ${fx}`;
    dialogueBox.style.setProperty('--border-color', bColor);
    dialogueBox.style.borderColor = bColor;
    dialogueBox.style.background = bgRgba;

    textTarget.style.color = tColor;
    textTarget.style.fontSize = fontSize;
    textTarget.style.fontFamily = `"${theme.font_family || 'Comfortaa'}", sans-serif`;
    
    if (cursor) {
      cursor.style.backgroundColor = '';
      cursor.style.height = fontSize;
    }
  } catch (e) {}
}

function extractPayload(obj) {
  if (!obj) return null;
  if (typeof obj === 'string') {
    try { return extractPayload(JSON.parse(obj)); } catch (e) { return null; }
  }
  if (typeof obj === 'object') {
    if (obj.text) return { 
      text: obj.text, 
      duration: parseFloat(obj.duration) || 3.5, 
      char_id: obj.char_id || obj.character || null,
      draft_theme: obj.draft_theme || null 
    };
    if (obj.data) return extractPayload(obj.data);
    if (obj.message) return extractPayload(obj.message);
  }
  return null;
}

function connectWebSocket() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const ws = new WebSocket(`${protocol}//${window.location.host}/ws/overlay`);

  ws.onmessage = async (event) => {
    try {
      let parsed = JSON.parse(event.data);
      let payload = extractPayload(parsed);
      if (payload && payload.text) {
        await loadActiveTheme(payload.char_id, payload.draft_theme);
        showDialogue(payload.text, payload.duration);
      }
    } catch (e) {}
  };

  ws.onclose = () => setTimeout(connectWebSocket, 2000);
}

function showDialogue(fullText, durationSeconds) {
  if (!fullText) return;
  clearOverlayTimers();

  container.className = 'mita-container';
  container.style.cssText = '';

  const entrance = currentTheme.entrance_animation || 'slide-up';
  container.classList.add(`anim-${entrance}`);
  if (currentTheme.avatar_position === 'right') {
    container.classList.add('avatar-right');
  }

  if (!cursor) {
    cursor = document.createElement('span');
    cursor.className = 'cursor';
    cursor.id = 'cursor';
  }
  
  textTarget.innerHTML = "";
  textTarget.appendChild(cursor);
  cursor.style.display = "none";

  overlayTimers.push(setTimeout(() => {
    container.classList.add('active');
  }, 40));

  const audioDurationMs = ((durationSeconds && durationSeconds > 0) ? durationSeconds : 3.5) * 1000;
  const speechMs = audioDurationMs * 0.85;
  const textAnim = currentTheme.text_animation || 'typewriter';

  if (textAnim === 'instant') {
    textTarget.textContent = fullText;
    cursor.style.display = "none";
  } else if (textAnim === 'word-fade') {
    cursor.style.display = "none";
    const words = fullText.split(" ");
    textTarget.innerHTML = words.map(w => `<span class="word-span">${w}</span>`).join(" ");
    const spans = textTarget.querySelectorAll('.word-span');
    const wordDelay = Math.max(40, speechMs / words.length);

    spans.forEach((span, idx) => {
      overlayTimers.push(setTimeout(() => {
        span.classList.add('visible');
      }, idx * wordDelay));
    });
  } else if (textAnim === 'wavy-text') {
    cursor.style.display = "none";
    textTarget.innerHTML = fullText.split("").map((c, i) => 
      c === " " ? " " : `<span class="wavy-char" style="animation-delay: ${(i * 0.08) % 1.4}s">${c}</span>`
    ).join("");
  } else if (textAnim === 'glitch-decode') {
    cursor.style.display = "none";
    const chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*";
    const totalChars = fullText.length;
    let iteration = 0;
    const interval = Math.max(25, speechMs / (totalChars * 2));

    const glitchTimer = setInterval(() => {
      textTarget.innerText = fullText
        .split("")
        .map((letter, index) => {
          if (index < iteration) return letter;
          if (letter === " ") return " ";
          return chars[Math.floor(Math.random() * chars.length)];
        })
        .join("");

      if (iteration >= totalChars) {
        clearInterval(glitchTimer);
      }
      iteration += 1 / 2;
    }, interval);
    overlayTimers.push(glitchTimer);
  } else {
    textTarget.style.opacity = 1;
    textTarget.style.transition = 'none';
    textTarget.innerHTML = '';
    textTarget.appendChild(cursor);
    cursor.style.display = "inline-block";

    const charDelay = Math.max(15, speechMs / fullText.length);
    let charIndex = 0;

    function typeChar() {
      if (charIndex < fullText.length) {
        const charNode = document.createTextNode(fullText.charAt(charIndex));
        textTarget.insertBefore(charNode, cursor);
        charIndex++;
        overlayTimers.push(setTimeout(typeChar, charDelay));
      } else {
        cursor.style.display = "none";
      }
    }
    typeChar();
  }

  const hideDelayMs = (currentTheme.hide_delay !== undefined ? currentTheme.hide_delay : 2.0) * 1000;
  
  overlayTimers.push(setTimeout(() => {
    const exitAnim = currentTheme.exit_animation || 'fade-out';
    const exitClass = `anim-exit-${exitAnim}`;
    
    container.classList.remove('active');
    container.classList.add(exitClass);

    overlayTimers.push(setTimeout(() => {
      container.className = 'mita-container';
      textTarget.innerHTML = '';
    }, 450));
  }, audioDurationMs + hideDelayMs));
}

(async () => {
  await loadActiveTheme();

  if (isTestMode) {
    container.className = 'mita-container active';
    if (currentTheme.avatar_position === 'right') {
      container.classList.add('avatar-right');
    }
    if (cursor) cursor.style.display = 'none';
    textTarget.textContent = 'Тестовый текст диалогового окна для выравнивания, масштабирования и обрезки (Crop Alt) в OBS Studio...';
  } else {
    connectWebSocket();
  }
})();