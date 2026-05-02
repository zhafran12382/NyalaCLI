from __future__ import annotations

import difflib
from pathlib import Path
from typing import Any

from core.permissions import PermissionManager, is_sensitive_file, redact_secrets, safe_path_display

from .base import SkillResult, truncate, workspace_path


class FileManagerSkill:
    name = "file_manager"
    description = "Kelola file: list_dir, tree, read_file, write_file, append_file, delete_file, search_files, diff_preview."
    parameters_schema = {
        "action": "list_dir|tree|read_file|write_file|append_file|delete_file|search_files|diff_preview",
        "path": "Path relatif workspace atau absolute jika perlu.",
        "content": "Konten untuk write/append/diff.",
        "query": "Query untuk search_files.",
        "max_depth": "Depth tree.",
    }

    def run(self, args: dict[str, Any], context: dict[str, Any]) -> SkillResult:
        action = str(args.get("action", "")).strip()
        workspace = context["workspace"]
        permission: PermissionManager = context["permission"]
        console = context.get("console")

        try:
            if action == "list_dir":
                return self.list_dir(workspace_path(workspace, args.get("path") or "."))
            if action == "tree":
                return self.tree(workspace_path(workspace, args.get("path") or "."), int(args.get("max_depth", 3)))
            if action == "read_file":
                path = workspace_path(workspace, args.get("path"))
                decision = permission.check_file("read", path)
                if not permission.confirm_if_needed(decision, f"Baca file {safe_path_display(path)}?", console):
                    return SkillResult(False, "Akses file ditolak.")
                return self.read_file(path)
            if action == "write_file":
                path = workspace_path(workspace, args.get("path"))
                content = str(args.get("content", ""))
                decision = permission.check_file("write", path)
                if not permission.confirm_if_needed(decision, f"Tulis file {safe_path_display(path)}?", console):
                    return SkillResult(False, "Write file dibatalkan.")
                return self.write_file(path, content)
            if action == "append_file":
                path = workspace_path(workspace, args.get("path"))
                content = str(args.get("content", ""))
                decision = permission.check_file("append", path)
                if not permission.confirm_if_needed(decision, f"Append file {safe_path_display(path)}?", console):
                    return SkillResult(False, "Append file dibatalkan.")
                return self.append_file(path, content)
            if action == "delete_file":
                path = workspace_path(workspace, args.get("path"))
                decision = permission.check_file("delete", path)
                if not permission.confirm_if_needed(decision, f"Hapus file {safe_path_display(path)}?", console):
                    return SkillResult(False, "Delete file dibatalkan.")
                return self.delete_file(path)
            if action == "search_files":
                return self.search_files(workspace_path(workspace, args.get("path") or "."), str(args.get("query", "")))
            if action == "diff_preview":
                path = workspace_path(workspace, args.get("path"))
                return self.diff_preview(path, str(args.get("content", "")))
            return SkillResult(False, f"Aksi file_manager tidak dikenal: {action}")
        except Exception as exc:
            return SkillResult(False, f"file_manager error: {exc}")

    def list_dir(self, path: Path) -> SkillResult:
        if not path.exists():
            return SkillResult(False, f"Folder tidak ada: {safe_path_display(path)}")
        if not path.is_dir():
            return SkillResult(False, f"Bukan folder: {safe_path_display(path)}")
        lines = []
        for item in sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
            mark = "/" if item.is_dir() else ""
            lines.append(f"{item.name}{mark}")
        output = "\n".join(lines) or "(kosong)"
        return SkillResult(True, output)

    def tree(self, path: Path, max_depth: int = 3) -> SkillResult:
        if not path.exists():
            return SkillResult(False, f"Path tidak ada: {safe_path_display(path)}")
        max_depth = max(1, min(max_depth, 6))
        lines = [f"{path.name}/" if path.is_dir() else path.name]

        def walk(current: Path, prefix: str, depth: int) -> None:
            if depth > max_depth or not current.is_dir():
                return
            children = sorted(current.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
            children = [child for child in children if child.name not in {".git", "__pycache__"}]
            for index, child in enumerate(children[:80]):
                connector = "└── " if index == len(children[:80]) - 1 else "├── "
                lines.append(prefix + connector + child.name + ("/" if child.is_dir() else ""))
                extension = "    " if connector.startswith("└") else "│   "
                walk(child, prefix + extension, depth + 1)

        walk(path, "", 1)
        output, truncated = truncate("\n".join(lines), 10000)
        return SkillResult(True, output, "\n".join(lines) if truncated else None)

    def read_file(self, path: Path) -> SkillResult:
        if not path.exists():
            return SkillResult(False, f"File tidak ada: {safe_path_display(path)}")
        if not path.is_file():
            return SkillResult(False, f"Bukan file: {safe_path_display(path)}")
        text = path.read_text(encoding="utf-8", errors="replace")
        if is_sensitive_file(path):
            text = redact_secrets(text)
        output, truncated = truncate(text)
        return SkillResult(True, output, text if truncated else None)

    def write_file(self, path: Path, content: str) -> SkillResult:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return SkillResult(True, f"Ditulis: {safe_path_display(path)} ({len(content)} chars)")

    def append_file(self, path: Path, content: str) -> SkillResult:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(content)
        return SkillResult(True, f"Ditambahkan: {safe_path_display(path)} ({len(content)} chars)")

    def delete_file(self, path: Path) -> SkillResult:
        if not path.exists():
            return SkillResult(False, f"File tidak ada: {safe_path_display(path)}")
        if path.is_dir():
            return SkillResult(False, "delete_file hanya menghapus file, bukan folder.")
        path.unlink()
        return SkillResult(True, f"Dihapus: {safe_path_display(path)}")

    def search_files(self, path: Path, query: str) -> SkillResult:
        if not query:
            return SkillResult(False, "Query kosong.")
        if not path.exists():
            return SkillResult(False, f"Path tidak ada: {safe_path_display(path)}")
        matches: list[str] = []
        for item in path.rglob("*"):
            if len(matches) >= 200:
                break
            if item.is_dir() and item.name in {".git", "__pycache__"}:
                continue
            if query.lower() in item.name.lower():
                matches.append(safe_path_display(item))
                continue
            if item.is_file() and item.stat().st_size <= 512_000:
                try:
                    text = item.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                for line_no, line in enumerate(text.splitlines(), start=1):
                    if query.lower() in line.lower():
                        matches.append(f"{safe_path_display(item)}:{line_no}: {line.strip()[:160]}")
                        break
        return SkillResult(True, "\n".join(matches) or "Tidak ada hasil.")

    def diff_preview(self, path: Path, content: str) -> SkillResult:
        old = ""
        if path.exists() and path.is_file():
            old = path.read_text(encoding="utf-8", errors="replace")
        diff = difflib.unified_diff(
            old.splitlines(),
            content.splitlines(),
            fromfile=str(path),
            tofile=f"{path} (new)",
            lineterm="",
        )
        output = "\n".join(diff) or "Tidak ada perubahan."
        output, truncated = truncate(output, 10000)
        return SkillResult(True, output, None if not truncated else output)
