from __future__ import annotations

import platform
import subprocess
import socket
import os
import struct
from typing import List, Optional, Dict
from agent.error_handler import retry_on_failure, PrinterError


def discover_network_printer(ip: str, timeout: float = 2.0) -> Optional[Dict[str, str]]:
    """Discover printer at IP address using common ports.
    
    Args:
        ip: Printer IP address
        timeout: Connection timeout in seconds
    
    Returns:
        Dict with printer info if found, None otherwise
        Example: {'ip': '192.168.100.60', 'name': 'Brother MFC-7860DW', 'model': 'Brother MFC-7860DW', 'protocol': 'ipp'}
    """
    # Try IPP port 631 first (most common) and get printer info
    if _test_port(ip, 631, timeout):
        printer_info = get_printer_info_via_ipp(ip, timeout)
        if printer_info:
            result = {
                'ip': ip, 
                'protocol': 'ipp', 
                'port': 631,
                'name': printer_info.get('name', f'Network-{ip}'),
                'model': printer_info.get('model', 'Unknown'),
                'manufacturer': printer_info.get('manufacturer', 'Unknown')
            }
            return result
        else:
            # IPP port open but can't get info
            return {'ip': ip, 'name': f'Network-{ip}', 'protocol': 'ipp', 'port': 631}
    
    # Try RAW printing port 9100 (HP/Brother JetDirect)
    if _test_port(ip, 9100, timeout):
        return {'ip': ip, 'name': f'Network-{ip}', 'protocol': 'raw', 'port': 9100}
    
    # Try LPR port 515
    if _test_port(ip, 515, timeout):
        return {'ip': ip, 'name': f'Network-{ip}', 'protocol': 'lpr', 'port': 515}
    
    return None


