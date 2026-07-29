# Grok Imagine v1: фото + текст → видео

Дата: 2026-07-29

## Цель

Сделать рабочим раздел `Мяу → Оживить` на старой модели Kie.ai `grok-imagine/image-to-video`: одно внешнее фото и текстовое описание движения превращаются в короткое видео.

## Реализовано

- отдельный FSM-поток `Оживить`, не смешанный с фото-генерацией;
- выбор ровно одного референса из базы персонажей либо загрузка JPG/PNG/WEBP из Telegram;
- обязательный текст движения до 8000 символов;
- параметры `480p/720p`, `6/10 секунд`, форматы `9:16`, `16:9`, `1:1`, `2:3`, `3:2`;
- безопасные режимы внешнего фото `normal` и `fun`; `spicy` не показывается, потому что Kie не поддерживает его для external image input;
- явный экран проверки стоимости перед платным запуском;
- проверка общего AI-бюджета до постановки задачи;
- session-based dedupe key, защищающий от двойной платной постановки при повторном нажатии;
- provider input содержит одно `image_urls`, `prompt`, `mode`, `duration`, `resolution`, `aspect_ratio` и `nsfw_checker=false` для Mature-режима;
- автоматическая миграция старого `grok-imagine/text-to-video` fallback на `grok-imagine/image-to-video`;
- новый явный env `KIE_GROK_IMAGINE_IMAGE_TO_VIDEO_MODEL`;
- готовый MP4 скачивается worker-ом с Kie и загружается в Telegram байтами, а не передаётся Telegram как временный HTTP URL;
- основной способ доставки — playable `send_video` с `supports_streaming=true`; при отказе Telegram выполняется fallback на оригинальный документ;
- лимит результата 50 МБ, timeout 120 секунд и три попытки скачивания;
- добавлены unit-тесты UI, provider payload, стоимости, безопасных fallback-значений, конфигурации и доставки видео.

## Безопасность и ограничения

- доступ только владельцу по существующему `AccessPolicy`;
- один референс на задачу, согласно старому image-to-video API;
- принимаются только JPG, PNG и WEBP до 10 МБ;
- двойное подтверждение: параметры → проверка → запуск;
- `spicy` исключён для внешних изображений;
- платный provider call не выполняется при превышении лимита запроса, дневного или месячного бюджета;
- повторная доставка не создаёт новую provider generation;
- URL результата скачивается сразу, так как provider URLs могут истекать.

## Конфигурация

Рекомендуемая переменная:

```env
KIE_GROK_IMAGINE_IMAGE_TO_VIDEO_MODEL=grok-imagine/image-to-video
```

Старый `KIE_GROK_IMAGINE_VIDEO_MODEL` остаётся fallback только если содержит image-to-video id. Значение `grok-imagine/text-to-video` автоматически игнорируется в пользу нового безопасного default.

## Источник API-контракта

Официальная документация Kie.ai `Grok Imagine Image to Video` для `/api/v1/jobs/createTask` с моделью `grok-imagine/image-to-video`, одним `image_urls`, prompt, normal/fun mode, duration, 480p/720p и aspect ratio.
