# Repository Guidelines

## Project Structure & Module Organization

NyalaCLI is a Python terminal application with `main.py` as the CLI entry point. Core agent behavior, configuration, sessions, permissions, routing, and token utilities live in `core/`. Provider integrations are in `providers/`; built-in tools are in `skills/`; terminal UI helpers are in `ui/`. Tests live in `tests/` and mirror the modules they cover, such as `tests/test_config.py`. Generated user skills belong in `generated_skills/`. Runtime artifacts such as `__pycache__/`, `.pytest_cache/`, and `.tmp_setup_home/` should not be treated as source.

## Build, Test, and Development Commands

Install runtime dependencies:

```sh
python -m pip install -r requirements.txt
```

Run initial interactive setup:

```sh
python main.py setup
```

Start the local chat CLI:

```sh
python main.py chat
```

Run diagnostics and version checks:

```sh
python main.py doctor
python main.py version
```

Run the test suite:

```sh
python -m pytest tests
```

## Coding Style & Naming Conventions

Use Python 3 with 4-space indentation and type hints where they improve clarity. Keep module names lowercase with underscores, matching existing files such as `token_counter.py` and `openai_compatible.py`. Test files should be named `test_<module>.py`, and test functions should use `test_<behavior>()`. Prefer `pathlib.Path` for filesystem paths and keep user-facing terminal output routed through `ui/` helpers when practical.

## Testing Guidelines

The repository uses `pytest`. Keep tests focused on public behavior and side effects, especially configuration, session persistence, and permission handling. Use `tmp_path` and `monkeypatch` for filesystem and environment isolation. Add or update tests when changing logic in `core/`, provider selection, safety rules, or session storage.

## Commit & Pull Request Guidelines

This checkout does not include accessible Git history, so follow a simple imperative commit style, for example `Add Gemini provider validation` or `Fix session save path`. Pull requests should describe the user-visible change, list tests run, mention configuration or secret-handling impacts, and include terminal screenshots only for UI changes.

## Security & Configuration Tips

Do not commit API keys, local `.env` files, session logs, cache data, or generated runtime directories. `python main.py setup` stores secrets under `~/.nyalacli/.env`; tests should use temporary paths instead of real user configuration.