def _test_port(ip: str, port: int, timeout: float) -> bool:
    """Test if port is open on IP address."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((ip, port))
        sock.close()
        return result == 0
    except Exception:
        return False


def get_printer_info_via_ipp(ip: str, timeout: float = 3.0) -> Optional[Dict[str, str]]:
    """Get printer information via IPP using CUPS lpinfo command.
    
    Args:
        ip: Printer IP address
        timeout: Connection timeout in seconds
    
    Returns:
        Dict with printer info: {'name': 'Brother MFC-7860DW', 'model': '...', 'manufacturer': 'Brother'}
        None if failed to query
    """
    try:
        # Use CUPS lpinfo to query network device
        # lpinfo -v shows available devices including network printers
        # Format: network socket://192.168.100.60
        result = subprocess.run(
            ["lpinfo", "-v", "--timeout", str(int(timeout))],
            capture_output=True,
            timeout=timeout + 2,
            text=True
        )
        
        if result.returncode == 0 and result.stdout:
            # Check if our IP is discovered
            if ip in result.stdout:
                # Found the printer, now try to get make-and-model using lpinfo -m
                # But first, let's use ipptool (standard CUPS tool) to query attributes
                pass
        
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
        pass
    
    # Try using CUPS ipptool to query IPP attributes directly
    try:
        # Create temporary IPP test file
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.test', delete=False) as f:
            f.write("""
{
    OPERATION Get-Printer-Attributes
    GROUP operation-attributes-tag
    ATTR charset attributes-charset utf-8
    ATTR language attributes-natural-language en-us
    ATTR uri printer-uri $uri
    ATTR keyword requested-attributes printer-make-and-model,printer-info,printer-name
}
""")
            test_file = f.name
        
        try:
            # Try both URIs - Brother printers work better with ipp://IP/ (no port/path)
            for uri in [f"ipp://{ip}/", f"ipp://{ip}:631/"]:
                result = subprocess.run(
                    ["ipptool", "-tv", uri, test_file],
                    capture_output=True,
                    timeout=timeout,
                    text=True
                )
                
                if result.returncode == 0 or "successful-ok" in result.stdout:
                    output = result.stdout
                    info = {}
                    
                    # Parse ipptool output format:
                    # printer-make-and-model (textWithoutLanguage) = Brother MFC-7860DW
                    # printer-info (textWithoutLanguage) = MFG:Brother;CMD:...
                    # printer-name (nameWithoutLanguage) = BRW00809289DA29
                    import re
                    
                    # Extract make-and-model
                    model_match = re.search(r'printer-make-and-model\s*\([^)]+\)\s*=\s*(.+?)(?:\n|$)', output)
                    if model_match:
                        model = model_match.group(1).strip()
                        info['model'] = model
                        
                        # Extract manufacturer from model
                        if 'Brother' in model:
                            info['manufacturer'] = 'Brother'
                        elif 'HP' in model or 'Hewlett' in model:
                            info['manufacturer'] = 'HP'
                        elif 'Canon' in model:
                            info['manufacturer'] = 'Canon'
                        elif 'Epson' in model:
                            info['manufacturer'] = 'Epson'
                        elif 'Samsung' in model:
                            info['manufacturer'] = 'Samsung'
                        elif 'Xerox' in model:
                            info['manufacturer'] = 'Xerox'
                    
                    # Extract printer name
                    name_match = re.search(r'printer-name\s*\([^)]+\)\s*=\s*(.+?)(?:\n|$)', output)
                    if name_match:
                        name = name_match.group(1).strip()
                        if name and 'unknown' not in name.lower():
                            info['name'] = name
                    
                    # If no name, use model as name
                    if 'model' in info and 'name' not in info:
                        info['name'] = info['model']
                    
                    # Parse printer-info for additional details
                    info_match = re.search(r'printer-info\s*\([^)]+\)\s*=\s*(.+?)(?:\n|$)', output)
                    if info_match:
                        printer_info_str = info_match.group(1).strip()
                        # Format: MFG:Brother;CMD:PJL,PCL,PCLXL;MDL:MFC-7860DW;CLS:PRINTER;...
                        if 'MDL:' in printer_info_str:
                            mdl_match = re.search(r'MDL:([^;]+)', printer_info_str)
                            if mdl_match and 'model' not in info:
                                info['model'] = mdl_match.group(1).strip()
                        if 'MFG:' in printer_info_str:
                            mfg_match = re.search(r'MFG:([^;]+)', printer_info_str)
                            if mfg_match and 'manufacturer' not in info:
                                info['manufacturer'] = mfg_match.group(1).strip()
                    
                    if info:
                        return info
                    break  # If we got response, don't try other URI
                    
        finally:
            # Clean up temp file
            try:
                import os
                os.unlink(test_file)
            except:
                pass
                
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
        pass
    
    return None


def get_available_printers() -> List[str]:
    """Get list of available CUPS printers.
    
    Returns:
        List of printer names, empty list if none found or error
    """
    if platform.system().lower() != "linux":
        return []
    
    try:
        result = subprocess.run(
            ["lpstat", "-p"],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0 and result.stdout.strip():
            # Parse output: "printer Canon_MF4410 is idle. enabled since ..."
            printers = []
            for line in result.stdout.strip().split('\n'):
                if line.startswith('printer '):
                    # Extract printer name between "printer " and next space
                    parts = line.split()
                    if len(parts) >= 2:
                        printers.append(parts[1])
            return printers
    except Exception:
        pass
    
    return []


def setup_network_printer(ip: str, name: str = None) -> Optional[str]:
    """Setup network printer in CUPS if not already configured.
    
    Args:
        ip: Printer IP address
        name: Optional printer name (default: Brother-{ip})
    
    Returns:
        Printer name if successful, None if failed
    """
    if platform.system().lower() != "linux":
        return None
    
    # Auto-detect protocol
    printer_info = discover_network_printer(ip)
    if not printer_info:
        print(f"⚠️  Cannot reach printer at {ip}")
        return None
    
    # Generate printer name
    if not name:
        name = f"Brother-{ip.replace('.', '-')}"
    
    # Check if already configured
    existing_printers = get_available_printers()
    if name in existing_printers:
        print(f"✅ Printer '{name}' already configured")
        return name
    
    # Add printer to CUPS
    protocol = printer_info['protocol']
    port = printer_info['port']
    
    try:
        if protocol == 'ipp':
            device_uri = f"ipp://{ip}:631/ipp/print"
        elif protocol == 'raw':
            device_uri = f"socket://{ip}:9100"
        else:
            device_uri = f"lpd://{ip}/queue"
        
        # Try Brother driver first, fallback to everywhere
        driver = "brother-MFC-7860DW-cups-en.ppd"  # Brother LPR driver PPD
        
        # Check if Brother driver available
        result = subprocess.run(
            ["lpinfo", "-m"],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if "MFC-7860DW" not in result.stdout and "MFC7860DW" not in result.stdout:
            # Fallback to driverless
            driver = "everywhere"
            print(f"ℹ️  Brother driver not found, using driverless mode")
        else:
            print(f"✅ Using Brother MFC-7860DW driver")
        
        # Add printer with lpadmin
        subprocess.run(
            ["lpadmin", "-p", name, "-E", "-v", device_uri, "-m", driver],
            check=True,
            capture_output=True,
            timeout=10
        )
        
        print(f"✅ Network printer '{name}' added successfully ({protocol}://{ip}:{port})")
        return name
    
    except subprocess.CalledProcessError as e:
        print(f"⚠️  Failed to add printer: {e.stderr.decode() if e.stderr else str(e)}")
        return None
    except Exception as e:
        print(f"⚠️  Error setting up printer: {e}")
        return None


@retry_on_failure(max_retries=2, delay=2.0, backoff=1.5, exceptions=(subprocess.CalledProcessError, PrinterError))
def print_pdf_duplex(path: str, printer_name: Optional[str] = None, printer_ip: Optional[str] = None):
    """Print a PDF using CUPS two-sided-long-edge with retry logic.
    
    Args:
        path: Path to PDF file
        printer_name: Specific printer name (if None, uses CUPS default)
    
    Raises:
        PrinterError: If printing fails after retries
    """
    if platform.system().lower() != "linux":
        print("⚠️  Printing only supported on Linux")
        return
    
    cmd = ["lp", "-o", "sides=two-sided-long-edge"]
    if printer_name:
        cmd.extend(["-d", printer_name])
    cmd.append(path)
    
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        raise PrinterError(
            f"CUPS lp command failed: {e}",
            pdf_path=path,
            printer_name=printer_name or "default",
            command=" ".join(cmd)
        )
    except Exception as e:
        raise PrinterError(
            f"Print dispatch failed: {e}",
            pdf_path=path,
            printer_name=printer_name or "default"
        )


@retry_on_failure(max_retries=2, delay=2.0, backoff=1.5, exceptions=(subprocess.CalledProcessError, PrinterError))
def print_pdf_monochrome(path: str, duplex: bool = False, printer_name: Optional[str] = None, printer_ip: Optional[str] = None):
    """Print a PDF in monochrome with retry logic.

    Uses CUPS `print-color-mode=monochrome`. If `duplex=True`, also sets
    `sides=two-sided-long-edge`.
    
    Args:
        path: Path to PDF file
        duplex: Enable duplex printing
        printer_name: Specific printer name (if None, uses CUPS default)
        printer_ip: Printer IP address (if set, auto-setup network printer)
    
    Raises:
        PrinterError: If printing fails after retries
    """
    if platform.system().lower() != "linux":
        print("⚠️  Printing only supported on Linux")
        return
    
    # Auto-setup network printer if IP provided
    if printer_ip and not printer_name:
        printer_name = setup_network_printer(printer_ip)
        if not printer_name:
            raise PrinterError(
                f"Failed to setup network printer at {printer_ip}",
                pdf_path=path,
                printer_name=printer_ip,
                duplex=duplex
            )
    
    cmd = ["lp", "-o", "print-color-mode=monochrome"]
    if duplex:
        cmd += ["-o", "sides=two-sided-long-edge"]
    if printer_name:
        cmd.extend(["-d", printer_name])
    cmd.append(path)
    
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        raise PrinterError(
            f"CUPS lp command failed: {e}",
            pdf_path=path,
            printer_name=printer_name or "default",
            command=" ".join(cmd),
            duplex=duplex
        )
    except Exception as e:
        raise PrinterError(
            f"Monochrome print failed: {e}",
            pdf_path=path,
            printer_name=printer_name or "default",
            duplex=duplex
        )

