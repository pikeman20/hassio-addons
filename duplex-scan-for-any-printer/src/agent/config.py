from __future__ import annotations

import os
import yaml
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class A4Page:
    width_pt: int = 595
    height_pt: int = 842


@dataclass
class PrinterConfig:
    enabled: bool = False
    name: str = ""
    ip: str = ""


@dataclass
class TelegramConfig:
    enabled: bool = False
    bot_token: str = ""
    authorized_users: List[int] = field(default_factory=list)
    notify_chat_ids: List[int] = field(default_factory=list)  # pre-configured chat IDs to always notify
    notify_on_session_ready: bool = True


@dataclass
class Config:
    inbox_base: str
    subdirs: Dict[str, str]
    output_dir: str
    session_timeout_seconds: int = 300
    a4_page: A4Page = field(default_factory=A4Page)
    printer: PrinterConfig = field(default_factory=PrinterConfig)
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    margin_pt: int = 10
    gutter_pt: int = 18
    delete_inbox_files_after_process: bool = True
    test_mode: bool = False

    @staticmethod
    def load(path: str) -> "Config":
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        a4 = raw.get("a4_page", {})
        printer_raw = raw.get("printer", {})
        telegram_raw = raw.get("telegram")
        cfg = Config(
            inbox_base=raw.get("inbox_base", "/scan_inbox"),
            subdirs=raw.get(
                "subdirs",
                {
                    "scan_duplex": "scan_duplex",
                    "copy_duplex": "copy_duplex",
                    "scan_document": "scan_document",
                    "card_2in1": "card_2in1",
                    "confirm": "confirm",
                    "confirm_print": "confirm_print",
                    "reject": "reject",
                    "test_print": "test_print",
                },
            ),
            output_dir=raw.get("output_dir", "/scan_out"),
            session_timeout_seconds=int(raw.get("session_timeout_seconds", 300)),
            a4_page=A4Page(
                width_pt=int(a4.get("width_pt", 595)),
                height_pt=int(a4.get("height_pt", 842)),
            ),
            printer=PrinterConfig(
                enabled=bool(printer_raw.get("enabled", False)),
                name=str(printer_raw.get("name", "")),
                ip=str(printer_raw.get("ip", "")),
            ),
            telegram=TelegramConfig(
                enabled=bool(telegram_raw.get("enabled", False)) if telegram_raw else False,
                bot_token=str(telegram_raw.get("bot_token", "")) if telegram_raw else "",
                authorized_users=[int(x) for x in (telegram_raw.get("authorized_users") or [])] if telegram_raw else [],
                notify_chat_ids=[int(x) for x in (telegram_raw.get("notify_chat_ids") or [])] if telegram_raw else [],
                notify_on_session_ready=bool(telegram_raw.get("notify_on_session_ready", True)) if telegram_raw else True,
            ),
            margin_pt=int(raw.get("margin_pt", 10)),
            gutter_pt=int(raw.get("gutter_pt", 18)),
            delete_inbox_files_after_process=bool(
                raw.get("delete_inbox_files_after_process", True)
            ),
            test_mode=bool(raw.get("test_mode", False)),
        )
        # Allow env overrides for base folders
        cfg.inbox_base = os.getenv("SCAN_INBOX_BASE", cfg.inbox_base)
        cfg.output_dir = os.getenv("SCAN_OUTPUT_DIR", cfg.output_dir)
        # Override bot token from environment if available
        cfg.telegram.bot_token = os.getenv("SCAN_TELEGRAM_BOT_TOKEN", cfg.telegram.bot_token)
        return cfg

    def path_for(self, key: str) -> str:
        """Absolute path for a subdir key."""
        name = self.subdirs.get(key, key)
        return os.path.join(self.inbox_base, name)
