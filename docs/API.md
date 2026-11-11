# HTTP и WebSocket API

Базовый адрес по умолчанию: `http://127.0.0.1:8765`. Маршруты разделены на APIRouter в `server/studio/routes/`; `server/app.py` подключает их. Swagger доступен на `/docs`, если сервер запущен с настройками FastAPI по умолчанию.

## Основные маршруты

| Метод | Путь | Назначение |
|---|---|---|
| GET | `/` | Dashboard index |
| GET | `/overlay`, `/overlay/` | OBS Overlay |
| WS | `/ws/overlay` | WebSocket для событий Overlay |
| GET | `/api/system_config` | Системная конфигурация и состояние WS |
| POST | `/api/system_config` | Сохранение host/port/n_timesteps/browser flag; port — целое 1–65535 |
| GET | `/api/da/config` | Настройки и статус DonationAlerts |
| POST | `/api/da/config` | Сохранение настроек DonationAlerts |
| GET | `/api/da/auth_url` | Формирование OAuth URL |
| GET | `/api/da/callback` | OAuth callback |
| POST | `/api/da/test_donation` | Тестовый вызов Streamer.bot; при отказе HTTP 502 с причиной |
| GET | `/api/presets` | Список персонажей и активный ID |
| POST | `/api/presets/set_active` | Выбор активного персонажа |
| GET | `/api/active_overlay_config` | Тема и аватар персонажа |
| GET | `/api/fonts` | Список пользовательских шрифтов |
| POST | `/api/upload_font` | Загрузка шрифта |
| POST | `/api/trim_and_transcribe` | Обрезка WAV и транскрипция |
| POST | `/api/normalize_audio` | Нормализация аудио |
| POST | `/api/isolate_vocal` | Выделение вокала Demucs |
| POST | `/api/convert_to_telegram_ogg` | Конвертация в OGG/Opus |
| POST | `/api/test_draft_tts` | Пробная генерация с временным/сохранённым голосом |
| POST | `/api/trigger_overlay_preview` | Тестовая реплика Overlay без генерации |
| POST | `/api/characters/save` | Создание/обновление персонажа |
| DELETE | `/api/characters/{char_id}` | Удаление персонажа |
| POST | `/speak` | Генерация WAV для внешней интеграции |

## POST /speak

JSON body:

```json
{
  "text": "Привет, это тест.",
  "character": "mita",
  "speed": 1.0
}
```

- `text` обязателен и не должен быть пустым.
- `character` необязателен: используется активный персонаж.
- `speed` необязателен: используется скорость пресета.
- Ответ: `audio/wav`.
- 400 — пустой/неозвучиваемый текст или некорректный speed; 404 — персонаж/voice.wav не найден; 503 — нехватка VRAM; 500 — другая ошибка генерации.

Пример:

```bash
curl -X POST "http://127.0.0.1:8765/speak" \
  -H "Content-Type: application/json" \
  -d "{\"text\":\"Привет!\",\"character\":\"mita\",\"speed\":1.0}" \
  --output speech.wav
```

## WebSocket /ws/overlay

Overlay подключается к WebSocket на том же origin. Событие, рассылаемое backend, имеет поля:
- `event`: `mita_dialogue`;
- `text`: исходный текст реплики;
- `duration`: длительность WAV в секундах;
- `char_id`: ID персонажа;
- `draft_theme`: необязательная временная тема для предпросмотра.

Overlay также принимает вложенные формы payload с `data` или `message`, если объект содержит `text`. Для HTTP mutation и WebSocket при наличии Origin выполняется проверка same-origin.

## Остальные API

Форматы multipart полей для аудио-эндпоинтов и дополнительные поля персонажей следует сверять с сигнатурами маршрутов в `server/app.py`. В текущей версии API не описан отдельной схемой OpenAPI вне автоматически генерируемой FastAPI документации.
