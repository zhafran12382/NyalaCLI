# NyalaCLI

> AI agent terminal-first untuk Termux Android, ringan, indah, bebas, dan tetap waras.

NyalaCLI adalah Python CLI AI agent yang dibuat untuk layar HP Android melalui Termux. Fokusnya adalah chat terminal yang nyaman, ReAct/tool loop, provider AI fleksibel, tools lokal, session memory, token tracking, custom routing, dan orkestrasi multi-agent ringan bernama NyalaTeam.

Linux, macOS, dan Windows tetap bisa dipakai, tetapi desain path, UX, dependency, dan safety default mengutamakan Termux Android tanpa root.

## Mockup

```text
╭──────────────────────────── NyalaCLI ────────────────────────────╮
│ AI agent terminal-first untuk Termux Android                      │
╰──────────────────────────────────────────────────────────────────╯
╭ provider openrouter  model openrouter/free  mode balanced ───────╮
│ workspace ~/storage/shared/NyalaCLI  session nyala-20260425-...  │
╰──────────────────────────────────────────────────────────────────╯
╭─ Nyala ~/storage/shared/NyalaCLI
╰─❯ /help

╭────────────────────────────── Nyala ─────────────────────────────╮
│ Ringkas, siap pakai, dan bisa memanggil tool bila diperlukan.     │
╰──────────────────────────────────────────────────────────────────╯
```

## Fitur

- Termux Android first: deteksi Termux, path `~/.nyalacli`, workspace `~/storage/shared/NyalaCLI` jika storage tersedia.
- Provider: OpenRouter, Gemini, OpenAI, Groq, Together AI, DeepInfra, Fireworks AI, Mistral, xAI, Perplexity, DeepSeek, Cerebras, local OpenAI-compatible, dan custom endpoint.
- Tools lokal: file manager, bash exec, python exec, Tavily web search, web scraper, generated skill creator.
- ReAct loop JSON: model bisa memanggil tool dengan `{"tool":"nama_tool","args":{...}}`.
- Safety mode: `safe`, `balanced`, `freedom`.
- Secret redaction untuk API key, bearer token, dan private key.
- Session dan compact memory lokal.
- Token estimate sederhana.
- NyalaTeam: Lead, Planner, Runner untuk subtugas ringan.
- UI rich + prompt_toolkit, fallback ke `input()` jika terminal tidak cocok.

## Install Di Termux

```sh
pkg update
pkg install python git
termux-setup-storage
git clone <repo-url>
cd NyalaCLI
pip install -r requirements.txt
python main.py setup
python main.py chat
```

Jika `termux-setup-storage` belum dijalankan, NyalaCLI tidak crash. Workspace akan fallback ke:

```text
~/NyalaCLI_Workspace
```

Config default:

```text
~/.nyalacli/config.json
~/.nyalacli/.env
~/.nyalacli/sessions/
~/.nyalacli/logs/
~/.nyalacli/cache/
```

## Install Linux, macOS, Windows

```sh
git clone <repo-url>
cd NyalaCLI
python -m pip install -r requirements.txt
python main.py setup
python main.py chat
```

Windows didukung sebagai secondary target. Beberapa tool shell akan mengikuti kemampuan `cmd` atau PowerShell yang tersedia.

## Command Utama

```sh
python main.py setup
python main.py chat
python main.py config
python main.py skills
python main.py doctor
python main.py reset
python main.py version
```

## Slash Commands

```text
/help
/model <model_id>
/provider <provider>
/routing <provider_order|json|auto>
/effort Minimal|Low|Medium|High|Xhigh|off
/base-url <url>
/provider-test
/config
/skills
/token
/save <session_id>
/load <session_id>
/sessions
/compact
/clear
/safe on
/safe off
/mode safe
/mode balanced
/mode freedom
/workspace <path>
/pwd
/tree
/team <task>
/configure team
/doctor
/exit
```

## Chat TUI

`python main.py chat` memakai layar chat full-screen jika terminal mendukung `prompt_toolkit`. Layoutnya terdiri dari header, transcript scrollable, composer di bawah, dan footer status.

Keyboard:
- `Enter`: kirim
- `Esc+Enter`: baris baru
- `Tab` atau `Enter` saat suggestion aktif: pilih command suggestion
- `PgUp` / `PgDn`: scroll transcript
- `End`: kembali ke pesan terbaru
- `Ctrl+L`: bersihkan transcript

## Provider Setup

### OpenRouter

Jalankan:

```sh
python main.py setup
```

Pilih `OpenRouter`, isi API key, lalu pilih model dari daftar gratis/murah yang diambil dari OpenRouter. Kamu tetap bisa memasukkan model ID sendiri.

