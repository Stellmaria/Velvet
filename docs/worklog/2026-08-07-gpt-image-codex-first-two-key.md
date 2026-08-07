# Сессия: GPT Image 2 Codex-first, two-key Byesu fallback и high-res export

- Дата: 2026-08-07
- ID: `2026-08-07-gpt-image-codex-first-two-key`
- Линия/фаза: Hermes / GPT Image 2 / production recovery
- Статус: `частично`
- Ветка: `fix/gpt-image-codex-first-two-keys`
- Базовый commit: `8282a8c0c6b7143caef8d8b26f4def7b55c4e9d6`

## Перед началом

### Цель

Привести GPT Image 2 к единому owner-контракту:

- проверять живой лимит Codex непосредственно перед creative generation;
- использовать Codex первым для 1K, 2K и 4K;
- для успешных Codex 2K/4K после единственной creative generation выполнять отдельный GPT/Codex export pass уже над готовым artifact;
- переходить на Byesu только при подтверждённом Codex subscription limit;
- использовать Hermes-Codex Byesu key для анализа и отдельный Media Gen key для image generation;
- убрать legacy `Hermes-GPT-Pro` provider alias и не возвращаться к трёхключевой схеме.

### Исходный контекст

Production checkout находился на `0dceb104` и отставал от `origin/main`. Во время
reconcile `hermes-coders.service` прошёл runtime и sandbox smoke, но упал на
`tier_provider_smoke` с `velvet: Luna unavailable to shared key`. Из-за зависимости
router от coder service затем остановился `hermes-coder-router`, после чего Velvet
Bot получил `Temporary failure in name resolution` для `hermes-coder-router:8878`.

Отдельная проверка current `main` показала две ошибки image-контракта:

- `uses_codex_primary()` выбирал Codex только для 1K, поэтому 2K/4K шли напрямую в Byesu;
- `ByesuImageClient` использовал один `BYESU_HERMES_CODEX_API_KEY` и для анализа, и для image endpoint, а capability gate требовал от одного token group текстовые и media-модели одновременно.

### Планируемый объём

- сделать live Codex limit preflight одинаковым для всех поддерживаемых quality;
- удалить parameter-driven direct Byesu route;
- разделить Hermes-Codex и Media Gen credentials;
- сохранить Media Gen secret только в Velvet coder boundary;
- добавить separate provider capability smoke;
- реализовать post-generation Codex high-resolution export для 2K/4K без второго `image_gen`;
- добавить Pillow в coder image и exact pixel verification;
- обновить release graph, systemd lifecycle, regression tests и документацию;
- не менять production secret values из GitHub.

### Критерии готовности

- 1K/2K/4K являются Codex-first;
- Byesu запускается только при `subscription_limit`;
- до creative generation активные 100% Codex windows переключают на Byesu, неопределённый preflight fail-open пробует Codex;
- Hermes-Codex key и Media Gen key обязаны быть физически различными;
- analysis `/responses` использует Hermes-Codex key, image endpoints используют Media Gen key;
- Max не получает Media Gen secret;
- Codex 2K/4K имеет отдельный GPT export pass над уже созданным изображением и точную pixel verification;
- post-generation export не вызывает `image_gen` повторно;
- provider/image smoke fail-closed при неверном key capability;
- protected CI полностью зелёный до merge;
- production activation выполняется отдельно после secret rotation.

### Риски и ограничения

- live Codex subscription state и реальные Byesu model grants нельзя доказать CI;
- post-generation high-res pass может столкнуться с лимитом уже после успешной creative generation; в этом случае runtime не должен создавать второе изображение через Byesu;
- resize/export увеличивает количество пикселей, но не изобретает истинную нативную детализацию отсутствующего исходника;
- Media Gen secret нельзя проецировать через общий Compose wrapper, иначе расширится secret surface systemd lifecycle;
- существующий production Hermes-Codex credential должен быть заменён на ключ, который действительно видит требуемые coder/analysis модели.

## После завершения

### Фактически сделано

`byesu_image_routing_policy.py` переведён на Codex-first для 1K/2K/4K. Quality
больше не является причиной direct Byesu route. Byesu остаётся только
subscription-limit fallback, включая preflight skip при явно активном exhaustion.

`RoutedByesuImageClient` теперь использует два credential boundary:

- `BYESU_HERMES_CODEX_API_KEY` для analysis `/responses` и analysis model capability;
- `BYESU_MEDIA_GEN_API_KEY` для image generation/edit endpoints и image model capability.

Runtime проверяет, что два ключа различаются, и выполняет `GET /models` отдельно
для каждого. Один token group больше не обязан видеть текстовые и image-модели
одновременно.

