// ==================== КАСТОМНЫЙ POPOVER COLOR PICKER (STUDIO UI) ====================

(() => {
    const BASE_SWATCHES = [
        '#ffffff', '#000000', '#0d0b14', '#6366f1',
        '#ec4899', '#10b981', '#f59e0b', '#ef4444'
    ];

    const HEX_RE = /^#([0-9a-fA-F]{6})$/;
    const SHORT_HEX_RE = /^#([0-9a-fA-F]{3})$/;

    let popoverEl = null;
    let activeInput = null;
    let activeTrigger = null;
    let currentHsv = { h: 239, s: 59, v: 95 };
    let isDraggingSat = false;
    let isDraggingHue = false;

    function normalizeHex(raw, fallback = '#6366f1') {
        if (typeof raw !== 'string') return fallback;
        const trimmed = raw.trim();
        const withHash = trimmed.startsWith('#') ? trimmed : '#' + trimmed;
        if (HEX_RE.test(withHash)) {
            return withHash.toLowerCase();
        }
        const shortMatch = withHash.match(SHORT_HEX_RE);
        if (shortMatch) {
            const [r, g, b] = shortMatch[1].split('');
            return `#${r}${r}${g}${g}${b}${b}`.toLowerCase();
        }
        return fallback;
    }

    function hexToRgb(hex) {
        const clean = normalizeHex(hex, '#000000').slice(1);
        return {
            r: parseInt(clean.slice(0, 2), 16),
            g: parseInt(clean.slice(2, 4), 16),
            b: parseInt(clean.slice(4, 6), 16)
        };
    }

    function rgbToHex(r, g, b) {
        const toHex = (n) => Math.max(0, Math.min(255, Math.round(n))).toString(16).padStart(2, '0');
        return `#${toHex(r)}${toHex(g)}${toHex(b)}`;
    }

    function rgbToHsv(r, g, b) {
        const rn = r / 255;
        const gn = g / 255;
        const bn = b / 255;
        const max = Math.max(rn, gn, bn);
        const min = Math.min(rn, gn, bn);
        const d = max - min;

        let h = 0;
        const s = max === 0 ? 0 : d / max;
        const v = max;

        if (d !== 0) {
            switch (max) {
                case rn:
                    h = ((gn - bn) / d + (gn < bn ? 6 : 0)) / 6;
                    break;
                case gn:
                    h = ((bn - rn) / d + 2) / 6;
                    break;
                case bn:
                    h = ((rn - gn) / d + 4) / 6;
                    break;
            }
        }
        return {
            h: Math.round(h * 360),
            s: Math.round(s * 100),
            v: Math.round(v * 100)
        };
    }

    function hsvToRgb(h, s, v) {
        const hn = ((h % 360) + 360) % 360;
        const sn = Math.max(0, Math.min(100, s)) / 100;
        const vn = Math.max(0, Math.min(100, v)) / 100;

        const c = vn * sn;
        const x = c * (1 - Math.abs(((hn / 60) % 2) - 1));
        const m = vn - c;

        let r1 = 0, g1 = 0, b1 = 0;
        if (hn < 60) { r1 = c; g1 = x; b1 = 0; }
        else if (hn < 120) { r1 = x; g1 = c; b1 = 0; }
        else if (hn < 180) { r1 = 0; g1 = c; b1 = x; }
        else if (hn < 240) { r1 = 0; g1 = x; b1 = c; }
        else if (hn < 300) { r1 = x; g1 = 0; b1 = c; }
        else { r1 = c; g1 = 0; b1 = x; }

        return {
            r: Math.round((r1 + m) * 255),
            g: Math.round((g1 + m) * 255),
            b: Math.round((b1 + m) * 255)
        };
    }

    function setNativeInputValue(input, hex) {
        const desc = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value');
        if (desc && desc.set) {
            desc.set.call(input, hex);
        } else {
            input.value = hex;
        }
    }

    function syncTriggerFromInput(input) {
        const trigger = input._studioColorTrigger;
        if (!trigger) return;
        const hex = normalizeHex(input.value, '#6366f1');
        const dot = trigger.querySelector('.color-swatch-dot');
        const label = trigger.querySelector('.color-hex-label');
        if (dot) dot.style.backgroundColor = hex;
        if (label) label.textContent = hex.toUpperCase();
    }

    function hookInputValueSetter(input) {
        if (input._studioValueHooked) return;
        const protoDesc = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value');
        if (!protoDesc || !protoDesc.get || !protoDesc.set) return;

        Object.defineProperty(input, 'value', {
            configurable: true,
            enumerable: true,
            get() {
                return protoDesc.get.call(this);
            },
            set(val) {
                const normalized = normalizeHex(String(val || ''), '#6366f1');
                protoDesc.set.call(this, normalized);
                syncTriggerFromInput(this);
                if (activeInput === this && popoverEl && !popoverEl.classList.contains('hidden')) {
                    const rgb = hexToRgb(normalized);
                    currentHsv = rgbToHsv(rgb.r, rgb.g, rgb.b);
                    renderPopoverState(normalized);
                }
            }
        });
        input._studioValueHooked = true;
    }

    function ensurePopover() {
        if (popoverEl) return popoverEl;

        const el = document.createElement('div');
        el.className = 'studio-color-popover hidden';
        el.setAttribute('role', 'dialog');
        el.setAttribute('aria-label', 'Выбор цвета');

        el.innerHTML = `
            <div class="cp-popover-header">
                <span class="cp-title">Выбор цвета</span>
                <button type="button" class="cp-close-btn" title="Закрыть (Esc)">✕</button>
            </div>
            <div class="cp-saturation-box">
                <div class="cp-saturation-cursor"></div>
            </div>
            <div class="cp-hue-slider">
                <div class="cp-hue-thumb"></div>
            </div>
            <div class="cp-hex-row">
                <div class="cp-preview-pill"></div>
                <input type="text" class="cp-hex-input" maxlength="7" spellcheck="false" placeholder="#6366F1">
                <button type="button" class="cp-copy-btn" title="Скопировать HEX">📋</button>
            </div>
            <div class="cp-swatches-section cp-character-swatches">
                <span class="cp-swatches-title">Цвета персонажа</span>
                <div class="cp-swatches-grid" data-group="character"></div>
            </div>
            <div class="cp-swatches-section">
                <span class="cp-swatches-title">Базовые</span>
                <div class="cp-swatches-grid" data-group="base"></div>
            </div>
        `;

        document.body.appendChild(el);
        popoverEl = el;

        const satBox = el.querySelector('.cp-saturation-box');
        const hueSlider = el.querySelector('.cp-hue-slider');
        const hexInput = el.querySelector('.cp-hex-input');
        const copyBtn = el.querySelector('.cp-copy-btn');
        const closeBtn = el.querySelector('.cp-close-btn');
        const baseGrid = el.querySelector('.cp-swatches-grid[data-group="base"]');

        BASE_SWATCHES.forEach((hex) => {
            const btn = createSwatchButton(hex);
            baseGrid.appendChild(btn);
        });

        function updateSatFromEvent(clientX, clientY) {
            const rect = satBox.getBoundingClientRect();
            if (!rect.width || !rect.height) return;
            const x = Math.max(0, Math.min(rect.width, clientX - rect.left));
            const y = Math.max(0, Math.min(rect.height, clientY - rect.top));
            currentHsv.s = Math.round((x / rect.width) * 100);
            currentHsv.v = Math.round((1 - y / rect.height) * 100);
            const rgb = hsvToRgb(currentHsv.h, currentHsv.s, currentHsv.v);
            applyColorToActive(rgbToHex(rgb.r, rgb.g, rgb.b), true);
        }

        function updateHueFromEvent(clientX) {
            const rect = hueSlider.getBoundingClientRect();
            if (!rect.width) return;
            const x = Math.max(0, Math.min(rect.width, clientX - rect.left));
            currentHsv.h = Math.round((x / rect.width) * 359);
            const rgb = hsvToRgb(currentHsv.h, currentHsv.s, currentHsv.v);
            applyColorToActive(rgbToHex(rgb.r, rgb.g, rgb.b), true);
        }

        satBox.addEventListener('mousedown', (e) => {
            e.preventDefault();
            isDraggingSat = true;
            updateSatFromEvent(e.clientX, e.clientY);
        });

        hueSlider.addEventListener('mousedown', (e) => {
            e.preventDefault();
            isDraggingHue = true;
            updateHueFromEvent(e.clientX);
        });

        window.addEventListener('mousemove', (e) => {
            if (isDraggingSat) {
                updateSatFromEvent(e.clientX, e.clientY);
            } else if (isDraggingHue) {
                updateHueFromEvent(e.clientX);
            }
        });

        window.addEventListener('mouseup', () => {
            if (isDraggingSat || isDraggingHue) {
                isDraggingSat = false;
                isDraggingHue = false;
                if (activeInput) {
                    activeInput.dispatchEvent(new Event('change', { bubbles: true }));
                }
            }
        });

        hexInput.addEventListener('input', () => {
            const raw = hexInput.value.trim();
            const candidate = raw.startsWith('#') ? raw : '#' + raw;
            if (HEX_RE.test(candidate)) {
                const normalized = candidate.toLowerCase();
                const rgb = hexToRgb(normalized);
                currentHsv = rgbToHsv(rgb.r, rgb.g, rgb.b);
                applyColorToActive(normalized, false);
            }
        });

        hexInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                if (activeInput) {
                    const normalized = normalizeHex(hexInput.value, activeInput.value);
                    const rgb = hexToRgb(normalized);
                    currentHsv = rgbToHsv(rgb.r, rgb.g, rgb.b);
                    applyColorToActive(normalized, true);
                    activeInput.dispatchEvent(new Event('change', { bubbles: true }));
                }
                closePopover();
            }
        });

        copyBtn.addEventListener('click', () => {
            const val = hexInput.value.toUpperCase();
            if (navigator.clipboard && val) {
                navigator.clipboard.writeText(val).catch(() => {});
                copyBtn.textContent = '✓';
                setTimeout(() => { copyBtn.textContent = '📋'; }, 900);
            }
        });

        closeBtn.addEventListener('click', closePopover);

        document.addEventListener('mousedown', (e) => {
            if (!popoverEl || popoverEl.classList.contains('hidden')) return;
            if (popoverEl.contains(e.target)) return;
            if (activeTrigger && activeTrigger.contains(e.target)) return;
            closePopover();
        });

        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && popoverEl && !popoverEl.classList.contains('hidden')) {
                closePopover();
            }
        });

        window.addEventListener('resize', () => {
            if (popoverEl && !popoverEl.classList.contains('hidden') && activeTrigger) {
                positionPopover(activeTrigger);
            }
        });

        return el;
    }

    function createSwatchButton(hex) {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'cp-swatch-btn';
        btn.style.backgroundColor = hex;
        btn.title = hex.toUpperCase();
        btn.addEventListener('click', () => {
            const normalized = normalizeHex(hex, '#6366f1');
            const rgb = hexToRgb(normalized);
            currentHsv = rgbToHsv(rgb.r, rgb.g, rgb.b);
            applyColorToActive(normalized, true);
            if (activeInput) {
                activeInput.dispatchEvent(new Event('change', { bubbles: true }));
            }
        });
        return btn;
    }

    function renderCharacterSwatches() {
        if (!popoverEl) return;
        const section = popoverEl.querySelector('.cp-character-swatches');
        const grid = popoverEl.querySelector('.cp-swatches-grid[data-group="character"]');
        if (!section || !grid) return;

        grid.replaceChildren();
        const seen = new Set();
        document.querySelectorAll('input.studio-color-input').forEach((inp) => {
            const hex = normalizeHex(inp.value, '');
            if (hex && !seen.has(hex)) {
                seen.add(hex);
            }
        });

        if (seen.size === 0) {
            section.classList.add('hidden');
            return;
        }
        section.classList.remove('hidden');
        seen.forEach((hex) => {
            grid.appendChild(createSwatchButton(hex));
        });
    }

    function renderPopoverState(hex) {
        if (!popoverEl) return;
        const satBox = popoverEl.querySelector('.cp-saturation-box');
        const satCursor = popoverEl.querySelector('.cp-saturation-cursor');
        const hueThumb = popoverEl.querySelector('.cp-hue-thumb');
        const previewPill = popoverEl.querySelector('.cp-preview-pill');
        const hexInput = popoverEl.querySelector('.cp-hex-input');

        const pureHueRgb = hsvToRgb(currentHsv.h, 100, 100);
        satBox.style.backgroundColor = rgbToHex(pureHueRgb.r, pureHueRgb.g, pureHueRgb.b);
        satCursor.style.left = `${currentHsv.s}%`;
        satCursor.style.top = `${100 - currentHsv.v}%`;
        hueThumb.style.left = `${(currentHsv.h / 359) * 100}%`;
        previewPill.style.backgroundColor = hex;

        if (document.activeElement !== hexInput) {
            hexInput.value = hex.toUpperCase();
        }
    }

    function applyColorToActive(hex, updateHexField = true) {
        if (!activeInput) return;
        setNativeInputValue(activeInput, hex);
        syncTriggerFromInput(activeInput);
        renderPopoverState(hex);
        if (updateHexField && popoverEl) {
            const hexInput = popoverEl.querySelector('.cp-hex-input');
            if (hexInput) hexInput.value = hex.toUpperCase();
        }
        activeInput.dispatchEvent(new Event('input', { bubbles: true }));
    }

    function positionPopover(trigger) {
        if (!popoverEl || !trigger) return;
        const rect = trigger.getBoundingClientRect();
        const popRect = popoverEl.getBoundingClientRect();
        const popW = popRect.width || 248;
        const popH = popRect.height || 310;
        const margin = 8;

        let left = rect.left;
        if (left + popW > window.innerWidth - margin) {
            left = window.innerWidth - popW - margin;
        }
        if (left < margin) left = margin;

        let top = rect.bottom + 6;
        if (top + popH > window.innerHeight - margin) {
            top = rect.top - popH - 6;
        }
        if (top < margin) top = margin;

        popoverEl.style.left = `${Math.round(left)}px`;
        popoverEl.style.top = `${Math.round(top)}px`;
    }

    function openPopover(input, trigger) {
        const el = ensurePopover();

        if (activeTrigger && activeTrigger !== trigger) {
            activeTrigger.classList.remove('is-open');
        }

        if (activeInput === input && !el.classList.contains('hidden')) {
            closePopover();
            return;
        }

        activeInput = input;
        activeTrigger = trigger;
        trigger.classList.add('is-open');

        const titleEl = el.querySelector('.cp-title');
        if (titleEl) {
            titleEl.textContent = input.dataset.colorLabel || 'Выбор цвета';
        }

        const hex = normalizeHex(input.value, '#6366f1');
        const rgb = hexToRgb(hex);
        currentHsv = rgbToHsv(rgb.r, rgb.g, rgb.b);

        renderCharacterSwatches();
        el.classList.remove('hidden');
        renderPopoverState(hex);
        positionPopover(trigger);
    }

    function closePopover() {
        if (popoverEl) {
            popoverEl.classList.add('hidden');
        }
        if (activeTrigger) {
            activeTrigger.classList.remove('is-open');
        }
        activeInput = null;
        activeTrigger = null;
    }

    function mountInput(input) {
        if (input._studioColorMounted) {
            syncTriggerFromInput(input);
            return;
        }

        const initialHex = normalizeHex(input.value, '#6366f1');
        setNativeInputValue(input, initialHex);
        input.classList.add('hidden');

        const trigger = document.createElement('button');
        trigger.type = 'button';
        trigger.className = 'color-picker-trigger';
        trigger.setAttribute('aria-label', input.dataset.colorLabel || 'Выбрать цвет');

        const dot = document.createElement('span');
        dot.className = 'color-swatch-dot';
        dot.style.backgroundColor = initialHex;

        const label = document.createElement('span');
        label.className = 'color-hex-label';
        label.textContent = initialHex.toUpperCase();

        trigger.append(dot, label);
        input.insertAdjacentElement('afterend', trigger);

        input._studioColorTrigger = trigger;
        input._studioColorMounted = true;
        hookInputValueSetter(input);

        trigger.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            openPopover(input, trigger);
        });
    }

    function init() {
        document.querySelectorAll('input.studio-color-input').forEach(mountInput);
    }

    function syncAll() {
        document.querySelectorAll('input.studio-color-input').forEach((input) => {
            mountInput(input);
            syncTriggerFromInput(input);
        });
    }

    window.StudioColorPicker = {
        init,
        syncAll,
        syncInput: syncTriggerFromInput,
        close: closePopover
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
