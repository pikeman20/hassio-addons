"""Internal Agent API (127.0.0.1:8098)

Exposes scan agent state and commands as a localhost-only HTTP API.
Used by the web UI process (and any future integrations) to:
  - Query current session state
  - Issue confirm/reject commands
  - Check notification channel statuses

Binding to 127.0.0.1 prevents external access — only localhost services
(web UI, future dashboard, etc.) can call this API.
"""
from __future__ import annotations

import asyncio
import logging
import threading
from typing import Optional, Any, Callable

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

# Module-level state set by init() before start_in_thread()
_session_manager: Optional[Any] = None
_notification_manager: Optional[Any] = None
_session_command_cb: Optional[Callable] = None  # (confirm: bool, print_requested: bool) -> None

app = FastAPI(title="Scan Agent Internal API", docs_url=None, redoc_url=None)


def init(
    session_manager: Any,
    notification_manager: Any,
    session_command_cb: Callable,
) -> None:
    """Wire up references. Must be called before start_in_thread()."""
    global _session_manager, _notification_manager, _session_command_cb
    _session_manager = session_manager
    _notification_manager = notification_manager
    _session_command_cb = session_command_cb


def start_in_thread(host: str = "127.0.0.1", port: int = 8098) -> None:
    """Launch uvicorn in a daemon thread bound to localhost only."""
    def _run() -> None:
        uvicorn.run(app, host=host, port=port, log_level="error")

    threading.Thread(target=_run, daemon=True, name="agent-api").start()
    logger.info("Agent internal API listening on %s:%d", host, port)


# ─── Endpoints ────────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/api/session/current")
async def session_current():
    """Return the most relevant active session (prefers WAIT_CONFIRM)."""
    if _session_manager is None:
        return JSONResponse({"session": None, "message": "not initialized"})

    with _session_manager._lock:
        sessions = list(_session_manager._by_mode.values())

    if not sessions:
        return JSONResponse({"session": None})

    waiting = [s for s in sessions if s.state == "WAIT_CONFIRM"]
    s = waiting[0] if waiting else max(sessions, key=lambda x: x.last_activity)
    return JSONResponse({
        "session": {
            "id": s.id,
            "mode": s.mode,
            "state": s.state,
            "image_count": len(s.images),
            "created_at": s.created_at,
            "last_activity": s.last_activity,
        }
    })


@app.post("/api/session/confirm")
async def session_confirm(print_requested: bool = False):
    """Confirm the current WAIT_CONFIRM session.

    Fires the callback in a thread pool so the endpoint returns immediately
    without blocking while image processing runs.
    """
    if _session_command_cb is None:
        return JSONResponse({"ok": False, "message": "no command handler"}, status_code=503)
    try:
        loop = asyncio.get_event_loop()
        loop.run_in_executor(None, lambda: _session_command_cb(confirm=True, print_requested=print_requested))
        return JSONResponse({"ok": True, "message": "confirm accepted"})
    except Exception as e:
        return JSONResponse({"ok": False, "message": str(e)}, status_code=500)


@app.post("/api/session/reject")
async def session_reject():
    """Reject the current WAIT_CONFIRM session.

    Fires the callback in a thread pool so the endpoint returns immediately.
    """
    if _session_command_cb is None:
        return JSONResponse({"ok": False, "message": "no command handler"}, status_code=503)
    try:
        loop = asyncio.get_event_loop()
        loop.run_in_executor(None, lambda: _session_command_cb(confirm=False, print_requested=False))
        return JSONResponse({"ok": True, "message": "reject accepted"})
    except Exception as e:
        return JSONResponse({"ok": False, "message": str(e)}, status_code=500)


@app.get("/api/channels/status")
async def channels_status():
    """Return status of all notification channels (Telegram, etc.)."""
    if _notification_manager is None:
        return JSONResponse({"channels": {}})
    return JSONResponse({"channels": _notification_manager.get_statuses()})


@app.get("/api/channels/telegram/info")
async def telegram_info():
    """Return Telegram-specific info: registered chats and notify_chat_ids.

    This lets the web UI show which chat IDs are active so the user can copy
    their chat ID into config.yaml under notify_chat_ids.
    """
    if _notification_manager is None:
        return JSONResponse({"registered_chats": {}, "notify_chat_ids": []})
    statuses = _notification_manager.get_statuses()
    tg = statuses.get("telegram", {})
    return JSONResponse({
        "registered_chats": tg.get("registered_chats", {}),
        "notify_chat_ids": tg.get("notify_chat_ids", []),
    })
