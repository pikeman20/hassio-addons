"""
Resource cleanup and monitoring for scan agent.

Features:
- Automatic cleanup of old/expired files
- Disk space monitoring and alerts
- Memory monitoring (optional)
- Temp file management
"""

import os
import time
import shutil
from pathlib import Path
from typing import List, Tuple, Optional
from datetime import datetime, timedelta

from agent import logger


class ResourceMonitor:
    """Monitor and manage system resources."""
    
    def __init__(self, 
                 output_dir: str,
                 inbox_dir: str,
                 retention_days: int = 7,
                 min_disk_mb: int = 500,
                 min_memory_mb: int = 500):
        """
        Initialize resource monitor.
        
        Args:
            output_dir: Output directory for PDFs
            inbox_dir: Inbox directory for scanned files
            retention_days: Keep files for this many days (default 7)
            min_disk_mb: Minimum disk space in MB (default 500)
            min_memory_mb: Minimum memory in MB (default 500)
        """
        self.output_dir = Path(output_dir)
        self.inbox_dir = Path(inbox_dir)
        self.retention_days = retention_days
        self.min_disk_mb = min_disk_mb
        self.min_memory_mb = min_memory_mb
    
    def check_disk_space(self, path: Optional[str] = None) -> Tuple[bool, float]:
        """
        Check disk space availability.
        
        Args:
            path: Path to check (default: output_dir)
        
        Returns:
            Tuple of (is_sufficient, available_mb)
        """
        check_path = path or self.output_dir
        try:
            stat = shutil.disk_usage(check_path)
            available_mb = stat.free / (1024 * 1024)
            is_sufficient = available_mb >= self.min_disk_mb
            
            if not is_sufficient:
                logger.warning(
                    f"⚠️  Low disk space: {available_mb:.1f}MB available "
                    f"(minimum: {self.min_disk_mb}MB) at {check_path}"
                )
            
            return is_sufficient, available_mb
        except Exception as e:
            logger.error(f"Failed to check disk space: {str(e)}", exc_info=True)
            return True, 0.0  # Assume OK if check fails
    
    def check_memory(self) -> Tuple[bool, float]:
        """
        Check memory availability (requires psutil).
        
        Returns:
            Tuple of (is_sufficient, available_mb)
        """
        try:
            import psutil
            
            mem = psutil.virtual_memory()
            available_mb = mem.available / (1024 * 1024)
            is_sufficient = available_mb >= self.min_memory_mb
            
            if not is_sufficient:
                logger.warning(
                    f"⚠️  Low memory: {available_mb:.1f}MB available "
                    f"(minimum: {self.min_memory_mb}MB)"
                )
            
            return is_sufficient, available_mb
        except ImportError:
            # psutil not installed, skip check
            return True, 0.0
        except Exception as e:
            logger.error(f"Failed to check memory: {str(e)}", exc_info=True)
            return True, 0.0
    
    def cleanup_old_files(self, dry_run: bool = False) -> Tuple[int, int]:
        """
        Clean up files older than retention period.
        
        Args:
            dry_run: If True, only report what would be deleted
        
        Returns:
            Tuple of (files_deleted, space_freed_mb)
        """
        cutoff_time = time.time() - (self.retention_days * 24 * 3600)
        files_deleted = 0
        space_freed = 0
        
        logger.info(f"🧹 Starting cleanup (retention: {self.retention_days} days, dry_run: {dry_run})")
        
        # Clean output directory (PDFs)
        try:
            for pdf_file in self.output_dir.glob("*.pdf"):
                try:
                    mtime = pdf_file.stat().st_mtime
                    if mtime < cutoff_time:
                        file_size = pdf_file.stat().st_size
                        age_days = (time.time() - mtime) / (24 * 3600)
                        
                        if dry_run:
                            logger.info(
                                f"  [DRY RUN] Would delete: {pdf_file.name} "
                                f"(age: {age_days:.1f} days, size: {file_size / 1024:.1f}KB)"
                            )
                        else:
                            pdf_file.unlink()
                            files_deleted += 1
                            space_freed += file_size
                            logger.debug(
                                f"  Deleted: {pdf_file.name} "
                                f"(age: {age_days:.1f} days, size: {file_size / 1024:.1f}KB)"
                            )
                except Exception as e:
                    logger.warning(f"  Failed to process {pdf_file.name}: {str(e)}")
        except Exception as e:
            logger.error(f"Failed to scan output directory: {str(e)}", exc_info=True)
        
        # Clean inbox directory (leftover scans - shouldn't happen normally)
        try:
            for scan_file in self.inbox_dir.rglob("*"):
                if not scan_file.is_file():
                    continue
                
                try:
                    mtime = scan_file.stat().st_mtime
                    if mtime < cutoff_time:
                        file_size = scan_file.stat().st_size
                        age_days = (time.time() - mtime) / (24 * 3600)
                        
                        if dry_run:
                            logger.info(
                                f"  [DRY RUN] Would delete: {scan_file.relative_to(self.inbox_dir)} "
                                f"(age: {age_days:.1f} days, size: {file_size / 1024:.1f}KB)"
                            )
                        else:
                            scan_file.unlink()
                            files_deleted += 1
                            space_freed += file_size
                            logger.debug(
                                f"  Deleted: {scan_file.relative_to(self.inbox_dir)} "
                                f"(age: {age_days:.1f} days, size: {file_size / 1024:.1f}KB)"
                            )
                except Exception as e:
                    logger.warning(f"  Failed to process {scan_file.name}: {str(e)}")
        except Exception as e:
            logger.error(f"Failed to scan inbox directory: {str(e)}", exc_info=True)
        
        space_freed_mb = space_freed / (1024 * 1024)
        
        if not dry_run and files_deleted > 0:
            logger.info(
                f"✅ Cleanup complete: {files_deleted} files deleted, "
                f"{space_freed_mb:.2f}MB freed"
            )
        elif dry_run:
            logger.info(
                f"✅ Dry run complete: {files_deleted} files would be deleted, "
                f"{space_freed_mb:.2f}MB would be freed"
            )
        else:
            logger.info("✅ Cleanup complete: No old files found")
        
        return files_deleted, int(space_freed_mb)
    
    def cleanup_temp_files(self, temp_pattern: str = "tmp*") -> int:
        """
        Clean up temporary files in output directory.
        
        Args:
            temp_pattern: Glob pattern for temp files
        
        Returns:
            Number of files deleted
        """
        files_deleted = 0
        
        try:
            for temp_file in self.output_dir.glob(temp_pattern):
                if temp_file.is_file():
                    try:
                        temp_file.unlink()
                        files_deleted += 1
                        logger.debug(f"  Deleted temp file: {temp_file.name}")
                    except Exception as e:
                        logger.warning(f"  Failed to delete {temp_file.name}: {str(e)}")
        except Exception as e:
            logger.error(f"Failed to clean temp files: {str(e)}", exc_info=True)
        
        if files_deleted > 0:
            logger.info(f"🧹 Cleaned up {files_deleted} temp files")
        
        return files_deleted
    
    def get_directory_size(self, path: Optional[Path] = None) -> int:
        """
        Calculate total size of directory.
        
        Args:
            path: Directory path (default: output_dir)
        
        Returns:
            Size in bytes
        """
        check_path = path or self.output_dir
        total_size = 0
        
        try:
            for item in check_path.rglob("*"):
                if item.is_file():
                    try:
                        total_size += item.stat().st_size
                    except Exception:
                        pass
        except Exception as e:
            logger.error(f"Failed to calculate directory size: {str(e)}", exc_info=True)
        
        return total_size
    
    def report_status(self) -> dict:
        """
        Generate status report.
        
        Returns:
            Dictionary with resource status
        """
        disk_ok, disk_mb = self.check_disk_space()
        mem_ok, mem_mb = self.check_memory()
        
        output_size = self.get_directory_size(self.output_dir)
        output_size_mb = output_size / (1024 * 1024)
        
        # Count files
        try:
            pdf_count = len(list(self.output_dir.glob("*.pdf")))
            scan_count = len(list(self.inbox_dir.rglob("*.*")))
        except Exception:
            pdf_count = 0
            scan_count = 0
        
        status = {
            "disk_available_mb": disk_mb,
            "disk_ok": disk_ok,
            "memory_available_mb": mem_mb,
            "memory_ok": mem_ok,
            "output_size_mb": output_size_mb,
            "pdf_count": pdf_count,
            "scan_files_count": scan_count,
            "retention_days": self.retention_days
        }
        
        logger.info("📊 Resource Status:")
        logger.info(f"  Disk: {disk_mb:.1f}MB available ({'✅' if disk_ok else '⚠️'})")
        if mem_mb > 0:
            logger.info(f"  Memory: {mem_mb:.1f}MB available ({'✅' if mem_ok else '⚠️'})")
        logger.info(f"  Output: {output_size_mb:.2f}MB ({pdf_count} PDFs)")
        logger.info(f"  Inbox: {scan_count} files")
        logger.info(f"  Retention: {self.retention_days} days")
        
        return status


def schedule_periodic_cleanup(monitor: ResourceMonitor, 
                              interval_hours: int = 24,
                              dry_run: bool = False):
    """
    Schedule periodic cleanup (call this in a background thread).
    
    Args:
        monitor: ResourceMonitor instance
        interval_hours: Hours between cleanups
        dry_run: If True, only report what would be deleted
    """
    import threading
    
    def _cleanup_loop():
        while True:
            try:
                logger.info(f"🕒 Scheduled cleanup starting (interval: {interval_hours}h)")
                monitor.cleanup_old_files(dry_run=dry_run)
                monitor.cleanup_temp_files()
                monitor.report_status()
            except Exception as e:
                logger.error(f"Scheduled cleanup failed: {str(e)}", exc_info=True)
            
            # Sleep until next cleanup
            time.sleep(interval_hours * 3600)
    
    thread = threading.Thread(target=_cleanup_loop, daemon=True)
    thread.start()
    logger.info(f"✅ Scheduled cleanup enabled (every {interval_hours}h, dry_run: {dry_run})")
    return thread
