from __future__ import annotations

from rich.table import Table

from .autocomplete import SLASH_COMMANDS


HELP_ROWS = [
    ("/help", "Tampilkan bantuan."),
    ("/home", "Bersihkan layar dan tampilkan dashboard awal."),
    ("/palette", "Tampilkan command palette ringkas."),
    ("/context | /usage | /stats", "Tampilkan estimasi pemakaian context/token."),
    ("/model <model_id>", "Ganti model aktif."),
    ("/provider <provider>", "Ganti provider dan test koneksi."),
    ("/routing <provider_order|json|auto>", "Atur routing OpenRouter dan test koneksi."),
    ("/effort Minimal|Low|Medium|High|Xhigh|off", "Atur thinking effort jika model mendukung."),
    ("/base-url <url>", "Ganti endpoint local/custom lalu test koneksi."),
    ("/provider-test", "Kirim prompt test ke provider aktif."),
    ("/config", "Tampilkan config redacted."),
    ("/stream true|false", "Aktifkan/nonaktifkan output streaming."),
    ("/skills", "Tampilkan built-in skills."),
    ("/token", "Tampilkan estimasi token."),
    ("/save <session_id>", "Simpan session."),
    ("/load <session_id>", "Load session."),
    ("/resume [session_id]", "Resume session tertentu atau session terbaru."),
    ("/sessions", "Daftar session."),
    ("/compact", "Ringkas history ke memory lokal."),
    ("/clear", "Bersihkan layar."),
    ("/safe on|off", "Shortcut safe/freedom."),
    ("/mode safe|balanced|freedom", "Atur safety mode."),
    ("/workspace <path>", "Ganti workspace."),
    ("/pwd", "Tampilkan workspace."),
    ("/tree", "Tampilkan tree workspace."),
    ("/team <task>", "Jalankan NyalaTeam."),
    ("/configure team", "Konfigurasi jumlah planner/runner."),
    ("/doctor", "Jalankan doctor check."),
    ("/exit | /quit", "Keluar chat. Ctrl+C/Ctrl+Q juga didukung di TUI."),
    ("@<path>", "Lampirkan isi file workspace sebagai context prompt."),
    ("!<command>", "Jalankan command shell lewat permission system."),
]

PALETTE_GROUPS = {
    "Session": [
        ("/resume", "lanjutkan session terakhir"),
        ("/sessions", "lihat daftar session"),
        ("/save <id>", "simpan session aktif"),
        ("/compact", "ringkas history"),
    ],
    "Workspace": [
        ("@path", "lampirkan file ke prompt"),
        ("!cmd", "jalankan command lokal"),
        ("/workspace <path>", "pindah workspace"),
        ("/tree", "lihat tree workspace"),
    ],
    "Agent": [
        ("/model <id>", "ganti model"),
        ("/provider <name>", "ganti provider"),
        ("/provider-test", "cek provider aktif"),
        ("/stream true", "nyalakan streaming output"),
        ("/effort <level>", "atur thinking"),
        ("/mode safe|balanced|freedom", "ubah safety"),
        ("/team <task>", "orkestrasi NyalaTeam"),
    ],
    "Inspect": [
        ("/home", "tampilkan dashboard"),
        ("/context", "meter token"),
        ("/config", "config redacted"),
        ("/skills", "built-in tools"),
        ("/doctor", "diagnostik environment"),
        ("/quit", "keluar chat"),
    ],
}


def help_table() -> Table:
    table = Table(title="NyalaCLI Slash Commands", expand=True)
    table.add_column("Command", style="nyala.cyan", no_wrap=True)
    table.add_column("Fungsi", style="white")
    for command, description in HELP_ROWS:
        table.add_row(command, description)
    return table


def palette_table() -> Table:
    table = Table(title="Command Palette", expand=True, show_lines=False)
    table.add_column("Area", style="nyala.dim", no_wrap=True)
    table.add_column("Action", style="nyala.cyan", no_wrap=True)
    table.add_column("Use", style="white")
    for group, rows in PALETTE_GROUPS.items():
        for index, (command, description) in enumerate(rows):
            table.add_row(group if index == 0 else "", command, description)
    return table


def skills_table(skills: dict) -> Table:
    table = Table(title="Built-in Skills", expand=True)
    table.add_column("Skill", style="nyala.cyan", no_wrap=True)
    table.add_column("Deskripsi", style="white")
    for name, skill in sorted(skills.items()):
        table.add_row(name, getattr(skill, "description", ""))
    return table


def command_names() -> list[str]:
    return SLASH_COMMANDS[:]
