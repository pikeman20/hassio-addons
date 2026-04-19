# Development Roadmap

This roadmap tracks major features, phases, and progress.

## 2026 Q2

- Security hardening — Completed (2026-04-19)
  - Description: Implement path traversal protection, FTP permission restriction, CORS lockdown, error message hardening, and fix Telegram status display. Also fix image 404 bug in session processing.
  - Status: Done
  - Owner: engineering
  - Notes: Path validation on all file operations, FTP write-only for anonymous, CORS restricted to localhost:5173 (configurable), generic error messages, fixed image processing copying. See project-changelog.md and system-architecture.md for details.

- Telegram bot integration — Completed (2026-04-14)
  - Description: Add Telegram bot for notifications and remote confirmation of scan sessions.
  - Status: Done
  - Owner: engineering
  - Notes: Bot is opt-in via SCAN_TELEGRAM_BOT_TOKEN. See system-architecture.md and project-changelog.md for details.

- PDF preview worker improvements — In progress
  - Status: In progress

- Thumbnail rotation UX tweaks — Done (see commit history)

Roadmap maintenance
-------------------
- Update this file when phases change status or new features are planned.
