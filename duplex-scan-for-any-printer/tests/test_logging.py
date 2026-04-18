"""
Quick test for production logging system.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from agent.logger import init_logger, get_logger
import time

def test_basic_logging():
    """Test basic logging functionality."""
    print("Testing production logging system...")
    print("-" * 80)
    
    # Initialize logger
    log = init_logger(log_dir="logs_test", console_colors=True)
    
    # Test different log levels
    log.debug("This is a DEBUG message")
    log.info("This is an INFO message")
    log.warning("This is a WARNING message")
    log.error("This is an ERROR message")
    
    # Test session context
    print("\nTesting session context...")
    with log.session_context("test-session-001", "scan_duplex"):
        log.info("Processing with session context")
        log.debug("Debug message with context")
    
    # Test timing
    print("\nTesting timing utility...")
    with log.timing("Test operation"):
        time.sleep(0.1)
    
    # Test session events
    print("\nTesting session event logging...")
    log.log_session_event("CREATED", "sess-123", "scan_document", images=5)
    log.log_session_event("CONFIRMED", "sess-123", "scan_document", pages=2)
    
    # Test image processing log
    print("\nTesting image processing logging...")
    log.log_image_processing(
        "test_001.jpg",
        "ORIENTATION",
        "rotate_180",
        confidence=0.85,
        method="edge_based"
    )
    
    # Test performance logging
    print("\nTesting performance logging...")
    log.log_performance("PDF generation", 2.5, count=10)
    
    print("\n" + "=" * 80)
    print("✅ Logging test completed!")
    print(f"Check log files in: logs_test/")
    print("  - scan_agent.log  (INFO and above)")
    print("  - errors.log      (WARNING and above)")
    print("  - debug.log       (all messages)")
    print("=" * 80)

if __name__ == "__main__":
    test_basic_logging()
