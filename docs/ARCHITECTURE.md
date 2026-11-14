# Архитектура

## 1. Назначение и модель поставки

Stream TTS Studio — локальное Windows-приложение для синтеза речи на базе CosyVoice 3, предназначенное прежде всего для связки OBS и Streamer.bot во время стримов.

**Репозиторий не является полным дистрибутивом.** В Git хранится прикладной код Stream TTS Studio. Python, portable runtime, ядро CosyVoice, ML-библиотеки, модели, FFmpeg и вспомогательные инструменты находятся отдельно в большом архиве. Сначала разворачивается/обновляется этот базовый архив, затем поверх него накладывается код проекта. Окружение изолировано от системного Python и системных инструментов.

Следствие: изменения в приложении не должны самовольно обновлять, переустанавливать или заменять компоненты portable archive. Версии и внутреннее устройство архива нельзя достоверно установить по одному Git-репозиторию.

## 2. Эксплуатационный контекст

Владелец сообщил о многих часах успешной работы на реальных стримах, включая генерацию аудио и интеграцию OBS + Streamer.bot. Это подтверждает, что существующий пользовательский тракт является ценным рабочим baseline. При разработке его следует считать критичным и сохранять совместимость, пока не доказана необходимость изменения.

Целевой сценарий — локальный ПК, один пользователь/оператор, локальный backend и OBS Browser Source. Не следует без отдельного решения превращать приложение в сетевой или multi-user сервис.

## 3. Технологический стек

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
| ML runtime | Изолированная portable-среда; точные версии определяются архивом поставки |

## 4. Структура Git-репозитория

```text
server/
├── app.py
├── launcher.pyw  # Windows launcher, tray и локальный HTTP для монитора
└── studio/
    ├── core/
    │   ├── env.py
    │   ├── config.py
    │   ├── storage.py
    │   ├── validation.py
    │   └── ws.py
    ├── services/
    │   ├── text.py
    │   ├── tts_engine.py
    │   ├── da_worker.py
    │   ├── donations.py
    │   ├── streamerbot.py
    │   └── audio_tools.py
    └── routes/
        ├── pages.py
        ├── system.py
        ├── donations.py
        ├── characters.py
        ├── fonts.py
        ├── tools.py
        └── speak.py
tests/
.github/workflows/tests.yml
```

Runtime-данные и portable archive могут присутствовать в рабочей установке, но отсутствуют в Git. `server/app.py` остаётся штатной точкой запуска: bootstrap путей, настройка окружения, загрузка модели, создание FastAPI и подключение роутеров.
 
## 5. Компоненты и потоки

### Backend

`server/app.py` — тонкий entrypoint. Он первым добавляет `server/` в `sys.path`, затем вызывает `studio.core.env.configure_environment()` до импорта PyTorch/CosyVoice, загружает модель через `studio.services.tts_engine`, создаёт FastAPI и подключает APIRouter.

- `studio.core`: пути и переменные окружения, конфигурация, атомарное хранилище, валидация и WebSocket manager.
- `studio.services`: текст, CosyVoice inference, DonationAlerts worker/parser, Streamer.bot delivery и FFmpeg helper.
- `studio.routes`: страницы/WS, системные настройки, DonationAlerts OAuth/API, персонажи, шрифты, инструменты и `POST /speak`.

Whisper/Demucs и аудио endpoint orchestration находятся в `routes/tools.py`; `services/audio_tools.py` содержит общий FFmpeg helper. GPU-модель и генерация остаются в TTS service.

Этап разнесения монолитного backend завершён. Текущая структура разделяет bootstrap, core, services и routes; дальнейшее выделение модулей выполнять только при конкретной необходимости, сохраняя контракты и регрессионное покрытие.

### Dashboard
Статическая панель для персонажей, голосовых референсов, аудио-инструментов, настроек и интеграций. `builder.js` генерирует C# Actions для Streamer.bot. Существующие поля, имена и формат генерируемого кода являются совместимым интерфейсом.

Настройка `auto_open_browser` управляет автоматическим открытием Dashboard только при прямом запуске backend. В `server/app.py` это ограничено условием `not monitor_mode`; Launcher устанавливает `STUDIO_MONITOR_MODE=1`, поэтому при запуске через `start_studio.bat` открывается Monitor, а Dashboard доступен отдельно из меню трея.

