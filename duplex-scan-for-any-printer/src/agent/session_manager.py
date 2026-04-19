from __future__ import annotations

import os
import time
import threading
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Callable, Any, Any


STATE_COLLECTING = "COLLECTING"
STATE_WAIT_CONFIRM = "WAIT_CONFIRM"
STATE_CONFIRMED = "CONFIRMED"
STATE_REJECTED = "REJECTED"
STATE_SUSPENDED = "SUSPENDED"


@dataclass
class Session:
    id: str
    mode: str
    images: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=lambda: time.time())
    last_activity: float = field(default_factory=lambda: time.time())
    state: str = STATE_COLLECTING
    print_requested: bool = False  # True if confirm_print, False if confirm
    confirmer_chat_id: Optional[int] = None  # chat that confirmed, used to send back the PDF


class SessionManager:
    def __init__(
        self,
        timeout_seconds: int,
        on_confirm: Callable[[Session], None],
        on_reject: Callable[[Session], None],
        on_state_change: Optional[Callable[[Session, str, str], None]] = None,
        on_image_added: Optional[Callable[[Session], None]] = None,
    ):
        self.timeout_seconds = timeout_seconds
        self.on_confirm_cb = on_confirm
        self.on_reject_cb = on_reject
        self.on_state_change_cb = on_state_change
        self.on_image_added_cb = on_image_added
        self._by_mode: Dict[str, Session] = {}
        self._suspended_by_mode: Dict[str, Session] = {}
        self._lock = threading.Lock()
        self._start_timeout_watcher()

    def _start_timeout_watcher(self):
        def _watch():
            while True:
                time.sleep(2)
                now = time.time()
                with self._lock:
                    # Active sessions
                    for mode, s in list(self._by_mode.items()):
                        if s.state in (STATE_COLLECTING, STATE_WAIT_CONFIRM):
                            if now - s.last_activity > self.timeout_seconds:
                                s.state = STATE_REJECTED
                                self._cleanup_session_files(s)
                                self.on_reject_cb(s)
                                if self.on_state_change_cb:
                                    self.on_state_change_cb(s, STATE_WAIT_CONFIRM, STATE_REJECTED)
                                del self._by_mode[mode]
                    # Suspended sessions
                    for mode, s in list(self._suspended_by_mode.items()):
                        if s.state == STATE_SUSPENDED and now - s.last_activity > self.timeout_seconds:
                            s.state = STATE_REJECTED
                            self._cleanup_session_files(s)
                            self.on_reject_cb(s)
                            del self._suspended_by_mode[mode]
        t = threading.Thread(target=_watch, daemon=True)
        t.start()

    def add_image(self, mode: str, path: str):
        with self._lock:
            # Revive suspended session if returning to same mode
            s = self._by_mode.get(mode)
            if s is None:
                sus = self._suspended_by_mode.pop(mode, None)
                if sus is not None:
                    sus.state = STATE_COLLECTING
                    self._by_mode[mode] = sus
                    s = sus
            if s is None or s.state not in (STATE_COLLECTING, STATE_WAIT_CONFIRM):
                s = Session(id=f"{mode}-{int(time.time())}", mode=mode)
                self._by_mode[mode] = s

            # Suspend other active sessions to avoid accidental mixing
            for other_mode, other_s in list(self._by_mode.items()):
                if other_mode != mode and other_s.state in (STATE_COLLECTING, STATE_WAIT_CONFIRM):
                    other_s.state = STATE_SUSPENDED
                    self._suspended_by_mode[other_mode] = other_s
                    del self._by_mode[other_mode]

            s.images.append(path)
            s.last_activity = time.time()
            cb_session = s if self.on_image_added_cb else None
        # Call outside lock — timer is fast and non-blocking
        if cb_session and self.on_image_added_cb:
            self.on_image_added_cb(cb_session)

    def hint_wait_confirm(self, mode: str):
        with self._lock:
            s = self._by_mode.get(mode)
            if s and s.state == STATE_COLLECTING:
                old_state = s.state
                s.state = STATE_WAIT_CONFIRM
                if self.on_state_change_cb:
                    self.on_state_change_cb(s, old_state, STATE_WAIT_CONFIRM)

    def confirm_latest(self, print_requested: bool = False):
        with self._lock:
            s = self._latest_active_session()
            if s:
                old_state = s.state
                s.state = STATE_CONFIRMED
                s.print_requested = print_requested
                # copy ref; processing may be long
                self.on_confirm_cb(s)
                del self._by_mode[s.mode]
                # After processing, clear any suspended sessions/files to keep server light
                for mode, sus in list(self._suspended_by_mode.items()):
                    try:
                        self._cleanup_session_files(sus)
                    except Exception:
                        pass
                    del self._suspended_by_mode[mode]
                if self.on_state_change_cb:
                    self.on_state_change_cb(s, old_state, STATE_CONFIRMED)

    def reject_latest(self):
        with self._lock:
            s = self._latest_active_session()
            if s:
                old_state = s.state
                s.state = STATE_REJECTED
                self._cleanup_session_files(s)
                self.on_reject_cb(s)
                del self._by_mode[s.mode]
                if self.on_state_change_cb:
                    self.on_state_change_cb(s, old_state, STATE_REJECTED)

    def _latest_active_session(self) -> Optional[Session]:
        latest: Optional[Session] = None
        for s in self._by_mode.values():
            if s.state in (STATE_COLLECTING, STATE_WAIT_CONFIRM):
                if latest is None or s.last_activity > latest.last_activity:
                    latest = s
        return latest

    def _cleanup_session_files(self, s: Session):
        """Best-effort cleanup of session files with logging."""
        deleted_count = 0
        failed_count = 0
        
        for p in s.images:
            try:
                if os.path.exists(p):
                    os.remove(p)
                    deleted_count += 1
            except Exception as e:
                failed_count += 1
                print(f"[SessionManager] ⚠️  Failed to delete {os.path.basename(p)}: {str(e)}")
        
        if deleted_count > 0:
            print(f"[SessionManager] 🗑️  Cleaned up {deleted_count} rejected/timeout files")
        if failed_count > 0:
            print(f"[SessionManager] ⚠️  Failed to delete {failed_count} files")
