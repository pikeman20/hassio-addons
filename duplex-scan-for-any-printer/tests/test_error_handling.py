"""
Test error handling and recovery mechanisms.

Tests:
- Retry logic with exponential backoff
- Safe execution with fallback values
- Error classification and severity
- Error handlers for different failure types
"""

import sys
import os
import time
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from agent.error_handler import (
    retry_on_failure, safe_execute, ErrorSeverity,
    ScanAgentError, ImageProcessingError, PDFGenerationError, PrinterError,
    handle_session_error, handle_image_processing_error
)


def test_retry_decorator():
    """Test retry decorator with exponential backoff."""
    print("\n" + "="*70)
    print("TEST: Retry Decorator")
    print("="*70)
    
    # Counter to track attempts
    attempts = {"count": 0}
    
    @retry_on_failure(max_retries=3, delay=0.1, backoff=2.0)
    def flaky_function():
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise ValueError(f"Attempt {attempts['count']} failed")
        return "Success!"
    
    start = time.time()
    result = flaky_function()
    elapsed = time.time() - start
    
    print(f"✅ Result: {result}")
    print(f"✅ Attempts: {attempts['count']}")
    print(f"✅ Elapsed: {elapsed:.2f}s (expected ~0.3s: 0.1s + 0.2s delays)")
    assert attempts["count"] == 3, f"Expected 3 attempts, got {attempts['count']}"
    assert result == "Success!", f"Expected 'Success!', got {result}"
    

def test_safe_execute():
    """Test safe execution with fallback values."""
    print("\n" + "="*70)
    print("TEST: Safe Execute")
    print("="*70)
    
    # Success case
    result = safe_execute(lambda x: x * 2, 5, default=0)
    print(f"✅ Success case: {result} (expected 10)")
    assert result == 10
    
    # Failure case with default
    def failing_func():
        raise ValueError("Intentional error")
    
    result = safe_execute(failing_func, default=42, error_msg="Test failure")
    print(f"✅ Failure case: {result} (expected default 42)")
    assert result == 42
    
    # Failure case with None default
    result = safe_execute(failing_func, default=None, log_errors=False)
    print(f"✅ Failure with None: {result} (expected None)")
    assert result is None


def test_error_classification():
    """Test error types and severity levels."""
    print("\n" + "="*70)
    print("TEST: Error Classification")
    print("="*70)
    
    # ImageProcessingError
    img_err = ImageProcessingError("Crop failed", filename="test.jpg", operation="crop")
    print(f"✅ ImageProcessingError: severity={img_err.severity.value}, recoverable={img_err.recoverable}")
    assert img_err.severity == ErrorSeverity.LOW
    assert img_err.recoverable == True
    assert img_err.context["filename"] == "test.jpg"
    
    # PDFGenerationError
    pdf_err = PDFGenerationError("PDF failed", session_id="s123", mode="scan_duplex")
    print(f"✅ PDFGenerationError: severity={pdf_err.severity.value}, recoverable={pdf_err.recoverable}")
    assert pdf_err.severity == ErrorSeverity.MEDIUM
    assert pdf_err.recoverable == False
    
    # PrinterError
    printer_err = PrinterError("CUPS failed", pdf_path="/tmp/test.pdf", printer_name="HP")
    print(f"✅ PrinterError: severity={printer_err.severity.value}, recoverable={printer_err.recoverable}")
    assert printer_err.severity == ErrorSeverity.MEDIUM
    assert printer_err.recoverable == True


def test_error_handlers():
    """Test error handling functions."""
    print("\n" + "="*70)
    print("TEST: Error Handlers")
    print("="*70)
    
    # Session error handler
    print("\n📋 Testing session error handler:")
    error = PDFGenerationError("PDF generation failed", session_id="s123", mode="scan_duplex")
    handle_session_error("s123", "scan_duplex", error)
    print("✅ Session error handler executed")
    
    # Image processing error handler
    print("\n📋 Testing image processing error handler:")
    error = ImageProcessingError("Crop failed", filename="test.jpg", operation="crop")
    handle_image_processing_error("test.jpg", "crop", error)
    print("✅ Image processing error handler executed")
    
    # Generic exception
    print("\n📋 Testing generic exception handler:")
    handle_session_error("s124", "scan_document", ValueError("Generic error"))
    print("✅ Generic exception handler executed")


def test_retry_exhaustion():
    """Test retry decorator when all retries are exhausted."""
    print("\n" + "="*70)
    print("TEST: Retry Exhaustion")
    print("="*70)
    
    attempts = {"count": 0}
    
    @retry_on_failure(max_retries=2, delay=0.05, backoff=2.0)
    def always_fails():
        attempts["count"] += 1
        raise ValueError(f"Attempt {attempts['count']} failed")
    
    try:
        always_fails()
        print("❌ Should have raised ValueError")
        assert False
    except ValueError as e:
        print(f"✅ Raised ValueError after {attempts['count']} attempts: {e}")
        assert attempts["count"] == 3  # Initial + 2 retries


if __name__ == "__main__":
    print("\n" + "🧪"*35)
    print("ERROR HANDLING & RECOVERY TEST SUITE")
    print("🧪"*35)
    
    test_retry_decorator()
    test_safe_execute()
    test_error_classification()
    test_error_handlers()
    test_retry_exhaustion()
    
    print("\n" + "="*70)
    print("✅ ALL ERROR HANDLING TESTS PASSED!")
    print("="*70)
