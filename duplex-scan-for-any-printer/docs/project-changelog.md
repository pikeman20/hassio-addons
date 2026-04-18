# Project Changelog

All notable changes to this project are documented here. Keep entries short and linked to commits/PRs when available.

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

(Older entries kept in commit history. Add future entries here.)