### OBS Overlay
Browser Source получает конфигурацию/тему через HTTP и события реплик по WebSocket `/ws/overlay`. Текст реплики может включать недоверенный ввод зрителей/донатеров. Безопасное отображение текста должно сохранять визуальные режимы, анимации, тайминги и CSS.

### Streamer.bot
Внешний C# Action отправляет текст на `POST /speak`, получает WAV и воспроизводит его в текущем сценарии Streamer.bot. Нельзя менять URL, HTTP method, обязательные поля, тип ответа или поведение воспроизведения без согласованного переходного периода.

### DonationAlerts
OAuth и worker получают события донатов и вызывают настроенный Streamer.bot action. Секреты OAuth являются чувствительными локальными данными; UI/API должны позволять настраивать их, не раскрывая сохранённое значение обратно.

## 6. Критические контракты совместимости

Перед любым изменением сохранять и проверять:
- запуск через `start_studio.bat` (Launcher + tray) и резервный `start_server.bat` (консольный backend);
- существующие каталоги, имена файлов, JSON-ключи и идентификаторы персонажей;
- REST routes, HTTP methods, поля запросов и типы ответов, особенно `POST /speak`;
- WebSocket endpoint и структуру события Overlay;
- URL и параметры OBS Browser Source;
- сгенерированные C# Actions и адреса Streamer.bot;
- порядок генерации/передачи WAV и отображения текста;
- пользовательские темы, анимации и настройки Dashboard.

## 7. Хранение

Конкретные runtime-пути и правила резервного копирования описаны в [OPERATIONS.md](OPERATIONS.md). Не менять JSON-схемы и пути «заодно» с исправлением безопасности. Любая необходимая миграция должна быть отдельной, обратимой и протестированной на копии пользовательских данных.


## Desktop monitor

Рекомендуемый запуск — `start_studio.bat`. Батник проверяет portable `python.exe`, `pythonw.exe` и `server/launcher.pyw`, затем запускает Launcher через `pythonw.exe`. Если portable Python или `pythonw.exe` отсутствует, он вызывает резервный `start_server.bat`.

Launcher создаёт обязательную иконку системного трея, поднимает локальный HTTP-сервер только на loopback и запускает backend отдельным процессом через portable `python.exe`. Основной интерфейс монитора — отдельное окно `pywebview` на WebView2. Если пакет `pywebview` или WebView2 Runtime недоступен, используется запасной режим: Edge с `--app=` (если Edge найден), иначе системный браузер. Во время загрузки модели монитор опрашивает Launcher и показывает `logs/startup.log`; после готовности backend подключается к `/ws/monitor` и получает историю и новые события.

Режим выбирается один раз при старте. Причина фиксируется в `logs/startup.log` строкой «Режим окна монитора: pywebview …» или «Режим окна монитора: Edge/браузер (причина)». Для принудительного возврата к запасному режиму используется `STUDIO_MONITOR_WINDOW=browser` в окружении процесса, запустившего `start_studio.bat`.


### Manifest монитора и попытка улучшить иконку панели задач

Для попытки повысить чёткость иконки отдельного окна монитора Edge App Mode добавлен Web App Manifest. Реализация затронула **три файла**, каждый первоначально отдельным коммитом:

