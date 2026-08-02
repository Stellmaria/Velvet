from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.server_preflight import (
    ValidationReport,
    _validate_required_base,
    _validate_storage,
)
from velvet_bot.domains.telegram_storage.encryption import (
    StorageEncryptionKeyring,
    UnknownStorageEncryptionKey,
    decrypt_file,
    encrypt_file,
    encrypt_legacy_v1_file,
    inspect_encrypted_file,
    reencrypt_file,
    sha256_file,
)
from velvet_bot.domains.telegram_storage.models import TelegramStorageSettings

_CRYPTOGRAPHY_AVAILABLE = importlib.util.find_spec("cryptography") is not None


def _settings_env(secret: str, *, bot_token: str, supervisor_token: str) -> dict[str, str]:
    return {
        "SUPERVISOR_PROJECT_DIR": ".",
        "STORAGE_DELETE_AFTER_UPLOAD": "false",
        "STORAGE_ENCRYPTION_ACTIVE_KEY_ID": "backup-2026-08",
        "STORAGE_ENCRYPTION_SECRET": secret,
        "STORAGE_ENCRYPTION_KEYRING": "{}",
        "BOT_TOKEN": bot_token,
        "SUPERVISOR_TOKEN": supervisor_token,
    }


class BackupKeyringConfigurationTests(unittest.TestCase):
    def test_auth_tokens_are_never_used_as_backup_fallback(self) -> None:
        with patch.dict(
            os.environ,
            {
                "BOT_TOKEN": "123456:" + "b" * 32,
                "SUPERVISOR_TOKEN": "s" * 32,
                "STORAGE_DELETE_AFTER_UPLOAD": "false",
            },
            clear=True,
        ):
            with self.assertRaisesRegex(ValueError, "отдельный STORAGE_ENCRYPTION_SECRET"):
                TelegramStorageSettings.from_env()

    def test_keyring_status_and_repr_never_expose_key_material(self) -> None:
        active_secret = "active-" + "a" * 32
        old_secret = "old-" + "b" * 32
        keyring = StorageEncryptionKeyring(
            active_key_id="backup-new",
            keys={"backup-new": active_secret, "backup-old": old_secret},
            legacy_key_id="backup-old",
        )
        public = repr(keyring) + repr(keyring.public_status())
        self.assertNotIn(active_secret, public)
        self.assertNotIn(old_secret, public)
        self.assertIn("backup-new", public)
        self.assertIn("backup-old", public)

    def test_server_preflight_requires_key_id_and_rejects_auth_secret_reuse(self) -> None:
        base = {
            "BOT_TOKEN": "123456:" + "x" * 32,
            "DATABASE_URL": "postgresql://velvet:password@postgres:5432/velvet",
            "POSTGRES_DB": "velvet",
            "POSTGRES_USER": "velvet",
            "POSTGRES_PASSWORD": "p" * 32,
            "ALLOWED_USER_IDS": "1",
            "STORAGE_ENCRYPTION_SECRET": "backup-" + "z" * 32,
            "SUPERVISOR_TOKEN": "s" * 32,
            "VELVET_DATA_DIR": "/srv/velvet/data",
        }
        report = ValidationReport()
        _validate_required_base(base, report)
        self.assertTrue(
            any("STORAGE_ENCRYPTION_ACTIVE_KEY_ID" in error for error in report.errors)
        )

        reused = dict(base)
        reused["STORAGE_ENCRYPTION_ACTIVE_KEY_ID"] = "backup-active"
        reused["STORAGE_ENCRYPTION_SECRET"] = reused["SUPERVISOR_TOKEN"]
        reused_report = ValidationReport()
        _validate_storage(reused, reused_report)
        self.assertTrue(any("не должны совпадать" in error for error in reused_report.errors))


