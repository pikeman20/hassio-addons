#!/usr/bin/env python3
"""
Integration tests for duplex scanning system workflows
Tests complete end-to-end scenarios (scan_duplex, copy_duplex, etc.)

For unit tests of individual functions, see the tests/ directory.
"""
import sys
from pathlib import Path
from typing import Callable, List, Tuple
import time

current_dir = Path(__file__).parent.resolve()
project_root = current_dir.parent if current_dir.name == "tests" else current_dir
sys.path.insert(0, str(project_root / "src"))
#Resolve imports for src files

from agent.config import Config
from agent.session_manager import Session
from main import process_session


class TestCase:
    """Represents a single test case"""
    def __init__(self, name: str, mode: str, description: str = ""):
        self.name = name
        self.mode = mode
        self.description = description
    
    def run(self, cfg: Config) -> Tuple[bool, str]:
        """
        Execute the test case.
        Returns: (success: bool, message: str)
        """
        # Find images in the corresponding folder
        scan_dir = Path("scan_inbox") / self.mode
        images = sorted(scan_dir.glob("*.jpg"))
        
        if not images:
            return False, f"No images found in {scan_dir}"
        
        print(f"\n{'='*90}")
        print(f"🧪 Test: {self.name}")
        if self.description:
            print(f"   {self.description}")
        print(f"   Mode: {self.mode}")
        print(f"   Images: {len(images)} files")
        print('='*90)
        
        # Create session
        session = Session(
            id=f"test_{self.mode}_{int(time.time())}",
            mode=self.mode,
            images=[str(p) for p in images]
        )
        
        # Process
        try:
            process_session(cfg, session)
            return True, f"✅ Test passed: {len(images)} images processed"
        except Exception as e:
            return False, f"❌ Test failed: {str(e)}"


class TestSuite:
    """Collection of test cases"""
    def __init__(self, name: str):
        self.name = name
        self.tests: List[TestCase] = []
    
    def add(self, test: TestCase):
        """Add a test case to the suite"""
        self.tests.append(test)
        return self
    
    def run_all(self, cfg: Config) -> Tuple[int, int]:
        """
        Run all tests in the suite.
        Returns: (passed_count, total_count)
        """
        print(f"\n{'#'*90}")
        print(f"📦 Test Suite: {self.name}")
        print(f"   Total tests: {len(self.tests)}")
        print('#'*90)
        
        passed = 0
        failed = 0
        results = []
        
        for test in self.tests:
            success, message = test.run(cfg)
            results.append((test.name, success, message))
            
            if success:
                passed += 1
                print(f"\n{message}\n")
            else:
                failed += 1
                print(f"\n{message}\n")
        
        # Summary
        print(f"\n{'#'*90}")
        print(f"📊 Test Summary: {self.name}")
        print(f"   ✅ Passed: {passed}/{len(self.tests)}")
        print(f"   ❌ Failed: {failed}/{len(self.tests)}")
        print('#'*90)
        
        # Detailed results
        if results:
            print("\n📋 Detailed Results:")
            for name, success, message in results:
                status = "✅ PASS" if success else "❌ FAIL"
                print(f"   {status} - {name}")
        
        return passed, len(self.tests)


def create_duplex_test_suite() -> TestSuite:
    """Create test suite for duplex scanning modes"""
    suite = TestSuite("Duplex Scanning Tests")
    
    suite.add(TestCase(
        name="Scan Duplex",
        mode="scan_duplex",
        description="Test duplex scanning with orientation detection and deskew"
    ))
    
    suite.add(TestCase(
        name="Copy Duplex",
        mode="copy_duplex",
        description="Test duplex copying with orientation detection and deskew (no print in test mode)"
    ))
    
    suite.add(TestCase(
        name="Card 2-in-1",
        mode="card_2in1",
        description="Test card 2-in-1 pairing with gutter spacing and labels"
    ))
    
    suite.add(TestCase(
        name="Scan Document",
        mode="scan_document",
        description="Test document scanning with auto-cropping and deskew"
    ))
    return suite


if __name__ == "__main__":
    # Load config
    cfg = Config.load("config.yaml")
    
    # Verify test mode
    if not cfg.test_mode:
        print("⚠️  WARNING: test_mode is not enabled in config.yaml")
        print("   Tests will delete files and may send jobs to printer!")
        response = input("   Continue anyway? (y/N): ")
        if response.lower() != 'y':
            print("Aborted.")
            sys.exit(1)
    
    # Create and run test suite
    suite = create_duplex_test_suite()
    passed, total = suite.run_all(cfg)
    
    # Exit with appropriate code
    sys.exit(0 if passed == total else 1)
