"""
Configuration validation for scan agent.

Features:
- Validate config.yaml structure and required fields
- Check directory permissions and accessibility
- Verify CUPS printer availability (Linux only)
- Validate checkpoint files for image processing models
- Pre-flight checks before starting agent
"""

import os
import platform
import subprocess
from pathlib import Path
from typing import List, Tuple, Optional

from agent import logger
from agent.error_handler import ConfigurationError


class ConfigValidator:
    """Validate configuration and system requirements."""
    
    def __init__(self, config):
        """
        Initialize validator with config object.
        
        Args:
            config: Config instance to validate
        """
        self.config = config
        self.errors: List[str] = []
        self.warnings: List[str] = []
    
    def validate_all(self) -> bool:
        """
        Run all validation checks.
        
        Returns:
            True if all checks pass, False if any errors
        """
        logger.info("🔍 Running configuration validation...")
        
        self.validate_directories()
        self.validate_permissions()
        self.validate_checkpoint_files()
        self.validate_cups_availability()
        
        # Report results
        if self.errors:
            logger.error("❌ Configuration validation FAILED:")
            for error in self.errors:
                logger.error(f"  • {error}")
            return False
        
        if self.warnings:
            logger.warning("⚠️  Configuration warnings:")
            for warning in self.warnings:
                logger.warning(f"  • {warning}")
        
        logger.info("✅ Configuration validation PASSED")
        return True
    
    def validate_directories(self):
        """Validate that required directories exist or can be created."""
        logger.info("📁 Checking directories...")
        
        # Check inbox base
        inbox_path = Path(self.config.inbox_base)
        if not inbox_path.exists():
            try:
                inbox_path.mkdir(parents=True, exist_ok=True)
                logger.info(f"  Created inbox directory: {inbox_path}")
            except Exception as e:
                self.errors.append(
                    f"Cannot create inbox directory {inbox_path}: {str(e)}"
                )
        elif not inbox_path.is_dir():
            self.errors.append(
                f"Inbox path exists but is not a directory: {inbox_path}"
            )
        else:
            logger.info(f"  ✓ Inbox directory exists: {inbox_path}")
        
        # Check all subdirectories
        for key, subdir in self.config.subdirs.items():
            subdir_path = Path(self.config.inbox_base) / subdir
            if not subdir_path.exists():
                try:
                    subdir_path.mkdir(parents=True, exist_ok=True)
                    logger.info(f"  Created subdirectory: {key} -> {subdir_path}")
                except Exception as e:
                    self.errors.append(
                        f"Cannot create subdirectory {key} ({subdir_path}): {str(e)}"
                    )
            else:
                logger.debug(f"  ✓ Subdirectory exists: {key} -> {subdir_path}")
        
        # Check output directory
        output_path = Path(self.config.output_dir)
        if not output_path.exists():
            try:
                output_path.mkdir(parents=True, exist_ok=True)
                logger.info(f"  Created output directory: {output_path}")
            except Exception as e:
                self.errors.append(
                    f"Cannot create output directory {output_path}: {str(e)}"
                )
        elif not output_path.is_dir():
            self.errors.append(
                f"Output path exists but is not a directory: {output_path}"
            )
        else:
            logger.info(f"  ✓ Output directory exists: {output_path}")
    
    def validate_permissions(self):
        """Validate read/write permissions on directories."""
        logger.info("🔐 Checking permissions...")
        
        # Check inbox write permission (FTP server needs to write)
        inbox_path = Path(self.config.inbox_base)
        if inbox_path.exists():
            if not os.access(inbox_path, os.W_OK):
                self.errors.append(
                    f"No write permission for inbox directory: {inbox_path}"
                )
            else:
                logger.info(f"  ✓ Inbox writable: {inbox_path}")
        
        # Check output write permission (PDF generation)
        output_path = Path(self.config.output_dir)
        if output_path.exists():
            if not os.access(output_path, os.W_OK):
                self.errors.append(
                    f"No write permission for output directory: {output_path}"
                )
            else:
                logger.info(f"  ✓ Output writable: {output_path}")
        
        # Check subdirectories read permission
        for key, subdir in self.config.subdirs.items():
            subdir_path = Path(self.config.inbox_base) / subdir
            if subdir_path.exists():
                if not os.access(subdir_path, os.R_OK):
                    self.errors.append(
                        f"No read permission for subdirectory {key}: {subdir_path}"
                    )
    
    def validate_checkpoint_files(self):
        """Validate that model checkpoint files exist."""
        logger.info("🧠 Checking model checkpoints...")
        
        checkpoint_dir = Path("checkpoints")
        required_files = [
            "depth_anything_v2_vits_slim.onnx",
            "focus_matting_1.0.0.onnx",
            "focus_refiner_1.0.0.onnx",
            "isnet.onnx"
        ]
        
        if not checkpoint_dir.exists():
            self.errors.append(
                f"Checkpoint directory not found: {checkpoint_dir.absolute()}"
            )
            return
        
        for filename in required_files:
            filepath = checkpoint_dir / filename
            if not filepath.exists():
                self.errors.append(
                    f"Model checkpoint missing: {filename} (expected at {filepath.absolute()})"
                )
            else:
                # Check file size (should be > 1MB for ONNX models)
                size_mb = filepath.stat().st_size / (1024 * 1024)
                if size_mb < 1:
                    self.warnings.append(
                        f"Model checkpoint suspiciously small: {filename} ({size_mb:.2f}MB)"
                    )
                else:
                    logger.info(f"  ✓ Checkpoint found: {filename} ({size_mb:.1f}MB)")
    
    def validate_cups_availability(self):
        """Validate CUPS printing availability (Linux only)."""
        if platform.system().lower() != "linux":
            logger.info("🖨️  Skipping CUPS check (not Linux)")
            return
        
        logger.info("🖨️  Checking CUPS availability...")
        
        # Check if 'lp' command exists
        try:
            result = subprocess.run(
                ["which", "lp"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode != 0:
                self.warnings.append(
                    "CUPS 'lp' command not found. Printing will not work. "
                    "Install CUPS: sudo apt-get install cups"
                )
                return
            
            logger.info(f"  ✓ CUPS 'lp' command found: {result.stdout.strip()}")
        except subprocess.TimeoutExpired:
            self.warnings.append("CUPS check timed out")
            return
        except Exception as e:
            self.warnings.append(f"Failed to check CUPS availability: {str(e)}")
            return
        
        # Check if CUPS daemon is running
        try:
            result = subprocess.run(
                ["systemctl", "is-active", "cups"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                logger.info("  ✓ CUPS daemon is active")
            else:
                self.warnings.append(
                    "CUPS daemon not running. Start with: sudo systemctl start cups"
                )
        except subprocess.TimeoutExpired:
            self.warnings.append("CUPS daemon check timed out")
        except FileNotFoundError:
            # systemctl not available (maybe not systemd)
            logger.info("  ⚠️  systemctl not found, skipping daemon check")
        except Exception as e:
            self.warnings.append(f"Failed to check CUPS daemon: {str(e)}")
        
        # List available printers
        printers_list = []
        try:
            result = subprocess.run(
                ["lpstat", "-p"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                printers = result.stdout.strip().split('\n')
                if printers and printers[0]:
                    # Parse printer names
                    for line in printers:
                        if line.startswith('printer '):
                            parts = line.split()
                            if len(parts) >= 2:
                                printers_list.append(parts[1])
                    
                    logger.info(f"  ✓ Found {len(printers_list)} printer(s):")
                    for printer in printers_list[:3]:  # Show max 3
                        logger.info(f"    - {printer}")
                    
                    # Check if configured printer exists
                    if hasattr(self.config, 'printer') and self.config.printer.enabled:
                        configured_printer = self.config.printer.name.strip() if self.config.printer.name else ""
                        configured_ip = self.config.printer.ip.strip() if hasattr(self.config.printer, 'ip') and self.config.printer.ip else ""
                        
                        if configured_ip:
                            # Network printer mode - try to discover
                            logger.info(f"  🔍 Checking network printer at {configured_ip}...")
                            from agent.print_dispatcher import discover_network_printer
                            printer_info = discover_network_printer(configured_ip, timeout=3.0)
                            if printer_info:
                                logger.info(f"  ✓ Network printer found: {printer_info['protocol']}://{configured_ip}:{printer_info['port']}")
                            else:
                                logger.info(f"  ℹ️  Cannot reach printer at {configured_ip} (may be Docker network limitation)")
                                logger.info(f"  ℹ️  Printer will be auto-setup on first print attempt")
                        elif configured_printer:
                            if configured_printer not in printers_list:
                                self.warnings.append(
                                    f"Configured printer '{configured_printer}' not found. "
                                    f"Available: {', '.join(printers_list)}"
                                )
                            else:
                                logger.info(f"  ✓ Configured printer '{configured_printer}' is available")
                        else:
                            logger.info(f"  ℹ️  No specific printer configured, will use CUPS default")
                else:
                    logger.info(f"  ℹ️  No CUPS printers configured")
                    # Check if network printer IP is set
                    if hasattr(self.config, 'printer') and self.config.printer.enabled:
                        configured_ip = self.config.printer.ip.strip() if hasattr(self.config.printer, 'ip') and self.config.printer.ip else ""
                        if configured_ip:
                            # Try to discover and validate printer
                            from agent.print_dispatcher import discover_network_printer
                            printer_info = discover_network_printer(configured_ip, timeout=3.0)
                            if printer_info:
                                model = printer_info.get('model', 'Unknown')
                                manufacturer = printer_info.get('manufacturer', 'Unknown')
                                protocol = printer_info.get('protocol', 'unknown')
                                logger.info(f"  ✓ Found printer at {configured_ip}: {model} ({manufacturer}, {protocol})")
                                logger.info(f"  🔍 Will auto-setup on first print")
                            else:
                                # Cannot reach printer - this is OK in Docker Desktop
                                logger.info(f"  ℹ️  Cannot reach printer at {configured_ip} (may be Docker network limitation)")
                        else:
                            self.warnings.append(
                                "No printers configured in CUPS and no IP address set. "
                                "Add printer with: sudo lpadmin -p <name> -E -v <device> "
                                "OR set printer IP in addon config"
                            )
            else:
                logger.info(f"  ℹ️  CUPS lpstat unavailable (Docker mode)")
                # In Docker, CUPS may not be fully initialized yet
                if hasattr(self.config, 'printer') and self.config.printer.enabled:
                    configured_ip = self.config.printer.ip.strip() if hasattr(self.config.printer, 'ip') and self.config.printer.ip else ""
                    if configured_ip:
                        # Try to discover and validate printer
                        from agent.print_dispatcher import discover_network_printer
                        printer_info = discover_network_printer(configured_ip, timeout=3.0)
                        if printer_info:
                            model = printer_info.get('model', 'Unknown')
                            manufacturer = printer_info.get('manufacturer', 'Unknown')
                            protocol = printer_info.get('protocol', 'unknown')
                            logger.info(f"  ✓ Found printer at {configured_ip}: {model} ({manufacturer}, {protocol})")
                            logger.info(f"  🔍 Will auto-setup on first print")
                        else:
                            # Cannot reach printer - this is OK in Docker Desktop
                            logger.info(f"  ℹ️  Cannot reach printer at {configured_ip} (may be Docker network limitation)")
                    else:
                        logger.info(f"  ⚠️  Printer enabled but no IP set - printing may fail")
        except subprocess.TimeoutExpired:
            self.warnings.append("Printer listing timed out")
        except FileNotFoundError:
            logger.info(f"  ℹ️  'lpstat' command not found (Docker mode)")
            # In Docker without full CUPS, network printer via IP is the way
            if hasattr(self.config, 'printer') and self.config.printer.enabled:
                configured_ip = self.config.printer.ip.strip() if hasattr(self.config.printer, 'ip') and self.config.printer.ip else ""
                if configured_ip:
                    # Try to discover and validate printer
                    from agent.print_dispatcher import discover_network_printer
                    printer_info = discover_network_printer(configured_ip, timeout=3.0)
                    if printer_info:
                        model = printer_info.get('model', 'Unknown')
                        manufacturer = printer_info.get('manufacturer', 'Unknown')
                        protocol = printer_info.get('protocol', 'unknown')
                        logger.info(f"  ✓ Found printer at {configured_ip}: {model} ({manufacturer}, {protocol})")
                    else:
                        logger.info(f"  ℹ️  Cannot reach printer at {configured_ip}")
        except Exception as e:
            self.warnings.append(f"Failed to list printers: {str(e)}")


def validate_config(config) -> bool:
    """
    Validate configuration and system requirements.
    
    Args:
        config: Config instance
    
    Returns:
        True if validation passes, False otherwise
    
    Raises:
        ConfigurationError: If critical validation fails
    """
    validator = ConfigValidator(config)
    passed = validator.validate_all()
    
    if not passed:
        raise ConfigurationError(
            "Configuration validation failed. See logs for details.",
            config_key="all",
            errors=validator.errors
        )
    
    return True