@unittest.skipUnless(_CRYPTOGRAPHY_AVAILABLE, "cryptography is required")
class BackupKeyringCryptoTests(unittest.TestCase):
    def test_new_backup_contains_authenticated_key_id_without_secret(self) -> None:
        secret = "active-" + "a" * 32
        ring = StorageEncryptionKeyring(
            active_key_id="backup-2026-08",
            keys={"backup-2026-08": secret},
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "backup.dump"
            encrypted = root / "backup.velvet.enc"
            restored = root / "restored.dump"
            source.write_bytes(b"database-backup" * 100)
            encrypt_file(source, encrypted, ring)

            header = inspect_encrypted_file(encrypted)
            self.assertEqual(2, header.version)
            self.assertEqual("backup-2026-08", header.key_id)
            self.assertNotIn(secret.encode(), encrypted.read_bytes())

            decrypt_file(encrypted, restored, ring)
            self.assertEqual(sha256_file(source), sha256_file(restored))

    def test_bot_and_supervisor_rotation_do_not_change_restore_key(self) -> None:
        secret = "backup-" + "k" * 32
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "backup.dump"
            encrypted = root / "backup.velvet.enc"
            restored = root / "restored.dump"
            source.write_bytes(os.urandom(1024))

            with patch.dict(
                os.environ,
                _settings_env(
                    secret,
                    bot_token="123456:" + "a" * 32,
                    supervisor_token="b" * 32,
                ),
                clear=True,
            ):
                first = TelegramStorageSettings.from_env()
                encrypt_file(source, encrypted, first.encryption_keyring)

            with patch.dict(
                os.environ,
                _settings_env(
                    secret,
                    bot_token="654321:" + "c" * 32,
                    supervisor_token="d" * 32,
                ),
                clear=True,
            ):
                rotated = TelegramStorageSettings.from_env()
                decrypt_file(encrypted, restored, rotated.encryption_keyring)

            self.assertEqual(source.read_bytes(), restored.read_bytes())

    def test_historical_key_decrypts_old_object_and_unknown_id_is_terminal(self) -> None:
        old_secret = "old-" + "o" * 32
        new_secret = "new-" + "n" * 32
        old_ring = StorageEncryptionKeyring(
            active_key_id="backup-old",
            keys={"backup-old": old_secret},
        )
        migration_ring = StorageEncryptionKeyring(
            active_key_id="backup-new",
            keys={"backup-new": new_secret, "backup-old": old_secret},
        )
        new_only_ring = StorageEncryptionKeyring(
            active_key_id="backup-new",
            keys={"backup-new": new_secret},
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "backup.dump"
            encrypted = root / "old.velvet.enc"
            restored = root / "restored.dump"
            source.write_bytes(b"old-generation")
            encrypt_file(source, encrypted, old_ring)
            decrypt_file(encrypted, restored, migration_ring)
            self.assertEqual(source.read_bytes(), restored.read_bytes())

            with self.assertRaises(UnknownStorageEncryptionKey) as caught:
                decrypt_file(encrypted, root / "missing.dump", new_only_ring)
            self.assertEqual("backup-old", caught.exception.key_id)
            self.assertNotIn(old_secret, str(caught.exception))

    def test_legacy_v1_requires_declared_legacy_key(self) -> None:
        old_secret = "legacy-" + "l" * 32
        ring = StorageEncryptionKeyring(
            active_key_id="backup-new",
            keys={"backup-new": "new-" + "n" * 32, "legacy-token": old_secret},
            legacy_key_id="legacy-token",
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "backup.dump"
            encrypted = root / "legacy.velvet.enc"
            restored = root / "restored.dump"
            source.write_bytes(b"legacy-backup")
            encrypt_legacy_v1_file(source, encrypted, old_secret)
            self.assertEqual(1, inspect_encrypted_file(encrypted).version)
            decrypt_file(encrypted, restored, ring)
            self.assertEqual(source.read_bytes(), restored.read_bytes())

    def test_corrupted_tag_never_replaces_existing_restore_destination(self) -> None:
        ring = StorageEncryptionKeyring(
            active_key_id="backup-active",
            keys={"backup-active": "secret-" + "s" * 32},
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "backup.dump"
            encrypted = root / "backup.velvet.enc"
            restored = root / "restored.dump"
            source.write_bytes(os.urandom(2048))
            restored.write_bytes(b"known-good-existing-file")
            encrypt_file(source, encrypted, ring)
            payload = bytearray(encrypted.read_bytes())
            payload[-1] ^= 0x01
            encrypted.write_bytes(payload)

            with self.assertRaises(Exception):
                decrypt_file(encrypted, restored, ring)
            self.assertEqual(b"known-good-existing-file", restored.read_bytes())
            self.assertFalse(any(root.glob(".*.partial")))

    def test_reencrypt_verifies_new_generation_before_returning(self) -> None:
        old_secret = "old-" + "o" * 32
        ring = StorageEncryptionKeyring(
            active_key_id="backup-new",
            keys={"backup-new": "new-" + "n" * 32, "backup-old": old_secret},
        )
        old_ring = StorageEncryptionKeyring(
            active_key_id="backup-old",
            keys={"backup-old": old_secret},
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "backup.dump"
            old_encrypted = root / "old.velvet.enc"
            new_encrypted = root / "new.velvet.enc"
            restored = root / "restored.dump"
            source.write_bytes(os.urandom(4096))
            encrypt_file(source, old_encrypted, old_ring)

            reencrypt_file(old_encrypted, new_encrypted, ring)
            self.assertTrue(old_encrypted.exists())
            self.assertEqual("backup-new", inspect_encrypted_file(new_encrypted).key_id)
            decrypt_file(new_encrypted, restored, ring)
            self.assertEqual(source.read_bytes(), restored.read_bytes())


if __name__ == "__main__":
    unittest.main()
