"""
Test resource monitoring and cleanup.

Tests:
- Disk space checking
- Memory checking (if psutil available)
- Old file cleanup (with dry run)
- Temp file cleanup
- Directory size calculation
- Status reporting
"""

import sys
import os
import time
import tempfile
from pathlib import Path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from agent.resource_monitor import ResourceMonitor


def test_disk_space_check():
    """Test disk space monitoring."""
    print("\n" + "="*70)
    print("TEST: Disk Space Check")
    print("="*70)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        monitor = ResourceMonitor(
            output_dir=tmpdir,
            inbox_dir=tmpdir,
            min_disk_mb=100
        )
        
        is_sufficient, available_mb = monitor.check_disk_space()
        print(f"✅ Disk space: {available_mb:.1f}MB available")
        print(f"✅ Sufficient: {is_sufficient}")
        assert available_mb > 0


def test_memory_check():
    """Test memory monitoring."""
    print("\n" + "="*70)
    print("TEST: Memory Check")
    print("="*70)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        monitor = ResourceMonitor(
            output_dir=tmpdir,
            inbox_dir=tmpdir,
            min_memory_mb=100
        )
        
        is_sufficient, available_mb = monitor.check_memory()
        
        if available_mb > 0:
            print(f"✅ Memory: {available_mb:.1f}MB available")
            print(f"✅ Sufficient: {is_sufficient}")
        else:
            print("⚠️  psutil not installed, memory check skipped")


def test_old_file_cleanup():
    """Test old file cleanup with dry run."""
    print("\n" + "="*70)
    print("TEST: Old File Cleanup (Dry Run)")
    print("="*70)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir) / "output"
        inbox_dir = Path(tmpdir) / "inbox"
        output_dir.mkdir()
        inbox_dir.mkdir()
        
        # Create test files with different ages
        now = time.time()
        
        # Old file (10 days ago)
        old_pdf = output_dir / "old_session.pdf"
        old_pdf.write_text("old content")
        os.utime(old_pdf, (now - 10*24*3600, now - 10*24*3600))
        
        # Recent file (1 day ago)
        recent_pdf = output_dir / "recent_session.pdf"
        recent_pdf.write_text("recent content")
        os.utime(recent_pdf, (now - 1*24*3600, now - 1*24*3600))
        
        # Very recent file (1 hour ago)
        new_pdf = output_dir / "new_session.pdf"
        new_pdf.write_text("new content")
        
        monitor = ResourceMonitor(
            output_dir=str(output_dir),
            inbox_dir=str(inbox_dir),
            retention_days=7
        )
        
        # Dry run - should not delete anything
        print("\n📋 Dry run:")
        files_deleted, space_freed = monitor.cleanup_old_files(dry_run=True)
        print(f"✅ Would delete: {files_deleted} files")
        assert old_pdf.exists(), "Old file should still exist after dry run"
        assert recent_pdf.exists(), "Recent file should still exist"
        assert new_pdf.exists(), "New file should still exist"
        
        # Actual cleanup - should delete old file only
        print("\n📋 Actual cleanup:")
        files_deleted, space_freed = monitor.cleanup_old_files(dry_run=False)
        print(f"✅ Deleted: {files_deleted} files, freed {space_freed}MB")
        assert not old_pdf.exists(), "Old file should be deleted"
        assert recent_pdf.exists(), "Recent file should be kept"
        assert new_pdf.exists(), "New file should be kept"
        assert files_deleted == 1, f"Expected 1 file deleted, got {files_deleted}"


def test_temp_file_cleanup():
    """Test temp file cleanup."""
    print("\n" + "="*70)
    print("TEST: Temp File Cleanup")
    print("="*70)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir) / "output"
        output_dir.mkdir()
        
        # Create temp files
        temp1 = output_dir / "tmp_12345.pdf"
        temp2 = output_dir / "tmp_67890.jpg"
        regular = output_dir / "session.pdf"
        
        temp1.write_text("temp1")
        temp2.write_text("temp2")
        regular.write_text("regular")
        
        monitor = ResourceMonitor(
            output_dir=str(output_dir),
            inbox_dir=tmpdir
        )
        
        files_deleted = monitor.cleanup_temp_files(temp_pattern="tmp*")
        print(f"✅ Deleted {files_deleted} temp files")
        
        assert not temp1.exists(), "Temp file 1 should be deleted"
        assert not temp2.exists(), "Temp file 2 should be deleted"
        assert regular.exists(), "Regular file should be kept"
        assert files_deleted == 2


def test_directory_size():
    """Test directory size calculation."""
    print("\n" + "="*70)
    print("TEST: Directory Size Calculation")
    print("="*70)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir) / "output"
        output_dir.mkdir()
        
        # Create files with known sizes
        file1 = output_dir / "file1.pdf"
        file2 = output_dir / "file2.pdf"
        
        file1.write_text("A" * 1024)  # 1KB
        file2.write_text("B" * 2048)  # 2KB
        
        monitor = ResourceMonitor(
            output_dir=str(output_dir),
            inbox_dir=tmpdir
        )
        
        size_bytes = monitor.get_directory_size()
        size_kb = size_bytes / 1024
        
        print(f"✅ Directory size: {size_kb:.2f}KB ({size_bytes} bytes)")
        assert size_bytes == 3072, f"Expected 3072 bytes, got {size_bytes}"


def test_status_report():
    """Test status reporting."""
    print("\n" + "="*70)
    print("TEST: Status Report")
    print("="*70)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir) / "output"
        inbox_dir = Path(tmpdir) / "inbox"
        output_dir.mkdir()
        inbox_dir.mkdir()
        
        # Create some test files
        (output_dir / "test1.pdf").write_text("test1")
        (output_dir / "test2.pdf").write_text("test2")
        (inbox_dir / "scan1.jpg").write_text("scan1")
        
        monitor = ResourceMonitor(
            output_dir=str(output_dir),
            inbox_dir=str(inbox_dir),
            retention_days=7
        )
        
        status = monitor.report_status()
        
        print(f"✅ Disk available: {status['disk_available_mb']:.1f}MB")
        print(f"✅ PDF count: {status['pdf_count']}")
        print(f"✅ Scan files: {status['scan_files_count']}")
        print(f"✅ Output size: {status['output_size_mb']:.4f}MB")
        
        assert status['pdf_count'] == 2
        assert status['scan_files_count'] == 1
        assert status['retention_days'] == 7


if __name__ == "__main__":
    print("\n" + "🧪"*35)
    print("RESOURCE MONITORING & CLEANUP TEST SUITE")
    print("🧪"*35)
    
    test_disk_space_check()
    test_memory_check()
    test_old_file_cleanup()
    test_temp_file_cleanup()
    test_directory_size()
    test_status_report()
    
    print("\n" + "="*70)
    print("✅ ALL RESOURCE MONITORING TESTS PASSED!")
    print("="*70)
