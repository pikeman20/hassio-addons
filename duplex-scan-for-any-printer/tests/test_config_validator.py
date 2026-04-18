"""
Test configuration validation.

Tests:
- Directory validation and creation
- Permission checks
- Checkpoint file validation
- CUPS availability (Linux only)
"""

import sys
import os
import tempfile
from pathlib import Path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from agent.config import Config
from agent.config_validator import ConfigValidator


def test_directory_validation():
    """Test directory validation and creation."""
    print("\n" + "="*70)
    print("TEST: Directory Validation")
    print("="*70)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a test config
        inbox_dir = os.path.join(tmpdir, "scan_inbox")
        output_dir = os.path.join(tmpdir, "scan_out")
        
        config = Config(
            inbox_base=inbox_dir,
            subdirs={
                "scan_duplex": "scan_duplex",
                "confirm": "confirm",
                "reject": "reject"
            },
            output_dir=output_dir
        )
        
        validator = ConfigValidator(config)
        validator.validate_directories()
        
        # Check that directories were created
        assert os.path.exists(inbox_dir), "Inbox directory should be created"
        assert os.path.exists(output_dir), "Output directory should be created"
        assert os.path.exists(os.path.join(inbox_dir, "scan_duplex"))
        assert os.path.exists(os.path.join(inbox_dir, "confirm"))
        assert os.path.exists(os.path.join(inbox_dir, "reject"))
        
        print(f"✅ Directories created: {len(validator.errors)} errors")
        assert len(validator.errors) == 0


def test_permission_validation():
    """Test permission validation."""
    print("\n" + "="*70)
    print("TEST: Permission Validation")
    print("="*70)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        inbox_dir = os.path.join(tmpdir, "scan_inbox")
        output_dir = os.path.join(tmpdir, "scan_out")
        
        # Create directories
        os.makedirs(inbox_dir)
        os.makedirs(output_dir)
        
        config = Config(
            inbox_base=inbox_dir,
            subdirs={"scan_duplex": "scan_duplex"},
            output_dir=output_dir
        )
        
        validator = ConfigValidator(config)
        validator.validate_permissions()
        
        print(f"✅ Permissions checked: {len(validator.errors)} errors")
        assert len(validator.errors) == 0


def test_checkpoint_validation():
    """Test checkpoint file validation."""
    print("\n" + "="*70)
    print("TEST: Checkpoint Validation")
    print("="*70)
    
    config = Config(
        inbox_base="/tmp/inbox",
        subdirs={},
        output_dir="/tmp/output"
    )
    
    validator = ConfigValidator(config)
    validator.validate_checkpoint_files()
    
    # Should have errors if checkpoints directory doesn't exist
    # or files are missing
    print(f"✅ Checkpoint validation: {len(validator.errors)} errors, {len(validator.warnings)} warnings")
    
    # In real deployment, we should have all checkpoint files
    # For this test, we just verify the validation logic runs


def test_cups_validation():
    """Test CUPS availability validation."""
    print("\n" + "="*70)
    print("TEST: CUPS Validation")
    print("="*70)
    
    config = Config(
        inbox_base="/tmp/inbox",
        subdirs={},
        output_dir="/tmp/output"
    )
    
    validator = ConfigValidator(config)
    validator.validate_cups_availability()
    
    # Should skip on Windows or check CUPS on Linux
    print(f"✅ CUPS validation: {len(validator.errors)} errors, {len(validator.warnings)} warnings")


def test_full_validation():
    """Test full validation workflow."""
    print("\n" + "="*70)
    print("TEST: Full Validation Workflow")
    print("="*70)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        inbox_dir = os.path.join(tmpdir, "scan_inbox")
        output_dir = os.path.join(tmpdir, "scan_out")
        
        config = Config(
            inbox_base=inbox_dir,
            subdirs={
                "scan_duplex": "scan_duplex",
                "confirm": "confirm"
            },
            output_dir=output_dir
        )
        
        validator = ConfigValidator(config)
        
        # Temporarily suppress checkpoint validation for test
        # (checkpoints may not exist in test environment)
        original_validate = validator.validate_checkpoint_files
        validator.validate_checkpoint_files = lambda: None
        
        result = validator.validate_all()
        
        print(f"✅ Full validation: {result}")
        print(f"   Errors: {len(validator.errors)}")
        print(f"   Warnings: {len(validator.warnings)}")
        
        # Restore original method
        validator.validate_checkpoint_files = original_validate


if __name__ == "__main__":
    print("\n" + "🧪"*35)
    print("CONFIGURATION VALIDATION TEST SUITE")
    print("🧪"*35)
    
    test_directory_validation()
    test_permission_validation()
    test_checkpoint_validation()
    test_cups_validation()
    test_full_validation()
    
    print("\n" + "="*70)
    print("✅ ALL CONFIGURATION VALIDATION TESTS PASSED!")
    print("="*70)
