# Архитектура

## 1. Назначение

Stream TTS Studio — локальное Windows-приложение для синтеза речи и voice cloning на базе CosyVoice 3. В одном приложении объединены управление персонажами и голосовыми референсами, аудиообработка, HTTP API для внешних автоматизаций, интеграция DonationAlerts и браузерный OBS Overlay.

## 2. Технологический стек

| Слой | Технологии / назначение |
|---|---|
| Backend | Python, FastAPI, Uvicorn |
| TTS | CosyVoice 3, PyTorch, torchaudio, NumPy |
| Распознавание | faster-whisper |
| Очистка голоса | Demucs |
| Аудио I/O | SoundFile, FFmpeg |
| Интеграции | requests, websockets, OAuth DonationAlerts, Streamer.bot HTTP API |
| Dashboard | HTML, CSS, vanilla JavaScript |
| Overlay | HTML, CSS, vanilla JavaScript, WebSocket |
| ML runtime | CUDA/PyTorch; конкретная portable-сборка находится вне Git-дерева |

## 3. Структура репозитория

```text
/
├── README.md
├── start_server.bat
├── server/
│   ├── app.py                 # Backend, API, TTS orchestration
│   └── fonts/
│       ├── fonts.css
│       └── bundled/           # Поставляемые шрифты
├── web/
│   ├── dashboard/
│   │   ├── index.html
│   │   ├── app.js             # UI, персонажи, аудио-редактор, API calls
│   │   ├── builder.js         # Генератор C# для Streamer.bot
│   │   ├── style.css
│   │   └── vendor/            # WaveSurfer, regions
│   └── overlay/
│       ├── overlay.html
│       ├── overlay.js         # WebSocket-клиент и анимация реплик
│       └── overlay.css
└── dosc/                      # Документация проекта
```

Runtime-каталоги создаются или используются backend во время работы: `characters/`, `server/temp/`, `server/fonts/custom/`, а также данные portable CosyVoice в `cosyvoice3/`. JSON-файлы конфигурации/персонажей также создаются при работе и не перечислены как исходные файлы в текущем дереве.

## 4. Компоненты и ответственность

### Backend (`server/app.py`)

Один модуль FastAPI выполняет несколько ролей:
- загрузка CosyVoice при импорте модуля;
- конфигурация путей, кэшей и offline-переменных окружения;
- хранение конфигурации, OAuth-токенов и пресетов в JSON;
- генерация WAV и синхронизация доступа к модели через `generation_lock`;
- обработка аудио (нормализация, Demucs, Whisper, FFmpeg);
- REST API для Dashboard и Streamer.bot;
- WebSocket broadcast для OBS Overlay;
- фоновый DonationAlerts worker.

### Dashboard

Статическая одностраничная панель. `app.js` управляет вкладками, персонажами, референсным аудио, записью/обрезкой/прослушиванием и вызовами API. `builder.js` формирует C# Actions для Streamer.bot.

### OBS Overlay

Browser Source открывает `/overlay`, получает тему/аватар через REST API и подписывается на `/ws/overlay`. Backend рассылает событие реплики; клиент выбирает персонажа/тему и отображает текст с анимацией. При закрытии соединения клиент переподключается с задержкой.

### Интеграции

- **Streamer.bot → Studio:** C# Action отправляет `POST /speak`; в ответ получает WAV. Внешний Action отвечает за воспроизведение (README указывает `CPH.PlaySound()`).
- **DonationAlerts → Studio → Streamer.bot:** Studio получает OAuth-токен, подключается к Centrifugo WebSocket, разбирает донаты и вызывает настроенный Streamer.bot `/DoAction`.
- **Studio → OBS:** backend публикует событие через локальный WebSocket.

## 5. Основные потоки данных

### Генерация речи

1. Клиент отправляет текст, ID персонажа (необязательно) и скорость на `POST /speak`.
2. Backend выбирает активного персонажа, загружает его `voice.wav` и `reference_text`.
3. Текст очищается/нормализуется и разбивается на предложения.
4. Для каждого предложения CosyVoice формирует аудиофрагмент; между предложениями вставляется короткая пауза.
5. Фрагменты сглаживаются, объединяются и кодируются в WAV.
6. Backend возвращает WAV и отправляет в Overlay событие с текстом, длительностью и ID персонажа.

### Подготовка голосового референса

Dashboard загружает аудио. Backend может конвертировать его в mono WAV 24 kHz через FFmpeg, сохранить в персонаже, нормализовать, обрезать и транскрибировать через faster-whisper, либо выделить вокал через Demucs.

### DonationAlerts

1. OAuth callback получает authorization code и сохраняет token response.
2. Worker проверяет access token, при 401 пытается обновить его.
3. Worker получает профиль и socket token, подключается к Centrifugo.
4. Worker подписывается на канал донатов пользователя.
5. При событии извлекает автора, сумму, валюту и сообщение и вызывает Streamer.bot.

## 6. Хранение данных

| Данные | Место |
|---|---|
| Системная конфигурация | `server/config.json` |
| Пресеты персонажей | `server/presets.json` |
| Активный персонаж | `server/active_character.json` |
| DonationAlerts client config | `server/da_config.json` |
| DonationAlerts OAuth tokens | `server/da_tokens.json` |
| Голос и аватар персонажа | `characters/<id>/voice.wav`, `avatar.png` |
| Временные аудиофайлы | `server/temp/` |
| Пользовательские шрифты | `server/fonts/custom/` |
| Модели и cache | `cosyvoice3/` |

Все перечисленные файлы runtime-данных следует считать локальными пользовательскими данными и секретами там, где это применимо. Их резервное копирование и исключение из Git должны быть предусмотрены отдельно.
