"""
Error handling and recovery for scan agent.

Features:
- Graceful error handling with context
- Retry logic with exponential backoff
- Error notifications and logging
- Recovery strategies for common failures
"""

import time
import functools
from typing import Optional, Callable, Any, TypeVar, Dict
from enum import Enum

from agent import logger


class ErrorSeverity(Enum):
    """Error severity levels."""
    LOW = "low"           # Recoverable, retry automatically
    MEDIUM = "medium"     # Recoverable with user intervention
    HIGH = "high"         # Session failed, can continue service
    CRITICAL = "critical" # Service failure, requires restart


class ScanAgentError(Exception):
    """Base exception for scan agent errors."""
    
    def __init__(self, message: str, severity: ErrorSeverity = ErrorSeverity.MEDIUM, 
                 recoverable: bool = True, context: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.severity = severity
        self.recoverable = recoverable
        self.context = context or {}


class ImageProcessingError(ScanAgentError):
    """Error during image processing (load, rotate, crop, etc)."""
    
    def __init__(self, message: str, filename: str, operation: str, **context):
        super().__init__(
            message,
            severity=ErrorSeverity.LOW,
            recoverable=True,
            context={"filename": filename, "operation": operation, **context}
        )


class PDFGenerationError(ScanAgentError):
    """Error during PDF generation."""
    
    def __init__(self, message: str, session_id: str, mode: str, **context):
        super().__init__(
            message,
            severity=ErrorSeverity.MEDIUM,
            recoverable=False,
            context={"session_id": session_id, "mode": mode, **context}
        )


class PrinterError(ScanAgentError):
    """Error during printing."""
    
    def __init__(self, message: str, pdf_path: str, printer_name: str, **context):
        super().__init__(
            message,
            severity=ErrorSeverity.MEDIUM,
            recoverable=True,
            context={"pdf_path": pdf_path, "printer_name": printer_name, **context}
        )


class ConfigurationError(ScanAgentError):
    """Configuration validation error."""
    
    def __init__(self, message: str, config_key: str, **context):
        super().__init__(
            message,
            severity=ErrorSeverity.CRITICAL,
            recoverable=False,
            context={"config_key": config_key, **context}
        )


class ResourceError(ScanAgentError):
    """Resource availability error (disk space, memory, etc)."""
    
    def __init__(self, message: str, resource_type: str, **context):
        super().__init__(
            message,
            severity=ErrorSeverity.HIGH,
            recoverable=False,
            context={"resource_type": resource_type, **context}
        )


T = TypeVar('T')


def retry_on_failure(max_retries: int = 3, delay: float = 1.0, 
                     backoff: float = 2.0, exceptions: tuple = (Exception,)):
    """
    Retry decorator with exponential backoff.
    
    Args:
        max_retries: Maximum number of retry attempts
        delay: Initial delay between retries (seconds)
        backoff: Backoff multiplier (delay *= backoff after each retry)
        exceptions: Tuple of exceptions to catch and retry
    
    Example:
        @retry_on_failure(max_retries=3, delay=1.0, backoff=2.0)
        def risky_operation():
            # Will retry up to 3 times with delays: 1s, 2s, 4s
            ...
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            current_delay = delay
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    
                    if attempt < max_retries:
                        logger.warning(
                            f"🔄 {func.__name__} failed (attempt {attempt + 1}/{max_retries + 1}), "
                            f"retrying in {current_delay:.1f}s: {str(e)}"
                        )
                        time.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        logger.error(
                            f"❌ {func.__name__} failed after {max_retries + 1} attempts: {str(e)}",
                            exc_info=True
                        )
            
            # All retries exhausted
            raise last_exception
        
        return wrapper
    return decorator


def safe_execute(func: Callable[..., T], *args, 
                 default: Optional[T] = None,
                 error_msg: Optional[str] = None,
                 log_errors: bool = True,
                 **kwargs) -> Optional[T]:
    """
    Execute function safely with error handling.
    
    Args:
        func: Function to execute
        *args: Positional arguments for func
        default: Default value to return on error
        error_msg: Custom error message prefix
        log_errors: Whether to log errors
        **kwargs: Keyword arguments for func
    
    Returns:
        Function result or default value on error
    
    Example:
        result = safe_execute(load_image, path, default=None, error_msg="Failed to load")
    """
    try:
        return func(*args, **kwargs)
    except Exception as e:
        if log_errors:
            msg = f"{error_msg}: {str(e)}" if error_msg else f"Error in {func.__name__}: {str(e)}"
            logger.error(msg, exc_info=True)
        return default


def handle_session_error(session_id: str, mode: str, error: Exception) -> None:
    """
    Handle errors during session processing.
    
    Args:
        session_id: Session identifier
        mode: Processing mode
        error: Exception that occurred
    """
    if isinstance(error, ScanAgentError):
        severity = error.severity
        context = error.context
    else:
        severity = ErrorSeverity.MEDIUM
        context = {}
    
    # Log with appropriate severity
    if severity == ErrorSeverity.CRITICAL:
        logger.critical(
            f"💥 CRITICAL ERROR in session {session_id} (mode: {mode}): {str(error)}",
            exc_info=True
        )
    elif severity == ErrorSeverity.HIGH:
        logger.error(
            f"🚨 HIGH severity error in session {session_id} (mode: {mode}): {str(error)}",
            exc_info=True
        )
    elif severity == ErrorSeverity.MEDIUM:
        logger.error(
            f"⚠️  Error in session {session_id} (mode: {mode}): {str(error)}",
            exc_info=True
        )
    else:  # LOW
        logger.warning(
            f"⚠️  Recoverable error in session {session_id} (mode: {mode}): {str(error)}"
        )
    
    # Log context if available
    if context:
        logger.debug(f"Error context: {context}")


def handle_image_processing_error(filename: str, operation: str, error: Exception) -> None:
    """
    Handle errors during image processing.
    
    Args:
        filename: Image filename
        operation: Processing operation that failed
        error: Exception that occurred
    """
    logger.warning(
        f"⚠️  Image processing failed: {operation} on {filename}: {str(error)}"
    )
    logger.debug(f"Image processing error details", exc_info=True)


def handle_pdf_generation_error(session_id: str, mode: str, error: Exception) -> None:
    """
    Handle errors during PDF generation.
    
    Args:
        session_id: Session identifier
        mode: Processing mode
        error: Exception that occurred
    """
    logger.error(
        f"❌ PDF generation failed for session {session_id} (mode: {mode}): {str(error)}",
        exc_info=True
    )


def handle_printer_error(pdf_path: str, printer_name: str, error: Exception) -> None:
    """
    Handle errors during printing.
    
    Args:
        pdf_path: Path to PDF file
        printer_name: Printer name
        error: Exception that occurred
    """
    logger.error(
        f"🖨️  Printing failed: {pdf_path} to {printer_name}: {str(error)}",
        exc_info=True
    )
    logger.info(
        f"💡 PDF saved successfully, but printing failed. You can print manually: {pdf_path}"
    )


def check_disk_space(path: str, required_mb: int = 100) -> bool:
    """
    Check if sufficient disk space is available.
    
    Args:
        path: Path to check
        required_mb: Required space in MB
    
    Returns:
        True if sufficient space available
    
    Raises:
        ResourceError: If insufficient disk space
    """
    import shutil
    
    try:
        stat = shutil.disk_usage(path)
        available_mb = stat.free / (1024 * 1024)
        
        if available_mb < required_mb:
            raise ResourceError(
                f"Insufficient disk space: {available_mb:.1f}MB available, {required_mb}MB required",
                resource_type="disk_space",
                path=path,
                available_mb=available_mb,
                required_mb=required_mb
            )
        
        return True
    except ResourceError:
        raise
    except Exception as e:
        logger.warning(f"⚠️  Failed to check disk space: {str(e)}")
        return True  # Assume OK if check fails


def check_memory_available(required_mb: int = 500) -> bool:
    """
    Check if sufficient memory is available.
    
    Args:
        required_mb: Required memory in MB
    
    Returns:
        True if sufficient memory available
    """
    try:
        import psutil
        
        mem = psutil.virtual_memory()
        available_mb = mem.available / (1024 * 1024)
        
        if available_mb < required_mb:
            logger.warning(
                f"⚠️  Low memory: {available_mb:.1f}MB available, {required_mb}MB recommended"
            )
            return False
        
        return True
    except ImportError:
        # psutil not available, assume OK
        return True
    except Exception as e:
        logger.warning(f"⚠️  Failed to check memory: {str(e)}")
        return True
