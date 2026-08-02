from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    source = target.read_text(encoding="utf-8")
    if old not in source:
        raise SystemExit(f"Expected text not found in {path}: {old[:120]!r}")
    target.write_text(source.replace(old, new, 1), encoding="utf-8")


def patch_files() -> None:
    path = ROOT / "velvet_bot/domains/telegram_storage/files.py"
    source = path.read_text(encoding="utf-8")
    import_anchor = '''from velvet_bot.domains.telegram_storage.deletion import (
    DeletionPolicy,
    DeletionResult,
    delete_paths,
    temporary_deletion_policy,
)
'''
    import_replacement = import_anchor + '''from velvet_bot.domains.telegram_storage.encryption import (
    StorageEncryptionUnavailable,
    decrypt_file,
    encrypt_file,
    sha256_file,
)
'''
    if import_anchor not in source:
        raise SystemExit("files.py import anchor not found")
    source = source.replace(import_anchor, import_replacement, 1)
    source = source.replace("import hashlib\n", "", 1)
    source = source.replace("from functools import lru_cache\n", "", 1)
    source = source.replace(
        '''_MAGIC = b"VELVET-AESGCM1\\n"
_SALT_BYTES = 16
_NONCE_BYTES = 12
_TAG_BYTES = 16
_CHUNK_BYTES = 1024 * 1024
''',
        "_CHUNK_BYTES = 1024 * 1024\n",
        1,
    )
    blocks = (
        (r"\nclass StorageEncryptionUnavailable\(RuntimeError\):\n    pass\n", "\n"),
        (
            r"\n@lru_cache\(maxsize=1\)\ndef _crypto_components\(\):.*?(?=\n\ndef sha256_file)",
            "",
        ),
        (
            r"\ndef sha256_file\(path: str \| Path\) -> str:.*?(?=\n\ndef safe_token)",
            "",
        ),
        (
            r"\ndef _derive_key\(secret: str, salt: bytes\) -> bytes:.*?(?=\n\ndef split_file)",
            "",
        ),
    )
    for pattern, value in blocks:
        source, count = re.subn(pattern, value, source, count=1, flags=re.DOTALL)
        if count != 1:
            raise SystemExit(f"files.py crypto block not found: {pattern}")
    path.write_text(source, encoding="utf-8")


def patch_models() -> None:
    replace_once(
        "velvet_bot/domains/telegram_storage/models.py",
        '''from velvet_bot.domains.telegram_storage.deletion import (
    DeletionPolicy,
    build_storage_deletion_policy,
)
''',
        '''from velvet_bot.domains.telegram_storage.deletion import (
    DeletionPolicy,
    build_storage_deletion_policy,
)
from velvet_bot.domains.telegram_storage.encryption import (
    StorageEncryptionKeyring,
    keyring_from_env,
)
''',
    )
    replace_once(
        "velvet_bot/domains/telegram_storage/models.py",
        '''    max_part_bytes: int
    encryption_secret: str = field(repr=False)

    @classmethod
''',
        '''    max_part_bytes: int
    encryption_keyring: StorageEncryptionKeyring = field(repr=False)

    @property
    def encryption_secret(self) -> str:
        return self.encryption_keyring.active_secret

    @property
    def encryption_key_id(self) -> str:
        return self.encryption_keyring.active_key_id

    @classmethod
''',
    )
    replace_once(
        "velvet_bot/domains/telegram_storage/models.py",
        '''        secret = (
            os.getenv("STORAGE_ENCRYPTION_SECRET", "").strip()
            or os.getenv("SUPERVISOR_TOKEN", "").strip()
            or os.getenv("BOT_TOKEN", "").strip()
        )
        if len(secret) < 24:
            raise ValueError(
                "Для шифрования backup задайте STORAGE_ENCRYPTION_SECRET минимум из 24 символов."
            )
''',
        '''        encryption_keyring = keyring_from_env()
''',
    )
    replace_once(
        "velvet_bot/domains/telegram_storage/models.py",
        "            encryption_secret=secret,\n",
        "            encryption_keyring=encryption_keyring,\n",
    )


def patch_service() -> None:
    path = "velvet_bot/domains/telegram_storage/service.py"
    replace_once(
        path,
        '''                        "validation": item.validation,
                        "packed_at": datetime.now(UTC).isoformat(),
''',
        '''                        "validation": item.validation,
                        "encryption_key_id": self.settings.encryption_key_id,
                        "encryption_version": "AES-256-GCM+scrypt:v2",
                        "packed_at": datetime.now(UTC).isoformat(),
''',
    )
    replace_once(
        path,
        '''                    self.settings.encryption_secret,
                )
                await asyncio.to_thread(
                    decrypt_file,
                    encrypted_path,
                    verify_path,
                    self.settings.encryption_secret,
''',
        '''                    self.settings.encryption_keyring,
                )
                await asyncio.to_thread(
                    decrypt_file,
                    encrypted_path,
                    verify_path,
                    self.settings.encryption_keyring,
''',
    )
    replace_once(
        path,
        '''                        "source_sha256": source_digest,
                        "zip_sha256": zip_digest,
''',
        '''                        "source_sha256": source_digest,
                        "zip_sha256": zip_digest,
                        "encryption_key_id": self.settings.encryption_key_id,
''',
    )
    replace_once(
        path,
        '                    encryption_version="AES-256-GCM+scrypt:v1",\n',
        '                    encryption_version="AES-256-GCM+scrypt:v2",\n',
    )


