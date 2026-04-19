# Project Changelog

All notable changes to this project are documented here. Keep entries short and linked to commits/PRs when available.

## 2026-04-19 — Security hardening + image 404 bug fix (security/bugfix)
- Summary: Implemented comprehensive security hardening across path validation, FTP permissions, CORS, error message leaking, Telegram status display, and fixed image 404 bug in session processing.
- Files added/modified:
  - src/web_ui_server.py (_safe_path, _validate_project_id helpers; CORS restricted from wildcard to localhost:5173; _safe_500 helper for generic error messages; all file-serving/deleting endpoints path-validated)
  - src/agent/ftp_server.py (anonymous FTP permissions restricted from full access to write-only)
  - src/agent/agent_api.py (Telegram disabled-status display fix)
  - src/main.py (Telegram status display fix; image processing now copies instead of moves; cleanup logic updated)
- Security improvements:
  - **Path traversal protection**: All file operations validate paths remain within SCAN_OUT_DIR
  - **FTP hardening**: Anonymous users can no longer delete/download/rename scanned files (write-only mode)
  - **CORS lockdown**: Restricted from wildcard to localhost:5173 (configurable via CORS_ORIGINS env)
  - **Error message hardening**: Generic 500 responses prevent internal path/stack leaking
  - **Telegram status clarity**: Web UI now distinguishes "Telegram disabled" from "Telegram not configured"
- Bug fixes:
  - **Image 404 fix**: Process session now copies (not moves) inbox images; original paths saved for cleanup, preventing premature deletion
- Impact: Eliminates path traversal, unauthorized FTP operations, info leakage, and session image 404 errors. No breaking changes.
- Backwards compatibility: Fully compatible. CORS_ORIGINS env is optional (defaults to localhost:5173).

---

## 2026-04-14 — Telegram bot integration (feature)
- Summary: Added a Telegram bot to receive commands (/start, /help, /status, /confirm, /reject), notify users on session state changes, and allow authorized users to confirm/reject scans.
- Files added/modified:
  - src/agent/config.py (TelegramConfig dataclass, env override SCAN_TELEGRAM_BOT_TOKEN)
  - src/agent/telegram_bot.py (TelegramBot implementation)
  - src/agent/session_manager.py (on_state_change callback support)
  - src/main.py (bot lifecycle + integration)
  - src/web_ui_server.py (API endpoints for /api/bot/status and /api/session/status)
  - web_ui/src/ (frontend status display + scans store integration)
- Impact: Adds optional external control/notification channel. No database schema changes. Feature is opt-in via environment variable.
- Rollout notes:
  - Required: set SCAN_TELEGRAM_BOT_TOKEN in production environment and configure authorized Telegram user IDs in the app config.
  - Do NOT commit the token to source. Use your secret manager or CI/CD secret store.
- Backwards compatibility: Fully compatible when bot token is not provided; bot remains disabled.

---

(Older entries kept in commit history.)
