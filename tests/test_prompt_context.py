from __future__ import annotations

from core.prompt_context import attachment_notice, build_file_context


def test_build_file_context_attaches_workspace_file(tmp_path) -> None:
    source = tmp_path / "core" / "demo.py"
    source.parent.mkdir()
    source.write_text("print('hello')\n", encoding="utf-8")

    context, attachments = build_file_context("jelaskan @core/demo.py", tmp_path)

    assert "print('hello')" in context
    assert attachments[0].included is True
    assert "attached @core/demo.py" in attachment_notice(attachments)


def test_build_file_context_skips_sensitive_file(tmp_path) -> None:
    secret = tmp_path / ".env"
    secret.write_text("DUMMY_ENV_VALUE=placeholder\n", encoding="utf-8")

    context, attachments = build_file_context("cek @.env", tmp_path)

    assert context == ""
    assert attachments[0].included is False
    assert attachments[0].reason == "sensitive file"
