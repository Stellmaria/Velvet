from __future__ import annotations

import json
from typing import Any, Sequence

from velvet_bot.database import Database
from velvet_bot.domains.roleplay.models import (
    JsonObject,
    RoleplayCharacter,
    RoleplayCharacterDraft,
    RoleplayMemory,
    RoleplayMessage,
    RoleplaySession,
)
from velvet_bot.domains.roleplay.service import (
    normalize_roleplay_name,
    validate_character_draft,
    validate_memory,
    validate_message,
)


def _decode_object(value: Any) -> JsonObject:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        decoded = json.loads(value)
        return dict(decoded) if isinstance(decoded, dict) else {}
    return {}


def _decode_strings(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, list):
        return ()
    return tuple(str(item) for item in value if str(item).strip())


class RoleplayRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    @staticmethod
    def _character_from_row(row: Any) -> RoleplayCharacter:
        return RoleplayCharacter(
            id=int(row["id"]),
            owner_user_id=int(row["owner_user_id"]),
            name=str(row["name"]),
            normalized_name=str(row["normalized_name"]),
            adult_confirmed=bool(row["adult_confirmed"]),
            age_text=str(row["age_text"]) if row["age_text"] is not None else None,
            pronouns=str(row["pronouns"]) if row["pronouns"] is not None else None,
            appearance=_decode_object(row["appearance"]),
            personality=_decode_object(row["personality"]),
            speech=_decode_object(row["speech"]),
            biography=_decode_object(row["biography"]),
            behavior_rules=_decode_object(row["behavior_rules"]),
            canonical_facts=_decode_strings(row["canonical_facts"]),
            example_dialogue=_decode_strings(row["example_dialogue"]),
            system_notes=(
                str(row["system_notes"]) if row["system_notes"] is not None else None
            ),
            version=int(row["version"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _session_from_row(row: Any) -> RoleplaySession:
        return RoleplaySession(
            id=int(row["id"]),
            owner_user_id=int(row["owner_user_id"]),
            title=str(row["title"]),
            model=str(row["model"]),
            status=str(row["status"]),
            scenario=str(row["scenario"] or ""),
            world_lore=str(row["world_lore"] or ""),
            scene_state=_decode_object(row["scene_state"]),
            summary=str(row["summary"] or ""),
            generation_settings=_decode_object(row["generation_settings"]),
            next_sequence=int(row["next_sequence"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            last_message_at=row["last_message_at"],
        )

    @staticmethod
    def _message_from_row(row: Any) -> RoleplayMessage:
        return RoleplayMessage(
            id=int(row["id"]),
            session_id=int(row["session_id"]),
            sequence_no=int(row["sequence_no"]),
            role=str(row["role"]),
            speaker_key=(
                str(row["speaker_key"]) if row["speaker_key"] is not None else None
            ),
            content=str(row["content"]),
            token_count=(
                int(row["token_count"]) if row["token_count"] is not None else None
            ),
            created_at=row["created_at"],
        )

    @staticmethod
    def _memory_from_row(row: Any) -> RoleplayMemory:
        return RoleplayMemory(
            id=int(row["id"]),
            session_id=int(row["session_id"]),
            character_id=(
                int(row["character_id"]) if row["character_id"] is not None else None
            ),
            kind=str(row["kind"]),
            content=str(row["content"]),
            metadata=_decode_object(row["metadata"]),
            importance=int(row["importance"]),
            pinned=bool(row["pinned"]),
            active=bool(row["active"]),
            source_message_id=(
                int(row["source_message_id"])
                if row["source_message_id"] is not None
                else None
            ),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    async def create_character(
        self,
        *,
        owner_user_id: int,
        draft: RoleplayCharacterDraft,
    ) -> RoleplayCharacter:
        cleaned = validate_character_draft(draft)
        display_name, normalized_name = normalize_roleplay_name(cleaned.name)
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                """
                INSERT INTO rp_characters (
                    owner_user_id, name, normalized_name, adult_confirmed,
                    age_text, pronouns, appearance, personality, speech,
                    biography, behavior_rules, canonical_facts,
                    example_dialogue, system_notes
                )
                VALUES (
                    $1::BIGINT, $2::VARCHAR, $3::VARCHAR, $4::BOOLEAN,
                    $5::VARCHAR, $6::VARCHAR, $7::JSONB, $8::JSONB, $9::JSONB,
                    $10::JSONB, $11::JSONB, $12::JSONB, $13::JSONB, $14::TEXT
                )
                RETURNING *
                """,
                int(owner_user_id),
                display_name,
                normalized_name,
                cleaned.adult_confirmed,
                cleaned.age_text,
                cleaned.pronouns,
                json.dumps(cleaned.appearance, ensure_ascii=False),
                json.dumps(cleaned.personality, ensure_ascii=False),
                json.dumps(cleaned.speech, ensure_ascii=False),
                json.dumps(cleaned.biography, ensure_ascii=False),
                json.dumps(cleaned.behavior_rules, ensure_ascii=False),
                json.dumps(cleaned.canonical_facts, ensure_ascii=False),
                json.dumps(cleaned.example_dialogue, ensure_ascii=False),
                cleaned.system_notes,
            )
        return self._character_from_row(row)

    async def update_character(
        self,
        *,
        owner_user_id: int,
        character_id: int,
        draft: RoleplayCharacterDraft,
        expected_version: int | None = None,
    ) -> RoleplayCharacter:
        cleaned = validate_character_draft(draft)
        display_name, normalized_name = normalize_roleplay_name(cleaned.name)
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                """
                UPDATE rp_characters
                SET name = $3::VARCHAR,
                    normalized_name = $4::VARCHAR,
                    adult_confirmed = $5::BOOLEAN,
                    age_text = $6::VARCHAR,
                    pronouns = $7::VARCHAR,
                    appearance = $8::JSONB,
                    personality = $9::JSONB,
                    speech = $10::JSONB,
                    biography = $11::JSONB,
                    behavior_rules = $12::JSONB,
                    canonical_facts = $13::JSONB,
                    example_dialogue = $14::JSONB,
                    system_notes = $15::TEXT,
                    version = version + 1,
                    updated_at = NOW()
                WHERE id = $1::BIGINT
                  AND owner_user_id = $2::BIGINT
                  AND ($16::INTEGER IS NULL OR version = $16::INTEGER)
                RETURNING *
                """,
                int(character_id),
                int(owner_user_id),
                display_name,
                normalized_name,
                cleaned.adult_confirmed,
                cleaned.age_text,
                cleaned.pronouns,
                json.dumps(cleaned.appearance, ensure_ascii=False),
                json.dumps(cleaned.personality, ensure_ascii=False),
                json.dumps(cleaned.speech, ensure_ascii=False),
                json.dumps(cleaned.biography, ensure_ascii=False),
                json.dumps(cleaned.behavior_rules, ensure_ascii=False),
                json.dumps(cleaned.canonical_facts, ensure_ascii=False),
                json.dumps(cleaned.example_dialogue, ensure_ascii=False),
                cleaned.system_notes,
                expected_version,
            )
        if row is None:
            raise ValueError("RP-персонаж не найден или его карточка уже изменилась.")
        return self._character_from_row(row)

    async def get_character(
        self,
        *,
        owner_user_id: int,
        character_id: int,
    ) -> RoleplayCharacter | None:
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT *
                FROM rp_characters
                WHERE id = $1::BIGINT
                  AND owner_user_id = $2::BIGINT
                """,
                int(character_id),
                int(owner_user_id),
            )
        return self._character_from_row(row) if row is not None else None

    async def list_characters(
        self,
        *,
        owner_user_id: int,
        limit: int = 100,
    ) -> tuple[RoleplayCharacter, ...]:
        safe_limit = max(1, min(int(limit), 500))
        async with self._database.acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT *
                FROM rp_characters
                WHERE owner_user_id = $1::BIGINT
                ORDER BY normalized_name
                LIMIT $2::INTEGER
                """,
                int(owner_user_id),
                safe_limit,
            )
        return tuple(self._character_from_row(row) for row in rows)

    async def create_session(
        self,
        *,
        owner_user_id: int,
        title: str,
        model: str,
        scenario: str = "",
        world_lore: str = "",
        scene_state: JsonObject | None = None,
        generation_settings: JsonObject | None = None,
    ) -> RoleplaySession:
        cleaned_title = " ".join(title.split()).strip()[:240]
        cleaned_model = model.strip()[:240]
        if not cleaned_title:
            raise ValueError("Название RP-сессии не может быть пустым.")
        if not cleaned_model:
            raise ValueError("Модель RP-сессии не может быть пустой.")
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                """
                INSERT INTO rp_sessions (
                    owner_user_id, title, model, scenario, world_lore,
                    scene_state, generation_settings
                )
                VALUES (
                    $1::BIGINT, $2::VARCHAR, $3::VARCHAR, $4::TEXT, $5::TEXT,
                    $6::JSONB, $7::JSONB
                )
                RETURNING *
                """,
                int(owner_user_id),
                cleaned_title,
                cleaned_model,
                scenario.strip()[:40_000],
                world_lore.strip()[:80_000],
                json.dumps(scene_state or {}, ensure_ascii=False),
                json.dumps(generation_settings or {}, ensure_ascii=False),
            )
        return self._session_from_row(row)

    async def get_session(
        self,
        *,
        owner_user_id: int,
        session_id: int,
    ) -> RoleplaySession | None:
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT *
                FROM rp_sessions
                WHERE id = $1::BIGINT
                  AND owner_user_id = $2::BIGINT
                """,
                int(session_id),
                int(owner_user_id),
            )
        return self._session_from_row(row) if row is not None else None

    async def attach_character(
        self,
        *,
        owner_user_id: int,
        session_id: int,
        character_id: int,
        role_order: int,
        role_name: str | None = None,
        current_state: JsonObject | None = None,
        relationship_state: JsonObject | None = None,
    ) -> None:
        async with self._database.acquire() as connection:
            result = await connection.execute(
                """
                INSERT INTO rp_session_characters (
                    session_id, character_id, role_order, role_name,
                    current_state, relationship_state
                )
                SELECT
                    s.id, c.id, $4::INTEGER, $5::VARCHAR, $6::JSONB, $7::JSONB
                FROM rp_sessions s
                JOIN rp_characters c
                  ON c.id = $3::BIGINT
                 AND c.owner_user_id = $1::BIGINT
                WHERE s.id = $2::BIGINT
                  AND s.owner_user_id = $1::BIGINT
                ON CONFLICT (session_id, character_id)
                DO UPDATE SET
                    role_order = EXCLUDED.role_order,
                    role_name = EXCLUDED.role_name,
                    current_state = EXCLUDED.current_state,
                    relationship_state = EXCLUDED.relationship_state,
                    is_active = TRUE
                """,
                int(owner_user_id),
                int(session_id),
                int(character_id),
                max(1, int(role_order)),
                role_name.strip()[:120] if role_name else None,
                json.dumps(current_state or {}, ensure_ascii=False),
                json.dumps(relationship_state or {}, ensure_ascii=False),
            )
        if result.endswith("0"):
            raise ValueError("RP-сессия или RP-персонаж не найдены.")

    async def list_session_characters(
        self,
        *,
        owner_user_id: int,
        session_id: int,
    ) -> tuple[RoleplayCharacter, ...]:
        async with self._database.acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT c.*
                FROM rp_session_characters sc
                JOIN rp_sessions s ON s.id = sc.session_id
                JOIN rp_characters c ON c.id = sc.character_id
                WHERE sc.session_id = $1::BIGINT
                  AND s.owner_user_id = $2::BIGINT
                  AND c.owner_user_id = $2::BIGINT
                  AND sc.is_active = TRUE
                ORDER BY sc.role_order, c.id
                """,
                int(session_id),
                int(owner_user_id),
            )
        return tuple(self._character_from_row(row) for row in rows)

    async def append_message(
        self,
        *,
        owner_user_id: int,
        session_id: int,
        role: str,
        content: str,
        speaker_key: str | None = None,
        token_count: int | None = None,
    ) -> RoleplayMessage:
        cleaned_role, cleaned_content = validate_message(role, content)
        cleaned_speaker = speaker_key.strip()[:120] if speaker_key else None
        safe_tokens = max(0, int(token_count)) if token_count is not None else None
        async with self._database.acquire() as connection:
            async with connection.transaction():
                sequence = await connection.fetchval(
                    """
                    UPDATE rp_sessions
                    SET next_sequence = next_sequence + 1,
                        updated_at = NOW(),
                        last_message_at = NOW()
                    WHERE id = $1::BIGINT
                      AND owner_user_id = $2::BIGINT
                      AND status IN ('active', 'paused')
                    RETURNING next_sequence - 1
                    """,
                    int(session_id),
                    int(owner_user_id),
                )
                if sequence is None:
                    raise ValueError("Активная RP-сессия не найдена.")
                row = await connection.fetchrow(
                    """
                    INSERT INTO rp_messages (
                        session_id, sequence_no, role, speaker_key,
                        content, token_count
                    )
                    VALUES (
                        $1::BIGINT, $2::INTEGER, $3::VARCHAR, $4::VARCHAR,
                        $5::TEXT, $6::INTEGER
                    )
                    RETURNING *
                    """,
                    int(session_id),
                    int(sequence),
                    cleaned_role,
                    cleaned_speaker,
                    cleaned_content,
                    safe_tokens,
                )
        return self._message_from_row(row)

    async def list_recent_messages(
        self,
        *,
        owner_user_id: int,
        session_id: int,
        limit: int = 16,
    ) -> tuple[RoleplayMessage, ...]:
        safe_limit = max(1, min(int(limit), 200))
        async with self._database.acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT m.*
                FROM rp_messages m
                JOIN rp_sessions s ON s.id = m.session_id
                WHERE m.session_id = $1::BIGINT
                  AND s.owner_user_id = $2::BIGINT
                ORDER BY m.sequence_no DESC
                LIMIT $3::INTEGER
                """,
                int(session_id),
                int(owner_user_id),
                safe_limit,
            )
        return tuple(self._message_from_row(row) for row in reversed(rows))

    async def add_memory(
        self,
        *,
        owner_user_id: int,
        session_id: int,
        kind: str,
        content: str,
        character_id: int | None = None,
        metadata: JsonObject | None = None,
        importance: int = 50,
        pinned: bool = False,
        source_message_id: int | None = None,
    ) -> RoleplayMemory:
        cleaned_kind, cleaned_content, safe_importance = validate_memory(
            kind, content, importance
        )
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                """
                INSERT INTO rp_memories (
                    session_id, character_id, kind, content, metadata,
                    importance, pinned, source_message_id
                )
                SELECT
                    s.id, c.id, $4::VARCHAR, $5::TEXT, $6::JSONB,
                    $7::SMALLINT, $8::BOOLEAN, $9::BIGINT
                FROM rp_sessions s
                LEFT JOIN rp_characters c
                  ON c.id = $3::BIGINT
                 AND c.owner_user_id = $1::BIGINT
                WHERE s.id = $2::BIGINT
                  AND s.owner_user_id = $1::BIGINT
                  AND ($3::BIGINT IS NULL OR c.id IS NOT NULL)
                RETURNING rp_memories.*
                """,
                int(owner_user_id),
                int(session_id),
                int(character_id) if character_id is not None else None,
                cleaned_kind,
                cleaned_content,
                json.dumps(metadata or {}, ensure_ascii=False),
                safe_importance,
                bool(pinned),
                int(source_message_id) if source_message_id is not None else None,
            )
        if row is None:
            raise ValueError("RP-сессия или RP-персонаж для памяти не найдены.")
        return self._memory_from_row(row)

    async def list_memories(
        self,
        *,
        owner_user_id: int,
        session_id: int,
        kinds: Sequence[str] | None = None,
        limit: int = 200,
    ) -> tuple[RoleplayMemory, ...]:
        cleaned_kinds = [kind.strip().casefold() for kind in kinds or () if kind.strip()]
        safe_limit = max(1, min(int(limit), 1000))
        async with self._database.acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT m.*
                FROM rp_memories m
                JOIN rp_sessions s ON s.id = m.session_id
                WHERE m.session_id = $1::BIGINT
                  AND s.owner_user_id = $2::BIGINT
                  AND m.active = TRUE
                  AND (
                      COALESCE(cardinality($3::TEXT[]), 0) = 0
                      OR m.kind = ANY($3::TEXT[])
                  )
                ORDER BY m.pinned DESC, m.importance DESC, m.updated_at DESC
                LIMIT $4::INTEGER
                """,
                int(session_id),
                int(owner_user_id),
                cleaned_kinds,
                safe_limit,
            )
        return tuple(self._memory_from_row(row) for row in rows)

    async def update_session_state(
        self,
        *,
        owner_user_id: int,
        session_id: int,
        summary: str,
        scene_state: JsonObject,
    ) -> RoleplaySession:
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                """
                UPDATE rp_sessions
                SET summary = $3::TEXT,
                    scene_state = $4::JSONB,
                    updated_at = NOW()
                WHERE id = $1::BIGINT
                  AND owner_user_id = $2::BIGINT
                RETURNING *
                """,
                int(session_id),
                int(owner_user_id),
                summary.strip()[:40_000],
                json.dumps(scene_state, ensure_ascii=False),
            )
        if row is None:
            raise ValueError("RP-сессия не найдена.")
        return self._session_from_row(row)


__all__ = ("RoleplayRepository",)
