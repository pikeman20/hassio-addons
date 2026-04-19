"""Notification channel abstraction.

Implement NotificationChannel to add new notification/command channels
(Telegram, email, webhook, etc.) without modifying the core scan logic.

Usage:
    class MyChannel(NotificationChannel):
        @property
        def name(self) -> str: return "myservice"
        def notify_session_ready(self, session_info): ...
        def notify_session_processed(self, session_id, mode, success): ...
        @property
        def status(self) -> dict: return {"enabled": True, "connected": True, "message": "ok"}
        def start(self): ...
        def stop(self): ...

    manager = NotificationManager([MyChannel()])
    manager.start_all()
    manager.notify_session_ready({"id": "...", "mode": "scan_duplex", ...})
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Sequence, Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class NotificationChannel(ABC):
    """Abstract base for a notification/command channel."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique channel identifier (e.g. 'telegram', 'webhook')."""

    @abstractmethod
    def notify_session_ready(self, session_info: Dict[str, Any]) -> None:
        """Called when a session enters WAIT_CONFIRM state."""

    @abstractmethod
    def notify_session_processed(
        self, session_id: str, mode: str, success: bool, pdf_path: Optional[str] = None
    ) -> None:
        """Called after a session completes (confirmed or rejected)."""

    @property
    @abstractmethod
    def status(self) -> Dict[str, Any]:
        """Channel health dict with at least: enabled, connected, message."""

    @abstractmethod
    def start(self) -> None:
        """Connect / begin polling."""

    @abstractmethod
    def stop(self) -> None:
        """Disconnect / stop polling."""

    def notify_image_added(self, session_info: Dict[str, Any]) -> None:
        """Called when an image is added to an active session. Default: no-op."""

    def notify_session_action(self, confirmed: bool, action_by: str = "external") -> None:
        """Called when a session is confirmed/rejected from an external source (e.g. Web UI).

        Channels that track in-flight notification messages (e.g. Telegram inline keyboards)
        should use this to update/remove those messages.  Default is a no-op so existing
        channel implementations don't need to override it.
        """


class NotificationManager:
    """Broadcasts session events to all registered channels."""

    def __init__(self, channels: Sequence[NotificationChannel] = ()) -> None:
        self._channels: List[NotificationChannel] = list(channels)

    def add_channel(self, channel: NotificationChannel) -> None:
        self._channels.append(channel)

    def notify_session_ready(self, session_info: Dict[str, Any]) -> None:
        for ch in self._channels:
            try:
                ch.notify_session_ready(session_info)
            except Exception as e:
                logger.error("[%s] notify_session_ready failed: %s", ch.name, e)

    def notify_session_processed(
        self, session_id: str, mode: str, success: bool, pdf_path: Optional[str] = None
    ) -> None:
        for ch in self._channels:
            try:
                ch.notify_session_processed(session_id, mode, success, pdf_path=pdf_path)
            except Exception as e:
                logger.error("[%s] notify_session_processed failed: %s", ch.name, e)

    def notify_image_added(self, session_info: Dict[str, Any]) -> None:
        """Broadcast image-added event to all channels (for live count updates)."""
        for ch in self._channels:
            try:
                ch.notify_image_added(session_info)
            except Exception as e:
                logger.error("[%s] notify_image_added failed: %s", ch.name, e)

    def notify_session_action(self, confirmed: bool, action_by: str = "external") -> None:
        """Broadcast confirm/reject action to all channels (for UI cleanup)."""
        for ch in self._channels:
            try:
                ch.notify_session_action(confirmed, action_by)
            except Exception as e:
                logger.error("[%s] notify_session_action failed: %s", ch.name, e)

    def get_statuses(self) -> Dict[str, Dict[str, Any]]:
        return {ch.name: ch.status for ch in self._channels}

    def start_all(self) -> None:
        for ch in self._channels:
            try:
                ch.start()
                logger.info("Notification channel started: %s", ch.name)
            except Exception as e:
                logger.error("Failed to start channel %s: %s", ch.name, e)

    def stop_all(self) -> None:
        for ch in self._channels:
            try:
                ch.stop()
            except Exception as e:
                logger.error("Error stopping channel %s: %s", ch.name, e)