Routing provider bisa `auto`, daftar slug provider, atau JSON object OpenRouter:

```text
deepinfra,together,fireworks
{"order":["deepinfra","together"],"allow_fallbacks":true}
```

Jika kosong, OpenRouter memakai routing otomatis.

Thinking effort bisa diatur hanya untuk model OpenRouter yang mengiklankan parameter reasoning:

```text
/effort Medium
/effort off
```

### Gemini

Pilih `Gemini`, isi `GEMINI_API_KEY`, lalu masukkan model ID seperti:

```text
gemini-1.5-flash
gemini-1.5-pro
```

### OpenAI-Compatible Local

Pilih `OpenAI-compatible local`, lalu isi base URL:

```text
http://127.0.0.1:1234/v1
```

Cocok untuk local server yang menyediakan `/chat/completions`.

### Provider Custom

Pilih `Custom OpenAI-compatible`, isi nama provider, base URL, model ID, dan API key jika endpoint membutuhkannya. Setup akan mengirim prompt test. Jika provider/model/routing gagal, NyalaCLI meminta kamu mengganti pilihan sebelum config disimpan.

## Safety Modes

`safe`:
- konfirmasi semua bash command
- konfirmasi semua write/delete file
- konfirmasi baca file sensitif

`balanced`:
- read-only command boleh jalan
- write/delete perlu konfirmasi
- command berisiko perlu konfirmasi

`freedom`:
- lebih bebas
- destructive command ekstrem tetap diblokir

Command seperti `rm -rf /`, `rm -rf ~/storage`, `mkfs`, `dd if=`, `shutdown`, `reboot`, `curl ... | bash`, dan pola destruktif lain diblokir atau diminta konfirmasi.

## Built-In Skills

- `file_manager`: `list_dir`, `tree`, `read_file`, `write_file`, `append_file`, `delete_file`, `search_files`, `diff_preview`
- `bash_exec`: menjalankan command shell dengan timeout dan safety check
- `python_exec`: menjalankan script Python sementara
- `web_search`: Tavily search jika `TAVILY_API_KEY` tersedia
- `web_scraper`: ambil title, teks, dan links dari halaman web
- `skill_creator`: membuat template skill baru di `generated_skills/`

Generated skill tidak otomatis dieksekusi. Review manual tetap wajib.

## NyalaTeam

NyalaTeam adalah orkestrasi ringan:

- Lead membuat rencana
- Planner opsional merapikan subtugas
- Runner menjalankan subtugas
- Lead mensintesis hasil final

Gunakan:

```text
/configure team
/team refactor modul config dan jelaskan risikonya
```

Tool call Runner tetap melewati permission system yang sama.

## Token Tracking

NyalaCLI memakai estimasi sederhana:

```text
token ~= len(text) / 4
```

Gunakan:

```text
/token
/compact
```

`/compact` meringkas history lama menjadi memory lokal berisi fakta penting, preferensi, file yang diedit, command yang pernah dijalankan, keputusan teknis, dan todo lanjutan.

## Troubleshooting Termux

### Permission denied di storage

Jalankan:

```sh
termux-setup-storage
```

Lalu restart Termux session jika perlu.

### `pip` error

```sh
pkg update
pkg install python
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Jika shell hanya punya `python3`, gunakan `python3 main.py ...` atau buat alias sesuai lingkungan.

### Module not found

Pastikan berada di folder project:

```sh
cd NyalaCLI
pip install -r requirements.txt
python main.py doctor
```

### API key missing

Jalankan ulang:

```sh
python main.py setup
```

API key disimpan di `~/.nyalacli/.env`, bukan di repo.

### Terminal unicode rusak

NyalaCLI otomatis mencoba compact/plain fallback. Jika terminal tetap bermasalah, ubah config:

```json
"ui": {
  "unicode": false,
  "compact": true
}
```

### prompt_toolkit error

NyalaCLI akan fallback ke `input()` biasa dan tetap memakai output rich.

## Security Warning

AI agent terminal punya akses ke file dan command lokal sesuai izin user. Gunakan `safe` atau `balanced` jika bekerja di folder penting. Jangan paste secret ke chat bila tidak perlu. NyalaCLI meredaksi secret di output/log, tetapi redaction bukan pengganti kebiasaan operasional yang aman.

Log tool call disimpan di:

```text
~/.nyalacli/logs/tool_calls.log
```

## Development

```sh
python -m pytest
python main.py doctor
```

Project ini sengaja memakai dependency ringan yang ramah Termux:

```text
rich
prompt_toolkit
questionary
requests
python-dotenv
beautifulsoup4
```
