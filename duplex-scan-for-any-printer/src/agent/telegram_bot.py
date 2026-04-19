"""
Telegram Bot for Scanner Confirmation System

Provides command interface for confirming/rejecting scan sessions via Telegram.
"""
from __future__ import annotations

import os
import logging
import threading
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)

from agent.config import Config, TelegramConfig
from agent.notification_manager import NotificationChannel

logger = logging.getLogger(__name__)


@dataclass
class TelegramBot(NotificationChannel):
    """Telegram bot for handling scan session confirmations."""

    config: TelegramConfig
    session_timeout_seconds: int = 300  # mirrors Config.session_timeout_seconds for display
    _application: Optional[Application] = field(default=None, repr=False)
    _running: bool = field(default=False, repr=False)
    _polling_loop: Optional[Any] = field(default=None, repr=False)  # event loop running run_polling
    _authorized_chats: Dict[int, int] = field(default_factory=dict)  # user_id -> chat_id
    _session_callback: Optional[Any] = field(default=None, repr=False)
    _latest_session_info: Optional[Dict] = field(default=None, repr=False)
    _confirmer_chat_id: Optional[int] = field(default=None, repr=False)  # who confirmed — gets the PDF
    # Track message_ids sent per chat so we can edit them (remove buttons) when session resolves.
    _notification_messages: Dict[int, int] = field(default_factory=dict, repr=False)  # chat_id -> message_id
    # Debounce timers for live image-count edits: session_id -> threading.Timer
    _update_timers: Dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def name(self) -> str:
        return "telegram"

    @property
    def status(self) -> Dict[str, Any]:
        return {
            "enabled": self.config.enabled,
            "connected": self._running,
            "authorized_users": len(self._authorized_chats),
            "notify_chat_ids": self.config.notify_chat_ids,
            "registered_chats": {str(uid): cid for uid, cid in self._authorized_chats.items()},
            "pending_session": self._latest_session_info is not None,
            "message": "Bot operational" if self._running else "Bot stopped",
        }

    @property
    def _session_keyboard(self) -> InlineKeyboardMarkup:
        """Confirm/reject keyboard shared by initial notification and live-count edits."""
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton("\u2705 Confirm", callback_data="cmd_confirm"),
                InlineKeyboardButton("\U0001f5a8 Confirm + Print", callback_data="cmd_confirm_print"),
            ],
            [InlineKeyboardButton("\u274c Reject", callback_data="cmd_reject")],
        ])

    def notify_session_ready(self, session_info: Dict[str, Any]) -> None:
        """Store session info and notify all registered chats with inline confirm/reject buttons."""
        self.update_session_info(session_info)
        if not self.config.notify_on_session_ready:
            return
        msg = (
            f"\U0001f4c4 <b>Session Ready for Confirmation</b>\n\n"
            f"<b>ID:</b> {session_info.get('id', 'N/A')}\n"
            f"<b>Mode:</b> {session_info.get('mode', 'N/A')}\n"
            f"<b>Images:</b> {session_info.get('image_count', 0)}"
        )
        self.send_notification(msg, reply_markup=self._session_keyboard)

    def notify_image_added(self, session_info: Dict[str, Any]) -> None:
        """Debounced: edit tracked notification messages with updated image count."""
        if not self._notification_messages:
            return  # No message to update — fast exit
        self.update_session_info(session_info)
        session_id = session_info.get("id", "")
        # Cancel existing pending timer for this session
        existing = self._update_timers.pop(session_id, None)
        if existing:
            existing.cancel()
        timer = threading.Timer(1.5, self._do_update_image_count, args=[dict(session_info)])
        self._update_timers[session_id] = timer
        timer.start()

    def _do_update_image_count(self, session_info: Dict[str, Any]) -> None:
        """Timer callback: edit the Telegram message with the latest image count."""
        session_id = session_info.get("id", "")
        self._update_timers.pop(session_id, None)
        if not self._notification_messages:
            return
        # Prefer the live-updated _latest_session_info for freshest count
        info = self._latest_session_info or session_info
        msg = (
            f"\U0001f4c4 <b>Session Ready for Confirmation</b>\n\n"
            f"<b>ID:</b> {info.get('id', 'N/A')}\n"
            f"<b>Mode:</b> {info.get('mode', 'N/A')}\n"
            f"<b>Images:</b> {info.get('image_count', session_info.get('image_count', 0))}"
        )
        self._schedule(self._edit_notifications_with_keyboard(msg, self._session_keyboard))

    async def _edit_notifications_with_keyboard(
        self, new_text: str, keyboard: InlineKeyboardMarkup
    ) -> None:
        """Edit all tracked session-notification messages and re-attach the given keyboard."""
        for chat_id, message_id in list(self._notification_messages.items()):
            try:
                await self._application.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=new_text,
                    parse_mode="HTML",
                    reply_markup=keyboard,
                )
            except Exception as e:
                logger.debug(f"Could not edit notification in chat {chat_id}: {e}")

    def _cancel_update_timers(self) -> None:
        """Cancel all pending debounce timers (called on session resolve)."""
        for t in self._update_timers.values():
            t.cancel()
        self._update_timers.clear()

    def notify_session_processed(
        self,
        session_id: str,
        mode: str,
        success: bool,
        pdf_path: Optional[str] = None,
    ) -> None:
        """Notify chats that a session has been processed, and send the PDF to the confirmer."""
        icon = "\u2705" if success else "\u274c"
        action = "ready" if success else "failed"
        summary = f"{icon} <b>Session {action}</b>\n<b>ID:</b> {session_id}\n<b>Mode:</b> {mode}"
        self.send_notification(summary)

        # Send PDF document to whoever pressed Confirm (if available)
        if success and pdf_path and self._confirmer_chat_id:
            self._schedule(
                self._send_pdf(self._confirmer_chat_id, pdf_path, session_id)
            )
        self._cancel_update_timers()
        self._latest_session_info = None
        self._confirmer_chat_id = None
        self._notification_messages.clear()

    async def _send_pdf(self, chat_id: int, pdf_path: str, session_id: str) -> None:
        """Send the finished PDF as a document to a specific chat."""
        import os
        if not os.path.exists(pdf_path):
            logger.warning(f"PDF not found, cannot send: {pdf_path}")
            return
        try:
            with open(pdf_path, "rb") as f:
                await self._application.bot.send_document(
                    chat_id=chat_id,
                    document=f,
                    filename=os.path.basename(pdf_path),
                    caption=f"\U0001f4c4 <b>{session_id}</b>",
                    parse_mode="HTML",
                )
        except Exception as e:
            logger.error(f"Failed to send PDF to chat {chat_id}: {e}")

    async def _edit_all_notifications(self, new_text: str) -> None:
        """Edit all tracked session-notification messages: update text and remove buttons."""
        _empty_kb = InlineKeyboardMarkup([])
        for chat_id, message_id in list(self._notification_messages.items()):
            try:
                await self._application.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=new_text,
                    parse_mode="HTML",
                    reply_markup=_empty_kb,
                )
            except Exception as e:
                logger.debug(f"Could not edit notification in chat {chat_id}: {e}")
        self._notification_messages.clear()

    async def _edit_messages(self, messages: Dict[int, int], new_text: str) -> None:
        """Edit an explicit snapshot of messages (chat_id → message_id) and remove buttons.

        Takes a dict snapshot rather than reading the instance variable, so callers
        can sync-clear _notification_messages before scheduling this coroutine without
        risking a race condition.
        """
        _empty_kb = InlineKeyboardMarkup([])
        for chat_id, message_id in messages.items():
            try:
                await self._application.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=new_text,
                    parse_mode="HTML",
                    reply_markup=_empty_kb,
                )
            except Exception as e:
                logger.debug(f"Could not edit notification in chat {chat_id}: {e}")

    def notify_session_action(self, confirmed: bool, action_by: str = "Web UI") -> None:
        """NotificationChannel hook: edit tracked messages when action came from an external
        source (e.g. Web UI).  When Telegram itself triggered the action, _do_confirm /
        reject_command already snapshot+cleared _notification_messages synchronously, so
        this dict is empty and the edit part becomes a safe no-op.
        Always clears session state so /status reflects the resolved session.
        """
        self._cancel_update_timers()
        messages_snapshot = dict(self._notification_messages)
        self._notification_messages.clear()
        # Clear session state regardless of source so /status returns "no active session"
        self._latest_session_info = None
        self._confirmer_chat_id = None
        if not messages_snapshot:
            return
        label = "Confirmed" if confirmed else "Rejected"
        icon = "⏳" if confirmed else "❌"
        text = f"{icon} <b>Session {label}</b> from <i>{action_by}</i>"
        self._schedule(self._edit_messages(messages_snapshot, text))

    def start(self) -> None:
        """Implement NotificationChannel.start() by starting polling."""
        self.start_polling()

    def _schedule(self, coro) -> None:
        """Schedule a coroutine on the bot polling loop from any thread."""
        import asyncio
        loop = self._polling_loop
        if loop and loop.is_running():
            asyncio.run_coroutine_threadsafe(coro, loop)
        else:
            logger.warning("Bot event loop not available — notification dropped")

    @classmethod
    def from_config(cls, config: Config) -> Optional["TelegramBot"]:
        """Create TelegramBot from Config, returns None if not enabled."""
        if not config.telegram.enabled:
            logger.info("Telegram bot is disabled in configuration")
            return None

        if not config.telegram.bot_token:
            logger.warning("Telegram bot enabled but no bot token configured")
            return None

        return cls(config=config.telegram, session_timeout_seconds=config.session_timeout_seconds)

    def set_session_callback(self, callback: Any) -> None:
        """Set callback for session state changes."""
        self._session_callback = callback

    def update_session_info(self, session_info: Dict[str, Any]) -> None:
        """Update the latest session info for display in bot."""
        self._latest_session_info = session_info

    def is_authorized(self, user_id: int) -> bool:
        """Check if user is authorized to use bot commands."""
        if not self.config.authorized_users:
            # No authorized users configured - allow anyone
            return True
        # Compare as strings to handle both int and str values in config
        str_id = str(user_id)
        return any(str(u) == str_id for u in self.config.authorized_users)

    def register_chat(self, user_id: int, chat_id: int) -> None:
        """Register a user's chat ID for notifications."""
        self._authorized_chats[user_id] = chat_id

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /start command."""
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id

        self.register_chat(user_id, chat_id)

        if not self.is_authorized(user_id):
            await update.message.reply_text(
                "❌ You are not authorized to use this bot.\n"
                "Please contact the administrator to get access."
            )
            return

        welcome_text = (
            "✅ <b>Welcome to Scanner Bot!</b>\n\n"
            "This bot allows you to confirm or reject scanning sessions.\n\n"
            "📋 <b>Available Commands:</b>\n"
            "/start - Register and show this message\n"
            "/help - Show help and commands\n"
            "/status - Show current session status\n"
            "/confirm - Confirm current session\n"
            "/reject - Reject current session\n\n"
            "⏱️ Sessions will auto-timeout after "
            f"{self.session_timeout_seconds // 60} minutes of inactivity."
        )

        await update.message.reply_text(welcome_text, parse_mode="HTML")

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /help command."""
        if not self.is_authorized(update.effective_user.id):
            await update.message.reply_text("❌ You are not authorized to use this bot.")
            return

        help_text = (
            "📖 <b>Help</b>\n\n"
            "<b>/start</b> - Register with the bot\n"
            "<b>/help</b> - Show this help message\n"
            "<b>/status</b> - Show current session status and pending actions\n"
            "<b>/confirm</b> - Confirm the current scanning session and process it\n"
            "<b>/reject</b> - Reject and discard the current session\n\n"
            "<b>Note:</b> Only one session can be active at a time.\n"
            f"Auto-timeout: {self.session_timeout_seconds // 60} minutes"
        )

        keyboard = [
            [InlineKeyboardButton("📊 Status", callback_data="cmd_status")],
            [InlineKeyboardButton("✅ Confirm", callback_data="cmd_confirm")],
            [InlineKeyboardButton("❌ Reject", callback_data="cmd_reject")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(help_text, parse_mode="HTML", reply_markup=reply_markup)

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /status command."""
        if not self.is_authorized(update.effective_user.id):
            await update.message.reply_text("❌ You are not authorized to use this bot.")
            return

        if not self._latest_session_info:
            await update.message.reply_text(
                "📭 No active session.\n"
                "Scans will automatically appear here when images are uploaded."
            )
            return

        session = self._latest_session_info
        status_text = (
            f"📊 <b>Session Status</b>\n\n"
            f"<b>Session ID:</b> {session.get('id', 'N/A')}\n"
            f"<b>Mode:</b> {session.get('mode', 'N/A')}\n"
            f"<b>State:</b> {session.get('state', 'N/A')}\n"
            f"<b>Images:</b> {session.get('image_count', 0)}\n"
            f"<b>Timeout:</b> {self.session_timeout_seconds // 60} minutes"
        )

        keyboard = [
            [InlineKeyboardButton("✅ Confirm", callback_data="cmd_confirm")],
            [InlineKeyboardButton("❌ Reject", callback_data="cmd_reject")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(status_text, parse_mode="HTML", reply_markup=reply_markup)

    async def _reply(self, update: Update, text: str) -> None:
        """Reply to either a message or a callback_query edit.

        When editing a callback-query message we always pass an empty InlineKeyboardMarkup
        so Telegram actually removes the buttons (omitting reply_markup keeps them).
        """
        _empty_kb = InlineKeyboardMarkup([])
        if update.callback_query:
            try:
                await update.callback_query.edit_message_text(
                    text, parse_mode="HTML", reply_markup=_empty_kb
                )
            except Exception:
                await update.callback_query.message.reply_text(text, parse_mode="HTML")
        elif update.message:
            await update.message.reply_text(text, parse_mode="HTML")

    async def _do_confirm(self, update: Update, print_requested: bool = False) -> None:
        """Shared confirm logic used by /confirm command and inline buttons."""
        user = update.effective_user
        if not self.is_authorized(user.id):
            await self._reply(update, "❌ You are not authorized to use this bot.")
            return
        if not self._latest_session_info:
            await self._reply(update, "❌ No active session to confirm.")
            return
        if not self._session_callback:
            await self._reply(update, "⚠️ Bot not connected to session manager.")
            return

        # Immediately acknowledge the requester — user knows the tap/click was received
        label = "Confirm + Print" if print_requested else "Confirm"
        await self._reply(
            update,
            f"⏳ <b>{label}</b> received — processing…\n\nYou will receive the PDF when done.",
        )

        # Remember who confirmed so we can send them the finished PDF
        self._confirmer_chat_id = update.effective_chat.id if update.effective_chat else user.id

        # Snapshot and sync-clear tracked messages BEFORE scheduling the edit.
        # This prevents a race where _handle_telegram_command (called right after
        # _session_callback below) sees a non-empty dict and double-edits.
        confirmer_name = user.first_name or str(user.id)
        messages_snapshot = dict(self._notification_messages)
        self._notification_messages.clear()
        if messages_snapshot:
            self._schedule(
                self._edit_messages(
                    messages_snapshot,
                    f"⏳ <b>{label}</b> — processing…\n<i>Confirmed by {confirmer_name}</i>",
                )
            )

        try:
            self._session_callback(confirm=True, print_requested=print_requested)
        except Exception as e:
            logger.error(f"Error confirming session: {e}")
            self._confirmer_chat_id = None
            await self._reply(update, f"❌ Error confirming session: {e}")

    async def confirm_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /confirm command."""
        await self._do_confirm(update, print_requested=False)

    async def reject_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /reject command."""
        user = update.effective_user
        if not self.is_authorized(user.id):
            await self._reply(update, "❌ You are not authorized to use this bot.")
            return
        if not self._latest_session_info:
            await self._reply(update, "❌ No active session to reject.")
            return
        if not self._session_callback:
            await self._reply(update, "⚠️ Bot not connected to session manager.")
            return
        await self._reply(update, "\u23f3 Reject received \u2014 cleaning up\u2026")
        # Snapshot and sync-clear before scheduling edit (prevents race with _handle_telegram_command)
        rejecter_name = user.first_name or str(user.id)
        messages_snapshot = dict(self._notification_messages)
        self._notification_messages.clear()
        if messages_snapshot:
            self._schedule(
                self._edit_messages(
                    messages_snapshot,
                    f"\u274c <b>Session rejected</b> by {rejecter_name}",
                )
            )
        try:
            self._session_callback(confirm=False, print_requested=False)
            self._latest_session_info = None
            self._confirmer_chat_id = None
        except Exception as e:
            logger.error(f"Error rejecting session: {e}")
            await self._reply(update, f"❌ Error rejecting session: {e}")

    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle inline button callbacks."""
        query = update.callback_query
        await query.answer()

        if not self.is_authorized(query.from_user.id):
            await query.edit_message_text("❌ You are not authorized.")
            return

        data = query.data

        if data == "cmd_status":
            await self.status_command(update, context)
        elif data == "cmd_confirm":
            await self._do_confirm(update, print_requested=False)
        elif data == "cmd_confirm_print":
            await self._do_confirm(update, print_requested=True)
        elif data == "cmd_reject":
            await self.reject_command(update, context)

    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle errors."""
        logger.error(f"Error handling update: {context.error}")
        if update and update.message:
            await update.message.reply_text(
                "⚠️ An error occurred. Please try again later."
            )

    def start_polling(self) -> None:
        """Start the bot polling in a background thread."""
        if self._running:
            logger.warning("Bot is already running")
            return

        if not self.config.bot_token:
            logger.error("Cannot start bot: no bot token configured")
            return

        try:
            # Fix: SSL_CERT_FILE may point to a missing file (e.g., from another project's env).
            # Override it with certifi's bundled CA certificates so httpx/telegram can build SSL context.
            ssl_cert_file = os.environ.get("SSL_CERT_FILE", "")
            if ssl_cert_file and not os.path.exists(ssl_cert_file):
                try:
                    import certifi
                    os.environ["SSL_CERT_FILE"] = certifi.where()
                    logger.info(f"SSL_CERT_FILE was invalid ({ssl_cert_file!r}), overriding with certifi: {certifi.where()}")
                except ImportError:
                    del os.environ["SSL_CERT_FILE"]
                    logger.info(f"SSL_CERT_FILE was invalid ({ssl_cert_file!r}), unset to use system defaults")

            # Build application
            self._application = (
                Application.builder()
                .token(self.config.bot_token)
                .build()
            )

            # Add handlers
            self._application.add_handler(CommandHandler("start", self.start_command))
            self._application.add_handler(CommandHandler("help", self.help_command))
            self._application.add_handler(CommandHandler("status", self.status_command))
            self._application.add_handler(CommandHandler("confirm", self.confirm_command))
            self._application.add_handler(CommandHandler("reject", self.reject_command))
            self._application.add_handler(
                MessageHandler(filters.TEXT & ~filters.COMMAND, self.help_command)
            )
            self._application.add_handler(
                CallbackQueryHandler(self.button_callback)
            )

            # Add error handler
            self._application.add_error_handler(self.error_handler)

            # Start polling in a dedicated event loop so we can schedule
            # send_notification calls onto it from other threads.
            def run_polling():
                import asyncio
                import time
                max_retries = 5
                retry_delay = 10

                for attempt in range(max_retries):
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    self._polling_loop = loop
                    try:
                        logger.info(f"Bot polling started (attempt {attempt + 1}/{max_retries})")
                        # Use manual start/stop instead of run_polling() to avoid
                        # add_signal_handler() which only works on the main thread.
                        async def _poll():
                            await self._application.initialize()
                            await self._application.start()
                            await self._application.updater.start_polling(
                                drop_pending_updates=True
                            )
                            # Keep running until _running is cleared
                            while self._running:
                                await asyncio.sleep(1)
                            await self._application.updater.stop()
                            await self._application.stop()
                            await self._application.shutdown()

                        loop.run_until_complete(_poll())
                        break  # clean exit — don't retry
                    except Exception as e:
                        if attempt < max_retries - 1:
                            logger.warning(f"Bot polling crashed, restarting in {retry_delay}s: {e}")
                            time.sleep(retry_delay)
                        else:
                            logger.error(f"Bot polling failed after {max_retries} attempts: {e}")
                            self._running = False
                    finally:
                        try:
                            loop.close()
                        except Exception:
                            pass
                        self._polling_loop = None

            self._running = True
            threading.Thread(target=run_polling, daemon=True, name="telegram-polling").start()
            logger.info("Telegram bot started successfully")

        except Exception as e:
            logger.error(f"Failed to start Telegram bot: {e}")
            self._running = False

    def stop(self) -> None:
        """Stop the bot."""
        # Signal the polling loop to exit cleanly (loop checks self._running).
        self._running = False
        logger.info("Telegram bot stopped")

    def send_notification(
        self,
        message: str,
        parse_mode: str = "HTML",
        reply_markup: Optional[InlineKeyboardMarkup] = None,
    ) -> None:
        """Send a message to all configured and registered chat IDs."""
        if not self._running or not self._application:
            logger.warning("Cannot send notification: bot not running")
            return

        # Merge pre-configured chat IDs with dynamically registered ones.
        chat_ids: set = set()
        for cid in self.config.notify_chat_ids:
            try:
                chat_ids.add(int(cid))
            except (ValueError, TypeError):
                pass
        chat_ids.update(self._authorized_chats.values())

        if not chat_ids:
            logger.warning(
                "No chat IDs to notify. Add your chat ID to notify_chat_ids in config.yaml "
                "or send /start to the bot in a private chat."
            )
            return

        async def _send_to_all() -> None:
            for chat_id in chat_ids:
                try:
                    msg = await self._application.bot.send_message(
                        chat_id=chat_id,
                        text=message,
                        parse_mode=parse_mode,
                        reply_markup=reply_markup,
                    )
                    # Track message_id so we can edit/clear it later
                    self._notification_messages[chat_id] = msg.message_id
                except Exception as e:
                    err = str(e)
                    if "Forbidden" in err or "bot can't initiate" in err:
                        logger.warning(
                            f"Cannot DM chat {chat_id}: user hasn't started the bot in private. "
                            "Ask them to open the bot and send /start."
                        )
                    else:
                        logger.error(f"Failed to send notification to chat {chat_id}: {e}")

        self._schedule(_send_to_all())


# Import CallbackQueryHandler at module level for the handler
from telegram.ext import CallbackQueryHandler