def patch_preflight() -> None:
    replace_once(
        "scripts/server_preflight.py",
        "import ipaddress\n",
        "import ipaddress\nimport json\n",
    )
    replace_once(
        "scripts/server_preflight.py",
        '''    "STORAGE_ENCRYPTION_SECRET",
    "SUPERVISOR_TOKEN",
''',
        '''    "STORAGE_ENCRYPTION_SECRET",
    "STORAGE_ENCRYPTION_KEYRING",
    "SUPERVISOR_TOKEN",
''',
    )
    replace_once(
        "scripts/server_preflight.py",
        '''        "STORAGE_ENCRYPTION_SECRET",
        "SUPERVISOR_TOKEN",
''',
        '''        "STORAGE_ENCRYPTION_SECRET",
        "STORAGE_ENCRYPTION_ACTIVE_KEY_ID",
        "SUPERVISOR_TOKEN",
''',
    )
    anchor = '''def _validate_storage(values: dict[str, str], report: ValidationReport) -> None:
    storage_chat = values.get("TELEGRAM_STORAGE_CHAT_ID", "").strip()
'''
    replacement = '''def _validate_storage(values: dict[str, str], report: ValidationReport) -> None:
    active_key_id = values.get("STORAGE_ENCRYPTION_ACTIVE_KEY_ID", "").strip()
    active_secret = values.get("STORAGE_ENCRYPTION_SECRET", "").strip()
    legacy_key_id = values.get("STORAGE_ENCRYPTION_LEGACY_KEY_ID", "").strip()
    key_id_pattern = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
    if active_key_id and not key_id_pattern.fullmatch(active_key_id):
        report.error(
            "STORAGE_ENCRYPTION_ACTIVE_KEY_ID должен содержать 1–64 безопасных символа."
        )

    configured_keys: dict[str, str] = {}
    raw_keyring = values.get("STORAGE_ENCRYPTION_KEYRING", "").strip()
    if raw_keyring:
        try:
            payload = json.loads(raw_keyring)
        except json.JSONDecodeError:
            report.error("STORAGE_ENCRYPTION_KEYRING должен быть JSON-объектом key_id:secret.")
            payload = {}
        if not isinstance(payload, dict):
            report.error("STORAGE_ENCRYPTION_KEYRING должен быть JSON-объектом key_id:secret.")
        else:
            for key_id, secret in payload.items():
                if not isinstance(key_id, str) or not isinstance(secret, str):
                    report.error(
                        "STORAGE_ENCRYPTION_KEYRING принимает только строковые key ID и secrets."
                    )
                    continue
                if not key_id_pattern.fullmatch(key_id):
                    report.error(f"Некорректный backup key ID: {key_id!r}.")
                if len(secret) < 24:
                    report.error(
                        f"Historical backup key {key_id!r} должен содержать не менее 24 символов."
                    )
                configured_keys[key_id] = secret

    if active_key_id:
        configured_keys[active_key_id] = active_secret
    if legacy_key_id and legacy_key_id not in configured_keys:
        report.error(
            "STORAGE_ENCRYPTION_LEGACY_KEY_ID должен присутствовать в active/historical keyring."
        )
    auth_secrets = {
        values.get("BOT_TOKEN", "").strip(),
        values.get("SUPERVISOR_TOKEN", "").strip(),
    } - {""}
    reused = sorted(
        key_id for key_id, secret in configured_keys.items() if secret in auth_secrets
    )
    if reused:
        report.error(
            "Backup encryption keys не должны совпадать с BOT_TOKEN или SUPERVISOR_TOKEN: "
            + ", ".join(reused)
        )
    if active_key_id and active_secret and not reused:
        report.passed(
            "Backup keyring настроен отдельно от authentication tokens; "
            f"active={active_key_id}, keys={len(configured_keys)}."
        )

    storage_chat = values.get("TELEGRAM_STORAGE_CHAT_ID", "").strip()
'''
    replace_once("scripts/server_preflight.py", anchor, replacement)


