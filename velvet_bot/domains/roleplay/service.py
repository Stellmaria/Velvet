from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from velvet_bot.domains.roleplay.client import GeneratedRoleplayText, RoleplayClient, RoleplayClientError
from velvet_bot.domains.roleplay.models import RoleplayMessage, RoleplayReply, RoleplaySession
from velvet_bot.domains.roleplay.storage import RoleplayRepository

_DEFAULT_INSTRUCTIONS = """
Ты ведёшь литературную ролевую игру на русском языке.

Правила работы:
1. Соблюдай заданный пользователем канон, характеры, отношения, факты мира и хронологию.
2. Различай голоса персонажей, не смешивай их мотивы и манеру речи.
3. Не управляй персонажем пользователя без прямой просьбы. Описывай мир, NPC и последствия действий.
4. Продолжай сцену с текущего момента, не пересказывай без необходимости уже известные события.
5. Пиши цельной художественной прозой, сохраняй выбранное лицо повествования, темп и атмосферу.
6. Не выходи из роли и не обсуждай техническое устройство модели, если пользователь прямо этого не просит.
7. Все участники романтических или интимных сюжетов должны быть совершеннолетними.
8. Соблюдай правила подключённого провайдера модели.
""".strip()

_COMPACTION_INSTRUCTIONS = """
Ты обновляешь долговременную память ролевой игры. Верни только сжатое фактическое резюме на русском языке.
Сохраняй: канон, раскрытые секреты, обещания, конфликты, изменения отношений, важные предметы,
травмы, местоположение, незавершённые действия и причинно-следственные связи.
Не добавляй новых событий, оценок и художественных украшений. Не повторяй малозначимые реплики.
""".strip()

_MAX_CANON_LENGTH = 30_000
_MAX_USER_MESSAGE_LENGTH = 20_000


class RoleplayUnavailableError(RuntimeError):
    pass


class RoleplayInactiveError(RuntimeError):
    pass