Media secret не передаётся через `compose_image_runtime_env.py`. Добавлен
`prepare_image_secret_env.py`, который атомарно создаёт mode `0600`
`/srv/hermes-coders/secrets/velvet-media.env` только с Media Gen key. Этот env
подключён только к `hermes-coder-velvet`; Max его не получает. При включённом
fallback отсутствие Media Gen key блокирует lifecycle fail-closed.

Добавлен `image_provider_smoke.py`: при выключенном fallback он не требует media
credential; при включённом проверяет distinct keys, Sol/Terra/Luna на
Hermes-Codex key и `gpt-image-2`/`firefly-gpt-image-2` на Media Gen key.

Добавлен `codex_image_high_res_export.py`. После успешной Codex creative generation:

- 1K сразу остаётся финальным artifact;
- 2K/4K запускают второй Codex/GPT pass;
- второй pass явно запрещает `image_gen` и запускает подготовленный локальный Pillow export;
- результат проверяется на точные dimensions;
- status/content не сообщают преждевременный `completed`, пока export не закончен;
- Byesu-generated 2K/4K не проходят через дополнительный Codex export.

Coder image дополнен `python3-pil`. Runtime source/import graph и systemd permission
contract включают новый module. Systemd start/reload готовит isolated media env,
затем запускает Compose и после основных smoke выполняет image provider smoke.

Legacy provider alias `byesu-gpt-pro` удалён из `deploy/hermes-coders/config.yaml`;
Luna использует единый `byesu-coder` provider на Hermes-Codex physical key.
`.env.hermes.example` описывает два физических Byesu keys и совместимые alias
`OPENAI_API_KEY` + `BYESU_HERMES_CODEX_API_KEY` для одного Hermes-Codex key.

### Миграции и совместимость

SQL-миграций нет. `OPENAI_API_KEY` остаётся совместимым alias для основного Hermes,
но не является третьим физическим ключом. Production должен содержать два физических
Byesu credentials:

1. Hermes-Codex key, записанный одинаковым значением в `OPENAI_API_KEY` и
   `BYESU_HERMES_CODEX_API_KEY`;
2. отдельный `BYESU_MEDIA_GEN_API_KEY`.

`CODEX_IMAGE_BYESU_FALLBACK_ENABLED` остаётся выключенным до live capability
verification. Это позволяет обновить код и ключи без случайного платного fallback.

### Проверки

Добавлены/обновлены regression tests для:

- Codex-first routing всех quality;
- отсутствия direct Byesu quality route;
- split credential contract и independent capability gates;
- exact 2K/4K dimensions и prohibition второго `image_gen`;
- high-res status/content guard;
- Media Gen secret isolation и mode `0600`;
- image provider smoke lifecycle;
- runtime release/import graph;
- preflight install order и coverage всех quality.

Protected CI запущен на PR #699. Первый прогон `type check` прошёл. `project notes contract`
корректно потребовал этот канонический раздел `### PR и commit`; запись обновлена без
изменения runtime-кода. Live provider availability и реальные Codex windows
проверяются только после production secret rotation.

### PR и commit

- PR: #699 `Fix GPT Image 2 Codex-first routing and split Byesu keys`.
- Ветка: `fix/gpt-image-codex-first-two-keys`.
- Ветка синхронизирована с `main` merge-коммитом `9e748361712d1082192153a8d95fa1360e2e94a1` перед открытием PR.
- Следующие commit SHA фиксируют только CI/contract corrections на этой же ветке.
- Merge допустим только для exact reviewed head после terminal green protected CI и `behind_by=0`.

### Незавершённое

- дождаться terminal protected CI и исправить CI regressions без ослабления security/provider gates;
- перед merge снова подтвердить `behind_by=0` относительно current `main`;
- merge только exact reviewed head;
- обновить production checkout с текущего устаревшего SHA до merge commit;
- заменить production Hermes-Codex physical key на правильную token group и записать его в оба alias;
- добавить отдельный Media Gen physical key;
- сначала оставить Byesu image fallback выключенным и выполнить canonical reconcile;
- подтвердить `hermes-coders.service`, router и bot DNS health;
- выполнить capability smoke двух ключей;
- только после его успеха включить Byesu image fallback и reconcile повторно;
- выполнить live 1K/2K/4K Codex smoke и limit-driven Byesu smoke;
- после подтверждения новой двухключевой схемы удалить старый `Hermes-GPT-Pro` API key в Byesu dashboard.

### Следующий шаг

Довести protected CI PR #699 до terminal green, повторно синхронизировать ветку при
движении `main` и объединить только exact head. Production secrets и activation не
менять, пока merge commit не зафиксирован и capability plan не готов.
