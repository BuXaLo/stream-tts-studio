# Запуск и эксплуатация

## Запуск

Проект ориентирован на Windows portable deployment. Корневой `start_server.bat`:
- вычисляет каталог проекта через `%~dp0`;
- запускает `cosyvoice3\upy\python.exe`;
- передаёт ему `server\app.py`.

Перед запуском должны присутствовать portable Python, CosyVoice runtime, модели и FFmpeg по ожидаемым путям. Эти артефакты не включены в Git tree, доступный аудиту.

README рекомендует путь установки без кириллицы, пробелов и специальных символов. По умолчанию Dashboard открывается на `http://127.0.0.1:8765/dashboard`.

## Runtime paths

| Path | Роль |
|---|---|
| `cosyvoice3/` | portable runtime, модели, FFmpeg, cache |
| `characters/` | voice.wav и avatar.png по персонажам |
| `server/config.json` | host, port, n_timesteps, auto_open_browser |
| `server/presets.json` | метаданные и темы персонажей |
| `server/active_character.json` | выбранный персонаж |
| `server/da_config.json` | DonationAlerts/Streamer.bot settings |
| `server/da_tokens.json` | OAuth tokens |
| `server/temp/` | временные аудиофайлы |
| `server/fonts/custom/` | пользовательские шрифты |

## Конфигурация по умолчанию

- host: `127.0.0.1`
- port: `8765`
- n_timesteps: `6`
- auto_open_browser: `true`

Backend ограничивает n_timesteps диапазоном 4–15 при сохранении через API. Другие значения требуют проверки и валидации.

## Проверка работоспособности

1. Запустить BAT и убедиться, что CosyVoice загрузился без ошибки.
2. Открыть Dashboard и проверить загрузку списка персонажей.
3. Проверить, что выбранный персонаж содержит voice reference.
4. Выполнить короткую генерацию через Dashboard или `POST /speak`.
5. Открыть `/overlay?test` для проверки визуального расположения.
6. Проверить соединение OBS Browser Source с `/ws/overlay`.
7. DonationAlerts проверять только после настройки OAuth и Streamer.bot action.

## Резервное копирование

Резервировать отдельно:
- `characters/`;
- `server/presets.json`;
- `server/active_character.json`;
- `server/config.json`;
- `server/da_config.json` и `server/da_tokens.json` (как секретные данные);
- пользовательские шрифты.

Не хранить OAuth secrets в публичном Git. При переносе на другой ПК токены DonationAlerts могут потребовать повторной авторизации.

## Диагностика

- Модель не загружается: проверить portable Python, CUDA/PyTorch, модель CosyVoice и доступность GPU.
- Ошибка генерации: проверить наличие персонажа и `voice.wav`, корректность reference text, доступную VRAM.
- Не работает Overlay: проверить `/ws/overlay`, порт и URL Browser Source.
- Не приходят донаты: проверить OAuth, состояние worker, Centrifugo connection и доступность Streamer.bot `/DoAction`.
- Нет конвертации аудио: проверить `cosyvoice3/tools/ffmpeg.exe`.

## Эксплуатационные ограничения

Не запускать сервер на публичном интерфейсе до реализации аутентификации, ограничений CORS и безопасного доступа к API. Сейчас backend не предоставляет полноценного защищённого multi-user режима.