- `web/monitor/manifest.webmanifest` — манифест с именем монитора, режимом `standalone` и ссылкой на существующий `/favicon.ico` ([f4565d76](https://github.com/BuXaLo/stream-tts-studio/commit/f4565d76d66e591be7e52e77bd5682c156f9851d)).
- `web/monitor/index.html` — подключение манифеста через `<link rel="manifest">` ([7c767bbf](https://github.com/BuXaLo/stream-tts-studio/commit/7c767bbf92c4d640defb4df994bf51b164723eef)).
- `server/launcher.pyw` — раздача `/manifest.webmanifest` с MIME-типом `application/manifest+json; charset=utf-8` ([4329fb8c](https://github.com/BuXaLo/stream-tts-studio/commit/4329fb8c631a0d51a76dc76f361540e1d04102aa)).

Последующая корректировка манифеста отдельным коммитом [73799ef9](https://github.com/BuXaLo/stream-tts-studio/commit/73799ef98ef52b4c327e3bb4e3d80ae8ff3061c5): `start_url` установлен в `/?launcher=1`, чтобы сохранять Launcher-режим; убраны явно заданные размеры иконки. Таким образом, для полного просмотра истории нужно смотреть diff всех четырёх коммитов, а не только создания файла манифеста.

Манифест не устранил размытие значка в Edge App Mode и сохранён как статические метаданные для запасного режима. В основном режиме `pywebview` Launcher задаёт отдельный AppUserModelID (`StreamTTSStudio.Monitor`) и назначает большую и малую оконные иконки из `web/dashboard/favicon.ico` через `WM_SETICON`. Это реализация исправления для основного режима; Edge/browser fallback по-прежнему зависит от собственного механизма иконки браузера.

В режиме `pywebview` крестик скрывает окно, не завершая Launcher или backend; двойной щелчок по значку трея и пункт меню «Открыть монитор» возвращают то же окно. При выборе «Выход» окно закрывается, после чего Launcher штатно останавливает backend. В Edge/browser fallback окно закрывается вручную; сам Launcher и backend продолжают работать до команды «Выход». Меню также содержит «Открыть Dashboard» (браузер по умолчанию, URL `/dashboard/`) и «Выход»: Launcher выставляет сигнал закрытия в `/launcher-status`, монитор закрывает своё окно, затем Launcher штатно завершает backend и себя. Кнопка монитора запускает остановленный backend или останавливает работающий. Ошибка создания трея не маскируется: запуск прерывается, traceback записывается в `logs/startup.log`.

`start_server.bat` — альтернативный прямой консольный запуск `server/app.py` без Launcher и системного трея; сохраняет привычный вывод консоли и штатное поведение открытия Dashboard. Не запускайте оба режима одновременно: mutex приложения защищает от второго экземпляра и не допускает параллельного запуска двух backend-процессов. При повторном запуске пользователь должен закрыть/использовать уже работающий экземпляр, а не рассчитывать на второй сервер.

Монитор обслуживается локальным загрузчиком и backend-маршрутами `/monitor`, `/ws/monitor`, `/api/monitor/shutdown`. В launcher-режиме команда кнопки проходит через локальный `/launcher-stop`, который вызывает штатный механизм backend. WebSocket `/ws/overlay`, `POST /speak`, WAV-ответы и их схемы не меняются. События генерации формируются в общем `generate_voice`; время синтеза не включает последующую доставку WAV клиенту. Логи передаются отдельным обработчиком в `studio`, root и Uvicorn loggers; файловые логи сохраняются.


### Сбор startup.log в Monitor между циклами backend

В режиме Launcher Monitor читает `logs/startup.log` через локальный endpoint `/startup-log?offset=N`. Позиция чтения передаётся в байтах и сохраняется на протяжении жизни Monitor: остановка и повторный запуск backend не обнуляют offset и не очищают уже показанную историю.

Для каждого цикла backend сбор возобновляется перед запуском или ручной остановкой. При запуске Monitor читает журнал до достижения прежнего критерия готовности backend и DonationAlerts, после чего приостанавливает сбор. При ручном Stop сбор остаётся активным до завершения запроса `/launcher-stop`: этот запрос синхронно ожидает остановки backend, а Launcher фиксирует итоговый код завершения и сбрасывает запись журнала. После ответа Monitor выполняет финальное чтение хвоста и только затем завершает сбор. Это не даёт параллельному опросу статуса преждевременно закрыть сбор до появления последних shutdown-строк.

История событий Monitor и счётчики сохраняются между циклами backend, пока работает сам Monitor. После полного завершения Launcher/Monitor новый процесс начинает собственную сессию отображения.

Доработка не меняет непрерывную запись `startup.log`, stdout/stderr backend, `studio.log`, WebSocket `/ws/monitor` и `/ws/overlay`, `POST /speak`, WAV-контракт или `start_server.bat`. Прямой консольный режим не использует жизненный цикл Launcher Monitor.
