#!/usr/bin/env python3
"""
Unit tests for Telegram bot integration
"""
import os
import sys
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import asyncio

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from agent.config import Config, TelegramConfig
from agent.telegram_bot import TelegramBot


def test_telegram_config_loading():
    """Test that Telegram config loads from YAML"""
    # Create a minimal config
    config_data = {
        "inbox_base": "/test",
        "subdirs": {},
        "output_dir": "/test",
        "telegram": {
            "enabled": True,
            "bot_token": "test_token",
            "authorized_users": ["12345"],
            "notify_on_session_ready": True
        }
    }

    # Mock YAML loading
    with patch("builtins.open"), patch("yaml.safe_load", return_value=config_data):
        config = Config.load("dummy.yaml")

        assert config.telegram.enabled == True
        assert config.telegram.bot_token == "test_token"
        assert config.telegram.authorized_users == ["12345"]
        assert config.telegram.notify_on_session_ready == True


def test_telegram_config_env_override():
    """Test that bot token can be overridden by environment variable"""
    config_data = {
        "inbox_base": "/test",
        "subdirs": {},
        "output_dir": "/test",
        "session_timeout_seconds": 300,
        "a4_page": {"width_pt": 595, "height_pt": 842},
        "margin_pt": 10,
        "gutter_pt": 18,
        "delete_inbox_files_after_process": True,
        "test_mode": False,
        "telegram": {
            "enabled": True,
            "bot_token": "yaml_token",
            "authorized_users": [],
            "notify_on_session_ready": True
        }
    }

    with patch("builtins.open"), patch("yaml.safe_load", return_value=config_data):
        with patch.dict(os.environ, {"SCAN_TELEGRAM_BOT_TOKEN": "env_token"}):
            config = Config.load("dummy.yaml")
            # Should use environment variable
            assert config.telegram.bot_token == "env_token"


def test_telegram_bot_from_config_disabled():
    """Test that TelegramBot.from_config returns None when disabled"""
    config = Config(
        inbox_base="/test",
        subdirs={},
        output_dir="/test",
        telegram=TelegramConfig(enabled=False)
    )

    bot = TelegramBot.from_config(config)
    assert bot is None


def test_telegram_bot_from_config_no_token():
    """Test that TelegramBot.from_config returns None when no token"""
    config = Config(
        inbox_base="/test",
        subdirs={},
        output_dir="/test",
        telegram=TelegramConfig(enabled=True, bot_token="")
    )

    bot = TelegramBot.from_config(config)
    assert bot is None


def test_telegram_bot_from_config_enabled():
    """Test that TelegramBot.from_config returns instance when enabled with token"""
    config = Config(
        inbox_base="/test",
        subdirs={},
        output_dir="/test",
        telegram=TelegramConfig(enabled=True, bot_token="test_token")
    )

    bot = TelegramBot.from_config(config)
    assert bot is not None
    assert bot.config.bot_token == "test_token"


def test_telegram_bot_is_authorized():
    """Test user authorization logic"""
    config = TelegramConfig(
        enabled=True,
        bot_token="test",
        authorized_users=["12345", "67890"]
    )
    bot = TelegramBot(config=config)

    # Authorized users
    assert bot.is_authorized(12345) == True
    assert bot.is_authorized(67890) == True

    # Unauthorized users
    assert bot.is_authorized(99999) == False

    # When no authorized users configured, everyone is authorized
    bot_no_auth = TelegramBot(config=TelegramConfig(enabled=True, bot_token="test"))
    assert bot_no_auth.is_authorized(12345) == True


def test_telegram_bot_register_chat():
    """Test chat registration"""
    config = TelegramConfig(enabled=True, bot_token="test")
    bot = TelegramBot(config=config)

    bot.register_chat(12345, 98765)
    assert bot._authorized_chats[12345] == 98765


def test_telegram_bot_update_session_info():
    """Test session info update"""
    config = TelegramConfig(enabled=True, bot_token="test")
    bot = TelegramBot(config=config)

    session_info = {
        "id": "test-session-1",
        "mode": "scan_document",
        "state": "WAIT_CONFIRM",
        "image_count": 5
    }

    bot.update_session_info(session_info)
    assert bot._latest_session_info == session_info


def test_telegram_bot_send_notification_when_stopped():
    """Test that send_notification does nothing when bot is stopped"""
    config = TelegramConfig(enabled=True, bot_token="test")
    bot = TelegramBot(config=config)
    # Bot is not running (_running = False)

    # Should not raise exception
    bot.send_notification("test message")


if __name__ == "__main__":
    # Run tests
    test_telegram_config_loading()
    print("✓ test_telegram_config_loading passed")

    test_telegram_config_env_override()
    print("✓ test_telegram_config_env_override passed")

    test_telegram_bot_from_config_disabled()
    print("✓ test_telegram_bot_from_config_disabled passed")

    test_telegram_bot_from_config_no_token()
    print("✓ test_telegram_bot_from_config_no_token passed")

    test_telegram_bot_from_config_enabled()
    print("✓ test_telegram_bot_from_config_enabled passed")

    test_telegram_bot_is_authorized()
    print("✓ test_telegram_bot_is_authorized passed")

    test_telegram_bot_register_chat()
    print("✓ test_telegram_bot_register_chat passed")

    test_telegram_bot_update_session_info()
    print("✓ test_telegram_bot_update_session_info passed")

    test_telegram_bot_send_notification_when_stopped()
    print("✓ test_telegram_bot_send_notification_when_stopped passed")

    print("\n🎉 All Telegram bot tests passed!")