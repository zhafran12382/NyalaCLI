from __future__ import annotations

from pathlib import Path

from core.permissions import PermissionManager, is_extreme_command, is_sensitive_file, redact_secrets


def test_blocks_extreme_rm() -> None:
    assert is_extreme_command("rm -rf /")
    decision = PermissionManager("freedom").check_command("rm -rf /")
    assert decision.allowed is False


def test_sensitive_file_patterns() -> None:
    assert is_sensitive_file(Path(".env"))
    assert is_sensitive_file(Path("id_ed25519"))
    assert is_sensitive_file(Path("secret.pem"))


def test_redacts_common_secrets() -> None:
    text = "Authorization: Bearer abcdefghijklmnopqrstuvwxyz"
    assert "[REDACTED]" in redact_secrets(text)
