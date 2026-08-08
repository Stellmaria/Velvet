# Storage Librarian bounded output-length retry

- Дата: 2026-08-08
- ID: `2026-08-08-storage-librarian-length-retry`
- Линия/фаза: Storage Librarian / production output-budget hardening
- Статус: `частично`
- Ветка: `fix/storage-librarian-length-retry`
- Базовый commit: `6a9e61e016341c8d452d92f1e6677493076c16d9`
- Связанный PR: `#736 Add bounded hierarchical Storage Librarian chunking` уже merged

## Перед началом

### Цель

Закрыть оставшийся после bounded chunking класс terminal failures `Ollama analysis did not complete normally: done_reason=length` без silent source truncation, cloud fallback и неограниченного роста числа local Ollama inference calls.

### Исходный контекст

PR #736 закрыл oversized input: источники выше single-shot envelope теперь анализируются ordered chunks с bounded final synthesis, а многомегабайтные источники fail-closed отбрасываются по hard chunk-plan cap. При этом сам Ollama analysis client всё ещё считал любой `done_reason != stop` terminal failure.

В production до этого наблюдались реальные terminal failures Storage объектов `#35` и `#36` с `done_reason=length`. Это отдельный output-budget defect: вход уже дошёл до модели, но структурированный JSON не успел завершиться в `num_predict`.

### Планируемый объём

- ограничить JSON Schema так, чтобы модель не могла бесконечно раздувать summary/tags/entities/action_items;
- разрешить максимум один повтор конкретного logical analysis call только после `done_reason=length`;
- на повторе увеличить `num_predict` только если увеличенный output budget всё ещё помещается в тот же `num_ctx` вместе с полным исходным prompt;
- никогда не обрезать prompt/source ради retry;
- сохранить один общий wall-clock timeout на обе попытки;
- учитывать фактически потраченные prompt/completion tokens обеих попыток;
- для hierarchical analysis расходовать retry slots только из уже существующего `max_inference_calls`, а не расширять общий CPU budget;
- после исчерпания retry budget или второго `done_reason=length` завершать call terminally;
- остальные abnormal `done_reason`, HTTP/schema/network semantics не менять.

### Критерии готовности

- single-shot `done_reason=length` получает ровно один bounded retry;
- второй `done_reason=length` не создаёт третью попытку;
- near-context prompt не получает увеличенный `num_predict`, если это вытеснило бы вход из context budget;
- hierarchical retry budget вычисляется как `max_inference_calls - (chunk_count + synthesis)` и разделяется между calls одного object analysis;
- план без свободного inference slot не делает retry;
- final usage сообщает фактическое число inference calls и object-level length retries;
- existing valid response, timeout/network, malformed/schema и hard prompt guard contracts не регрессируют;
- package architecture inventory пересобран штатным generator;
- required GitHub CI должен быть зелёным до merge.

### Риски и ограничения

Retry не должен превращать `max_inference_calls=13` в скрытые 26 calls. Поэтому retry slots являются частью существующего object-level inference budget. Для максимального 12-chunk plan (`12 chunks + synthesis = 13`) дополнительных calls нет; защита от output overflow в этом случае опирается на более компактную JSON Schema.

Retry output budget также не может отбирать место у input. Если более высокий `num_predict` уменьшает допустимый prompt envelope ниже фактического prompt, повтор использует исходный output budget и лишь получает второй deterministic attempt.

## После завершения

### Фактически сделано

- JSON Schema получила bounded длины и `maxItems=3` для verbose collections;
- Ollama client различает single-shot, chunk и synthesis session IDs, чтобы вычислять planned object calls;
- свободные retry slots равны разнице между `max_inference_calls` и planned calls;
- `done_reason=length` может выполнить только одну дополнительную попытку текущего logical call и только при наличии свободного object retry slot;
- retry `num_predict` увеличивается максимум до `1536`, но лишь если полный prompt остаётся внутри bounded text context;
- один `asyncio.timeout` ограничивает суммарную длительность обеих попыток текущего logical call;
- usage суммирует prompt/completion tokens первой truncated completion и успешного retry;
- final session добавляет `actual_inference_calls` и `object_length_retries` для object-level observability;
- hard input guard больше не сообщает устаревшее `Chunking is not implemented`, поскольку chunking уже находится в `main`.

### Проверки

- изменённый Ollama client и новый regression test прошли локальный Python syntax compile;
- локально на isolated fake Ollama session проверено: `length -> stop` выполняет 2 calls, увеличивает default `num_predict` `384 -> 768` и суммирует usage;
- near-limit prompt проверен: retry сохраняет `num_predict=384`, если `768` уменьшил бы input budget ниже полного prompt;
- hierarchical plan `2 chunks + synthesis`, `max_inference_calls=4` проверен с одним shared retry: final `actual_inference_calls=4`, `object_length_retries=1`;
- полный hierarchical plan без свободного slot проверен: `done_reason=length` остаётся terminal после одного call;
- GitHub runner validation, canonical inventory regeneration и required CI ещё должны пройти.

### Незавершённое

- прогнать targeted regression tests и canonical package architecture generator на GitHub runner;
- обновить pinned package LOC contract по generated inventory;
- удалить временный validation workflow из итоговой ветки;
- открыть отдельный PR после проверки состава diff;
- после merge отдельно выполнить production rollout и повторную acceptance-проверку реальных failed Storage jobs;
- historical failed jobs не пере-enqueue автоматически в рамках этого изменения.
