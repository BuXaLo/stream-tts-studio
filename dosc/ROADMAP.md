# План развития

Порядок отражает приоритет по результатам статического аудита. Задачи не считаются выполненными, пока не внесены изменения и не проверены тестами.

## P0 — безопасность

- [ ] Устранить DOM XSS в Overlay: рендерить текст исключительно через text nodes.
- [ ] Устранить HTML injection в DonationAlerts callback.
- [ ] Исключить client_secret и OAuth tokens из GET API response.
- [ ] Добавить OAuth state и одноразовую проверку callback.
- [ ] Ограничить CORS и добавить локальную авторизацию изменяющих API/WS.
- [ ] Добавить ограничения upload size, audio duration и допустимых параметров.

## P1 — устойчивость

- [ ] Перенести синхронные HTTP вызовы DonationAlerts worker на async HTTP client.
- [ ] Добавить корректное завершение worker в lifespan shutdown.
- [ ] Добавить единый error handling и структурированное логирование с redaction секретов.
- [ ] Защитить файловые операции от конкурентной записи и частично записанных JSON.
- [ ] Добавить очистку старых временных файлов при старте.

## P2 — архитектура

Предлагаемая структура backend:

```text
server/
├── app.py
├── core/
│   ├── config.py
│   └── paths.py
├── api/
│   ├── routes/
│   │   ├── characters.py
│   │   ├── audio.py
│   │   ├── system.py
│   │   └── donations.py
│   └── schemas/
├── services/
│   ├── tts.py
│   ├── audio.py
│   ├── whisper.py
│   ├── demucs.py
│   ├── overlay.py
│   └── donation_alerts.py
├── repositories/
│   ├── characters.py
│   └── settings.py
└── tests/
```

- [ ] Перенести инициализацию ML engine в FastAPI lifespan.
- [ ] Ввести интерфейс TTS engine и mock для unit tests.
- [ ] Разделить routers, services, repositories и schemas без изменения публичного API.
- [ ] Зафиксировать версии зависимостей и документировать сборку portable runtime.

## P3 — качество и сопровождение

- [ ] Pytest: API contract, characters, sanitization, OAuth state, upload validation.
- [ ] Frontend tests для Overlay payload и text escaping.
- [ ] Smoke test запуска без GPU (с mock engine).
- [ ] CI: lint, type checks, unit tests, secret scan.
- [ ] Документировать версии моделей, CUDA, PyTorch, FFmpeg и лицензии.
- [ ] Ввести версионирование конфигураций и миграции JSON.
- [ ] Добавить health/readiness endpoints и понятный статус загрузки модели.

## Критерии завершения аудита

- [ ] Все P0 закрыты и покрыты регрессионными тестами.
- [ ] API endpoints и payloads сверены с фактической реализацией.
- [ ] Smoke/integration tests выполнены на целевой Windows + NVIDIA среде.
- [ ] Runtime dependency inventory и SBOM сохранены в документации.
