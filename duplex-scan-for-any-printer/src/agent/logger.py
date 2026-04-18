"""
Production logging system for scan agent.

Simplified for Docker/HAOS deployment:
- Console-only output (Docker captures stdout/stderr)
- Structured logging with context (session_id, mode, timing)
- Multiple log levels (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- No file handlers (HAOS/Docker handles persistence)
"""

import logging
import sys
import time
from typing import Optional
from contextlib import contextmanager


class SessionContextFilter(logging.Filter):
    """Add session context to log records."""
    
    def __init__(self):
        super().__init__()
        self.session_id: Optional[str] = None
        self.mode: Optional[str] = None
    
    def filter(self, record: logging.LogRecord) -> bool:
        record.session_id = self.session_id or "-"
        record.mode = self.mode or "-"
        return True


class ScanAgentLogger:
    """Main logger for scan agent - console only for Docker."""
    
    def __init__(self, level: str = "INFO"):
        # Create main logger
        self.logger = logging.getLogger("scan_agent")
        self.logger.setLevel(getattr(logging, level.upper()))
        self.logger.handlers.clear()
        
        # Session context filter
        self.context_filter = SessionContextFilter()
        
        # Single formatter for console (structured, parseable)
        formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(session_id)s | %(mode)s | '
            '%(filename)s:%(lineno)d | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # Console handler only (Docker/HAOS captures this)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.DEBUG)
        console_handler.setFormatter(formatter)
        console_handler.addFilter(self.context_filter)
        self.logger.addHandler(console_handler)
        
        self.logger.info("Logging initialized (console-only for Docker/HAOS)")
    
    def set_session_context(self, session_id: Optional[str], mode: Optional[str]):
        """Set current session context for logging."""
        self.context_filter.session_id = session_id
        self.context_filter.mode = mode
    
    def clear_session_context(self):
        """Clear session context."""
        self.context_filter.session_id = None
        self.context_filter.mode = None
    
    @contextmanager
    def session_context(self, session_id: str, mode: str):
        """Context manager for session logging."""
        old_session = self.context_filter.session_id
        old_mode = self.context_filter.mode
        try:
            self.set_session_context(session_id, mode)
            yield
        finally:
            self.context_filter.session_id = old_session
            self.context_filter.mode = old_mode
    
    @contextmanager
    def timing(self, operation: str, level: int = logging.INFO):
        """Context manager to log operation timing."""
        start = time.time()
        try:
            yield
        finally:
            elapsed = time.time() - start
            self.logger.log(level, f"⏱️  {operation}: {elapsed:.3f}s")
    
    def debug(self, msg: str, **kwargs):
        """Log debug message."""
        self.logger.debug(msg, extra=kwargs)
    
    def info(self, msg: str, **kwargs):
        """Log info message."""
        self.logger.info(msg, extra=kwargs)
    
    def warning(self, msg: str, **kwargs):
        """Log warning message."""
        self.logger.warning(msg, extra=kwargs)
    
    def error(self, msg: str, exc_info: bool = False, **kwargs):
        """Log error message."""
        self.logger.error(msg, exc_info=exc_info, extra=kwargs)
    
    def critical(self, msg: str, exc_info: bool = True, **kwargs):
        """Log critical message."""
        self.logger.critical(msg, exc_info=exc_info, extra=kwargs)


# Global logger instance
_logger: Optional[ScanAgentLogger] = None


def init_logger(level: str = "INFO") -> ScanAgentLogger:
    """Initialize global logger (console-only for Docker)."""
    global _logger
    _logger = ScanAgentLogger(level)
    return _logger


def get_logger() -> ScanAgentLogger:
    """Get global logger instance."""
    global _logger
    if _logger is None:
        _logger = init_logger()
    return _logger


# Convenience functions
def set_session_context(session_id: Optional[str], mode: Optional[str]):
    """Set session context for all subsequent logs."""
    get_logger().set_session_context(session_id, mode)


def clear_session_context():
    """Clear session context."""
    get_logger().clear_session_context()


def debug(msg: str, **kwargs):
    """Log debug message."""
    get_logger().debug(msg, **kwargs)


def info(msg: str, **kwargs):
    """Log info message."""
    get_logger().info(msg, **kwargs)


def warning(msg: str, **kwargs):
    """Log warning message."""
    get_logger().warning(msg, **kwargs)


def error(msg: str, exc_info: bool = False, **kwargs):
    """Log error message."""
    get_logger().error(msg, exc_info=exc_info, **kwargs)


def critical(msg: str, exc_info: bool = True, **kwargs):
    """Log critical message."""
    get_logger().critical(msg, exc_info=exc_info, **kwargs)
