# 2026-07-29 — оригинальные файлы результатов Kie

- Дата: 2026-07-29
- ID: kie-original-file-delivery
- Линия/фаза: Линия B — Velvet AI / media generation
- Статус: `завершено`
- Ветка: `agent/kie-original-file-delivery`
- Базовый commit: `a51fef4d4c267cedd66b183f9b2ac52c23214c74`

## Перед началом

### Цель

Отправлять изображения, созданные через «Мяу», в Telegram как оригинальные файлы-документы без дополнительного сжатия режима photo.

### Исходный контекст

После успешной генерации Kie worker передавал provider URL напрямую в `send_photo`. Telegram воспринимал результат как фотографию и создавал сжатую версию. Владельцу нужен исходный файл, который Kie разместил по result URL.

### Планируемый объём

- скачать байты каждого изображения с provider result URL;
- определить расширение по URL или `Content-Type`;
- сформировать безопасное имя файла с provider task id;
- отправить изображение через `send_document` и `BufferedInputFile`;
- оставить текущую доставку видео через `send_video`;
- ограничить загрузку результата размером 50 МБ;
- добавить сетевые повторы и browser-compatible `User-Agent`;
- покрыть доставку unit-тестами;
- подключить новый worker в production registry.

### Критерии готовности

- image result не передаётся в `send_photo`;
- Telegram получает `BufferedInputFile` с исходными байтами;
- имя файла имеет корректное расширение;
- подпись сообщает, что файл отправлен без сжатия Telegram;
- video result продолжает использовать `send_video`;
- пустой или слишком большой provider response не приводит к повторному платному вызову генерации;
- tests, type check, Docker build и project notes contract проходят.

### Риски и ограничения

- файл загружается в память перед передачей Telegram;
- установлен предел 50 МБ на один результат;
- ошибка скачивания или Telegram delivery происходит после успешного завершения provider task и не должна повторять платную генерацию;
- исходное качество ограничено самим файлом Kie, бот не выполняет дополнительное преобразование или апскейл.

## После завершения

### Фактически сделано

- добавлен `file_delivery_worker.KieGenerationWorker`, наследующий существующий queue worker;
- image results скачиваются с result URL и отправляются через `send_document`;
- используются оригинальные байты provider response без перекодирования;
- добавлено определение PNG, JPEG, WEBP, GIF, BMP и TIFF;
- имя строится как `meow-<provider-task-id>-<index>.<ext>`;
- download выполняется с timeout, тремя попытками и browser-compatible `User-Agent`;
- Content-Length и фактически прочитанный объём ограничены 50 МБ;
- видео остаётся в прежнем `send_video` flow;
- production worker registry переведён на новый delivery worker;
- добавлены unit-тесты документа, имени файла и video compatibility.

### Миграции и совместимость

Миграции базы и новые переменные `.env` не требуются. Queue lifecycle, бюджет, provider calls, progress и retry генерации не изменены. Меняется только best-effort доставка уже готового результата.

### Проверки

Ожидаются автоматические проверки GitHub Actions:

- полный tests workflow;
- type check;
- Docker build;
- project notes contract.

Live Kie-запросы в CI не выполняются.

### PR и commit

- PR: будет создан после фиксации файлов;
- ветка: `agent/kie-original-file-delivery`;
- базовый commit: `a51fef4d4c267cedd66b183f9b2ac52c23214c74`.

### Незавершённое

- провести live smoke генерации одного изображения после обновления локального бота;
- при необходимости позже добавить отдельный режим отправки видео как document без Telegram video processing.

### Следующий шаг

Слить PR после зелёного CI, обновить локальный `main`, перезапустить Supervisor и создать новую генерацию «Мяу» для проверки получения PNG/JPEG как файла.