class RoleplayService:
    def __init__(self, *, repository: RoleplayRepository, client: RoleplayClient | None,
                 provider_label: str, model_label: str, max_history_messages: int = 30,
                 compaction_margin: int = 16) -> None:
        self._repository = repository
        self._client = client
        self.provider_label = provider_label
        self.model_label = model_label
        self.max_history_messages = max(6, min(int(max_history_messages), 120))
        self.compaction_margin = max(4, min(int(compaction_margin), 80))
        self._session_locks: dict[tuple[int, int], asyncio.Lock] = {}

    @property
    def configured(self) -> bool:
        return self._client is not None

    async def get_session(self, *, chat_id: int, user_id: int) -> RoleplaySession | None:
        return await self._repository.get_session(chat_id=chat_id, user_id=user_id)

    async def is_active(self, *, chat_id: int, user_id: int) -> bool:
        if not self.configured:
            return False
        session = await self.get_session(chat_id=chat_id, user_id=user_id)
        return bool(session and session.enabled)

    async def start(self, *, chat_id: int, user_id: int) -> RoleplaySession:
        self._require_client()
        return await self._repository.set_enabled(chat_id=chat_id, user_id=user_id, enabled=True)

    async def stop(self, *, chat_id: int, user_id: int) -> RoleplaySession:
        return await self._repository.set_enabled(chat_id=chat_id, user_id=user_id, enabled=False)

    async def set_canon(self, *, chat_id: int, user_id: int, canon: str) -> RoleplaySession:
        cleaned = canon.strip()
        if len(cleaned) > _MAX_CANON_LENGTH:
            raise ValueError(f"Канон не должен превышать {_MAX_CANON_LENGTH} символов.")
        return await self._repository.set_system_prompt(
            chat_id=chat_id, user_id=user_id, system_prompt=cleaned)

    async def reset(self, *, chat_id: int, user_id: int) -> None:
        await self._repository.clear_history(chat_id=chat_id, user_id=user_id)

    async def reply(self, *, chat_id: int, user_id: int, text: str,
                    activate: bool = False) -> RoleplayReply:
        client = self._require_client()
        cleaned = text.strip()
        if not cleaned:
            raise ValueError("Сообщение для РЛ не может быть пустым.")
        if len(cleaned) > _MAX_USER_MESSAGE_LENGTH:
            raise ValueError(f"Сообщение не должно превышать {_MAX_USER_MESSAGE_LENGTH} символов.")
        key = (int(chat_id), int(user_id))
        lock = self._session_locks.setdefault(key, asyncio.Lock())
        async with lock:
            session = await self._repository.get_session(chat_id=chat_id, user_id=user_id)
            if session is None:
                session = await self._repository.ensure_session(chat_id=chat_id, user_id=user_id)
            if activate and not session.enabled:
                session = await self._repository.set_enabled(
                    chat_id=chat_id, user_id=user_id, enabled=True)
            if not session.enabled:
                raise RoleplayInactiveError(
                    "РЛ-режим выключен. Используйте /rp_on или /rp <текст>.")
            session = await self._compact_history_if_needed(session=session, client=client)
            history = await self._repository.get_recent_messages(
                chat_id=chat_id, user_id=user_id, limit=self.max_history_messages)
            current_message = RoleplayMessage(
                id=0, chat_id=int(chat_id), user_id=int(user_id), role="user",
                content=cleaned, created_at=datetime.now(timezone.utc))
            generated = await client.generate(
                instructions=self._build_instructions(session),
                messages=(*history, current_message))
            await self._repository.append_exchange(
                chat_id=chat_id, user_id=user_id, user_text=cleaned,
                assistant_text=generated.text)
            return RoleplayReply(text=generated.text, provider=generated.provider,
                                 model=generated.model)

    async def _compact_history_if_needed(self, *, session: RoleplaySession,
                                         client: RoleplayClient) -> RoleplaySession:
        count = await self._repository.count_messages(
            chat_id=session.chat_id, user_id=session.user_id)
        if count <= self.max_history_messages + self.compaction_margin:
            return session
        batch = await self._repository.get_compaction_batch(
            chat_id=session.chat_id, user_id=session.user_id,
            keep_recent=self.max_history_messages)
        if not batch:
            return session
        transcript = "\n".join(
            f"{message.role.upper()}: {message.content}" for message in batch)
        previous = session.summary.strip() or "Долговременная память пока пуста."
        compaction_input = RoleplayMessage(
            id=0, chat_id=session.chat_id, user_id=session.user_id, role="user",
            content=(f"Предыдущее резюме:\n{previous}\n\n"
                     f"Новые старые реплики для объединения:\n{transcript}"),
            created_at=datetime.now(timezone.utc))
        try:
            generated: GeneratedRoleplayText = await client.generate(
                instructions=_COMPACTION_INSTRUCTIONS, messages=(compaction_input,))
        except RoleplayClientError:
            return session
        await self._repository.apply_compaction(
            chat_id=session.chat_id, user_id=session.user_id,
            message_ids=tuple(message.id for message in batch),
            summary=generated.text.strip())
        refreshed = await self._repository.get_session(
            chat_id=session.chat_id, user_id=session.user_id)
        return refreshed or session

    @staticmethod
    def _build_instructions(session: RoleplaySession) -> str:
        sections = [_DEFAULT_INSTRUCTIONS]
        if session.system_prompt.strip():
            sections.append("КАНОН И НАСТРОЙКИ ПОЛЬЗОВАТЕЛЯ:\n" + session.system_prompt.strip())
        if session.summary.strip():
            sections.append("ДОЛГОВРЕМЕННАЯ ПАМЯТЬ СЕССИИ:\n" + session.summary.strip())
        return "\n\n".join(sections)

    def _require_client(self) -> RoleplayClient:
        if self._client is None:
            raise RoleplayUnavailableError(
                "Текстовая модель не настроена. Включите AI_TEXT_ENABLED и "
                "задайте провайдера, модель и API-ключ.")
        return self._client


__all__ = ("RoleplayInactiveError", "RoleplayService", "RoleplayUnavailableError")
