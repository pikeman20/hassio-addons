# Code Standards

This project follows pragmatic code standards focused on readability, maintainability, and minimal friction.

General
-------
- Keep files small (<200 lines) where practical.
- Use kebab-case for file names in JS/TS/Python/shell to make search and tooling predictable.
- Prefer composition over inheritance.
- Use clear function and variable names.

Python
------
- Follow PEP8 for formatting. Limit lines to 100 chars.
- Use dataclasses for simple configuration objects (e.g., TelegramConfig in src/agent/config.py).
- Do not commit secrets into source. Use environment variables for runtime secrets (e.g., SCAN_TELEGRAM_BOT_TOKEN).

Frontend
--------
- Keep components small and focused.
- Centralize state in stores (e.g., scans store) and expose selectors for components.

Bot integrations
----------------
- Bot features must be opt-in via config/env flag.
- Authorization lists can be provided via runtime config; consider persisting if needed.
- Handlers must validate permissions before performing actions.
- Prefer callbacks/hooks over tight coupling: session_manager exposes on_state_change for observers.

Testing
-------
- Write unit tests for command handlers and session state transitions when adding integrations.
- Run tests before merging.

Security
--------
- Never log secrets.
- Validate input from external services.

Notes
-----
- Recent change: Telegram bot integration added handlers and on_state_change support. Follow the Bot integrations guidelines when expanding features.
