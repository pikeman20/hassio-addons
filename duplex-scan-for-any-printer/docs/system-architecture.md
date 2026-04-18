# System Architecture

Overview
--------
PrinterDuplexScanForCheapPrint is a lightweight scanning orchestration service that manages scanner sessions, composes scans into PDFs, and provides a web UI for operators. The recent Telegram bot integration adds an optional external control and notification channel.

Architectural diagram (textual)
-------------------------------
- Scanners -> Session Manager -> PDF Workers -> Storage
- Web UI <-> Web UI Server <-> Session Manager
- Telegram Bot <-> Telegram API
  - Bot communicates with Session Manager via on_state_change callbacks and command handlers

Components
----------
- src/agent/config.py
  - Holds configuration dataclasses including TelegramConfig. Reads SCAN_TELEGRAM_BOT_TOKEN from environment when provided.
- src/agent/telegram_bot.py
  - TelegramBot class: handles commands (/start, /help, /status, /confirm, /reject), authorization, session state notifications.
- src/agent/session_manager.py
  - Core session lifecycle. Now supports on_state_change callbacks used by the TelegramBot and other observers.
- src/main.py
  - Application bootstrap: initializes session manager, web server, and Telegram bot (if configured). Manages bot lifecycle and graceful shutdown.
- src/web_ui_server.py
  - Provides /api/bot/status and /api/session/status endpoints. Shares bot instance with the main app for live status queries.
- web_ui/src/
  - Frontend shows bot status in EditorView and subscribes to session status updates via scans store.

Data flows
----------
- Session state changes (start, in_progress, waiting_for_confirm, completed, failed) are emitted by Session Manager.
- TelegramBot registers an on_state_change callback to receive events and sends notifications to authorized users.
- Authorized users can send /confirm and /reject commands. Handlers call back into Session Manager to apply decisions.
- Web UI queries /api/session/status and /api/bot/status to display live information.

Deployment considerations
-------------------------
- Bot is optional: if SCAN_TELEGRAM_BOT_TOKEN not set, bot initialization is skipped.
- Ensure Telegram bot token is stored securely in environment/secret store.
- Consider rate limits when enabling notifications for many users. Implement batching or deduping for high-frequency events.

Security
--------
- Authorization: Telegram bot restricts command usage to configured authorized user IDs.
- Secrets: Do not store bot token in source control. Use secret manager.

Open questions
--------------
- Do we want to persist Telegram user authorization list in a config file or a small database? Current implementation reads from runtime config.
- Should bot notifications be rate-limited or aggregated for bursty session events?