def patch_storage_center() -> None:
    path = "velvet_bot/presentation/telegram/storage_center.py"
    replace_once(
        path,
        '''        f"Чат: <code>{settings.chat_id}</code>",
        (
''',
        '''        f"Чат: <code>{settings.chat_id}</code>",
        (
            "Backup keyring: "
            f"active=<code>{escape(settings.encryption_key_id)}</code>, "
            f"доступно={len(settings.encryption_keyring.key_ids)}, "
            f"legacy-v1={'да' if settings.encryption_keyring.legacy_key_id else 'нет'}"
        ),
        (
''',
    )
    replace_once(
        path,
        '''            "<code>/storage_download ID</code> — получить файл или его части",
''',
        '''            "<code>/storage_download ID</code> — получить файл или его части",
            "<code>/storage_keys</code> — проверить доступность backup keys",
''',
    )
    insertion_anchor = '''async def handle_storage_startup(
    bot: Bot,
    database: Database,
) -> None:
'''
    handler = '''async def handle_storage_keys(
    message: Message,
    database: Database,
) -> None:
    settings = TelegramStorageSettings.from_env()
    async with database.acquire() as connection:
        rows = await connection.fetch(
            """
            SELECT id, encryption_version,
                   manifest ->> 'encryption_key_id' AS encryption_key_id
            FROM telegram_storage_objects
            WHERE storage_kind = 'backups'
              AND encrypted = TRUE
            ORDER BY id DESC
            LIMIT 500
            """
        )
    missing: list[str] = []
    legacy = 0
    for row in rows:
        key_id = row["encryption_key_id"]
        if key_id is None:
            legacy += 1
        label = str(key_id) if key_id is not None else "<legacy-v1>"
        selected = str(key_id) if key_id is not None else None
        if not settings.encryption_keyring.has_key(selected):
            missing.append(f"#{int(row['id'])}:{label}")

    lines = [
        "<b>Backup key availability</b>",
        "",
        f"Active: <code>{escape(settings.encryption_key_id)}</code>",
        "Доступные ID: "
        + ", ".join(
            f"<code>{escape(key_id)}</code>"
            for key_id in settings.encryption_keyring.key_ids
        ),
        f"Encrypted backup objects: <b>{len(rows)}</b>",
        f"Legacy v1 without header key ID: <b>{legacy}</b>",
    ]
    if missing:
        lines.extend(
            (
                "",
                f"Недоступно ключей для объектов: <b>{len(missing)}</b>",
                "• " + "\\n• ".join(escape(item) for item in missing[:20]),
            )
        )
    else:
        lines.extend(("", "Все известные backup имеют доступный decrypt key."))
    await message.answer("\\n".join(lines))


''' + insertion_anchor
    replace_once(path, insertion_anchor, handler)
    replace_once(
        path,
        '''    router.message.register(handle_storage_download, Command("storage_download"))
    router.startup.register(handle_storage_startup)
''',
        '''    router.message.register(handle_storage_download, Command("storage_download"))
    router.message.register(handle_storage_keys, Command("storage_keys"))
    router.startup.register(handle_storage_startup)
''',
    )


def patch_env_examples() -> None:
    section = '''
# Backup encryption key lifecycle.
# Active secret must be independent from BOT_TOKEN and SUPERVISOR_TOKEN.
STORAGE_ENCRYPTION_ACTIVE_KEY_ID=primary-2026-08
STORAGE_ENCRYPTION_SECRET=replace_with_random_backup_secret_at_least_32_chars
# JSON object with read-only historical keys retained for restore.
STORAGE_ENCRYPTION_KEYRING={}
# Set only during migration of VELVET-AESGCM1 backups without header key ID.
STORAGE_ENCRYPTION_LEGACY_KEY_ID=
'''
    for name in (".env.example", ".env.server.example"):
        path = ROOT / name
        source = path.read_text(encoding="utf-8")
        if "STORAGE_ENCRYPTION_ACTIVE_KEY_ID=" not in source:
            path.write_text(source.rstrip() + "\n" + section, encoding="utf-8")


def patch_existing_tests() -> None:
    replace_once(
        "tests/test_telegram_storage_center.py",
        '        self.assertIn("AES-256-GCM+scrypt:v1", service)\n',
        '        self.assertIn("AES-256-GCM+scrypt:v2", service)\n',
    )
    replace_once(
        "tests/test_server_preflight.py",
        '        "STORAGE_ENCRYPTION_SECRET": "storage_secret_12345678901234567890",\n',
        '        "STORAGE_ENCRYPTION_ACTIVE_KEY_ID": "backup-active",\n'
        '        "STORAGE_ENCRYPTION_SECRET": "storage_secret_12345678901234567890",\n',
    )


def main() -> None:
    patch_files()
    patch_models()
    patch_service()
    patch_preflight()
    patch_storage_center()
    patch_env_examples()
    patch_existing_tests()
    Path(__file__).unlink()


if __name__ == "__main__":
    main()
