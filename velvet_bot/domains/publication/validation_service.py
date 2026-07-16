from __future__ import annotations

import re

from velvet_bot.channel_analytics import (
    analyze_prompt_text,
    compact_identity,
    extract_hashtags,
    extract_links,
)
from velvet_bot.domains.publication.constants import (
    CAPTION_LIMIT,
    MEDIA_GROUP_LIMIT,
    TEXT_LIMIT,
)
from velvet_bot.domains.publication.models import PublicationDraft, PublicationIssue
from velvet_bot.domains.publication.repository import PublicationRepository
from velvet_bot.domains.publication.validation_repository import (
    PublicationValidationRepository,
)
from velvet_bot.post_classification import classify_post

_STORY_REQUIRED_UNIVERSES = frozenset({"shs", "kr", "lm", "idm", "lagerta"})
_ADULT_RE = re.compile(
    r"(?:^|[^\w])(?:18\+|nsfw|art\s*nude|nude|ню|обнаж|эрот|без\s+одежд)",
    re.IGNORECASE,
)
_URL_CANDIDATE_RE = re.compile(r"(?:https?://|t\.me/)[^\s<>]+", re.IGNORECASE)


class PublicationValidationService:
    """Validate publication content without opening PostgreSQL connections directly."""

    def __init__(
        self,
        *,
        drafts: PublicationRepository,
        validation: PublicationValidationRepository,
    ) -> None:
        self._drafts = drafts
        self._validation = validation

    async def validate(self, draft_id: int, *, owner_id: int) -> PublicationDraft:
        draft = await self._drafts.get_draft(draft_id, owner_id=owner_id)
        if draft is None:
            raise ValueError("Черновик не найден.")

        text = draft.text_content.strip()
        hashtags = extract_hashtags(text)
        prompt = analyze_prompt_text(text)
        media_type = draft.items[0].media_type if draft.items else "text"
        classification = classify_post(
            text,
            hashtags,
            is_prompt=prompt.is_prompt,
            media_type=media_type,
        )
        issues: list[PublicationIssue] = []

        self._validate_telegram_limits(draft, text, issues)

        tag_keys = [compact_identity(normalized) for _, normalized in hashtags]
        context = await self._validation.load_context(
            draft,
            normalized_aliases=tag_keys,
            text=text,
        )
        resolved_keys = {item.normalized_alias for item in context.characters}
        unresolved = [
            display
            for display, normalized in hashtags
            if compact_identity(normalized) not in resolved_keys
            and not re.fullmatch(r"[a-f0-9]{6}", normalized)
        ]

        if unresolved:
            issues.append(
                PublicationIssue(
                    "unresolved_tags",
                    "warning",
                    "Нераспознанные хэштеги",
                    ", ".join(f"#{value}" for value in unresolved[:12]),
                )
            )
        if classification.post_type in {"art", "prompt"} and not context.characters:
            issues.append(
                PublicationIssue(
                    "no_character",
                    "warning",
                    "Не найден персонаж",
                    "В посте нет хэштега, связанного с карточкой персонажа.",
                )
            )

        self._validate_character_metadata(context.characters, issues)

        if classification.post_type == "prompt":
            if not prompt.has_important:
                issues.append(
                    PublicationIssue(
                        "prompt_important",
                        "warning",
                        "Нет блока ВАЖНО",
                        "Структура промта неполная.",
                    )
                )
            if not prompt.has_strict:
                issues.append(
                    PublicationIssue(
                        "prompt_strict",
                        "warning",
                        "Нет блока СТРОГО",
                        "Структура промта неполная.",
                    )
                )
            if not prompt.has_technical:
                issues.append(
                    PublicationIssue(
                        "prompt_technical",
                        "warning",
                        "Нет технического блока",
                        "Не найдены камера, формат или параметры света.",
                    )
                )

        if _ADULT_RE.search(text) and draft.items and not draft.has_spoiler:
            issues.append(
                PublicationIssue(
                    "adult_spoiler",
                    "warning",
                    "Возможный 18+ без блюра",
                    "Проверьте пост и включите спойлер перед публикацией.",
                )
            )

        links = extract_links(text)
        raw_candidates = _URL_CANDIDATE_RE.findall(text)
        if raw_candidates and not links:
            issues.append(
                PublicationIssue(
                    "links",
                    "warning",
                    "Проверьте ссылки",
                    "Найдена ссылка, которую бот не смог разобрать.",
                )
            )

        if context.duplicate_draft is not None:
            issues.append(
                PublicationIssue(
                    "duplicate_draft",
                    "warning",
                    "Похожий черновик уже используется",
                    (
                        f"Черновик №{context.duplicate_draft.id} имеет статус "
                        f"{context.duplicate_draft.status}."
                    ),
                )
            )
        if context.duplicate_post is not None:
            detail = context.duplicate_post.message_url or (
                f"message_id={context.duplicate_post.message_id}"
            )
            issues.append(
                PublicationIssue(
                    "duplicate_post",
                    "warning",
                    "Такой текст уже публиковался",
                    detail,
                )
            )

        return await self._validation.save_result(
            draft,
            owner_id=owner_id,
            post_type=classification.post_type,
            issues=issues,
        )

    @staticmethod
    def _validate_telegram_limits(
        draft: PublicationDraft,
        text: str,
        issues: list[PublicationIssue],
    ) -> None:
        if not text and not draft.items:
            issues.append(
                PublicationIssue("empty", "error", "Пустой пост", "Нет текста и медиа.")
            )
        if not draft.items and len(text) > TEXT_LIMIT:
            issues.append(
                PublicationIssue(
                    "text_limit",
                    "error",
                    "Превышен лимит текста",
                    f"{len(text)} из {TEXT_LIMIT} символов.",
                )
            )
        if draft.items and len(text) > CAPTION_LIMIT:
            issues.append(
                PublicationIssue(
                    "caption_split",
                    "warning",
                    "Текст длиннее подписи к медиа",
                    f"{len(text)} символов. Бот отправит текст отдельно, затем медиа.",
                )
            )
        if len(draft.items) > MEDIA_GROUP_LIMIT:
            issues.append(
                PublicationIssue(
                    "media_count",
                    "error",
                    "Слишком большой альбом",
                    (
                        f"{len(draft.items)} файлов, допустимо не более "
                        f"{MEDIA_GROUP_LIMIT}."
                    ),
                )
            )
        if len(draft.items) > 1:
            types = {item.media_type for item in draft.items}
            if "animation" in types:
                issues.append(
                    PublicationIssue(
                        "album_animation",
                        "error",
                        "Анимация в альбоме",
                        "Telegram не принимает animation в sendMediaGroup.",
                    )
                )
            if "document" in types and types != {"document"}:
                issues.append(
                    PublicationIssue(
                        "album_mixed_document",
                        "error",
                        "Несовместимые типы альбома",
                        "Документы нельзя смешивать с фото или видео в одном альбоме.",
                    )
                )

    @staticmethod
    def _validate_character_metadata(characters, issues: list[PublicationIssue]) -> None:
        missing_category: list[str] = []
        missing_universe: list[str] = []
        missing_story: list[str] = []
        seen_characters: set[int] = set()

        for item in characters:
            if item.id in seen_characters:
                continue
            seen_characters.add(item.id)
            if not item.category:
                missing_category.append(item.name)
            if not item.universe:
                missing_universe.append(item.name)
            elif item.universe in _STORY_REQUIRED_UNIVERSES:
                if item.story_id is None and not item.has_multi_story:
                    missing_story.append(item.name)

        if missing_category:
            issues.append(
                PublicationIssue(
                    "category",
                    "error",
                    "Нет категории",
                    ", ".join(missing_category),
                )
            )
        if missing_universe:
            issues.append(
                PublicationIssue(
                    "universe",
                    "error",
                    "Нет вселенной",
                    ", ".join(missing_universe),
                )
            )
        if missing_story:
            issues.append(
                PublicationIssue(
                    "story",
                    "error",
                    "Нет истории",
                    ", ".join(missing_story),
                )
            )


__all__ = ("PublicationValidationService",)
