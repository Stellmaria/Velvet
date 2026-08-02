from __future__ import annotations

import re
from pathlib import Path

path = Path(__file__).with_name("apply_backup_keyring_508.py")
source = path.read_text(encoding="utf-8")

replacement = '''def patch_files() -> None:
    path = ROOT / "velvet_bot/domains/telegram_storage/files.py"
    source = path.read_text(encoding="utf-8")
    import_anchor = ''' + '"""' + '''from velvet_bot.domains.telegram_storage.deletion import (
    DeletionPolicy,
    DeletionResult,
    delete_paths,
    temporary_deletion_policy,
)
''' + '"""' + '''
    import_replacement = import_anchor + ''' + '"""' + '''from velvet_bot.domains.telegram_storage.encryption import (
    StorageEncryptionUnavailable,
    decrypt_file,
    encrypt_file,
    sha256_file,
)
''' + '"""' + '''
    if import_anchor not in source:
        raise SystemExit("files.py import anchor not found")
    source = source.replace(import_anchor, import_replacement, 1)
    source = source.replace("import hashlib\\n", "", 1)
    source = source.replace("from functools import lru_cache\\n", "", 1)
    source = source.replace(
        ''' + '"""' + '''_MAGIC = b"VELVET-AESGCM1\\n"
_SALT_BYTES = 16
_NONCE_BYTES = 12
_TAG_BYTES = 16
_CHUNK_BYTES = 1024 * 1024
''' + '"""' + ''',
        "_CHUNK_BYTES = 1024 * 1024\\n",
        1,
    )
    blocks = (
        (r"\\nclass StorageEncryptionUnavailable\\(RuntimeError\\):\\n    pass\\n", "\\n"),
        (
            r"\\n@lru_cache\\(maxsize=1\\)\\ndef _crypto_components\\(\\):.*?(?=\\n\\ndef sha256_file)",
            "",
        ),
        (
            r"\\ndef sha256_file\\(path: str \\| Path\\) -> str:.*?(?=\\n\\ndef safe_token)",
            "",
        ),
        (
            r"\\ndef _derive_key\\(secret: str, salt: bytes\\) -> bytes:.*?(?=\\n\\ndef split_file)",
            "",
        ),
    )
    for pattern, value in blocks:
        source, count = re.subn(pattern, value, source, count=1, flags=re.DOTALL)
        if count != 1:
            raise SystemExit(f"files.py crypto block not found: {pattern}")
    path.write_text(source, encoding="utf-8")


'''

source, count = re.subn(
    r"def patch_files\(\) -> None:.*?(?=def patch_models\(\) -> None:)",
    replacement,
    source,
    count=1,
    flags=re.DOTALL,
)
if count != 1:
    raise SystemExit("patch_files function not found")

old = '''def patch_existing_tests() -> None:
    replace_once(
        "tests/test_telegram_storage_center.py",
        '        self.assertIn("AES-256-GCM+scrypt:v1", service)\\n',
        '        self.assertIn("AES-256-GCM+scrypt:v2", service)\\n',
    )
'''
new = '''def patch_existing_tests() -> None:
    replace_once(
        "tests/test_telegram_storage_center.py",
        '        self.assertIn("AES-256-GCM+scrypt:v1", service)\\n',
        '        self.assertIn("AES-256-GCM+scrypt:v2", service)\\n',
    )
    replace_once(
        "tests/test_server_preflight.py",
        '        "STORAGE_ENCRYPTION_SECRET": "storage_secret_12345678901234567890",\\n',
        '        "STORAGE_ENCRYPTION_ACTIVE_KEY_ID": "backup-active",\\n'
        '        "STORAGE_ENCRYPTION_SECRET": "storage_secret_12345678901234567890",\\n',
    )
'''
if old not in source:
    raise SystemExit("patch_existing_tests anchor not found")
source = source.replace(old, new, 1)
path.write_text(source, encoding="utf-8")
Path(__file__).unlink()
