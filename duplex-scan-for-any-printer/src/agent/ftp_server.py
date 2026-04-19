"""
Simple FTP server for receiving scanner uploads.
Built on pyftpdlib for lightweight operation.
"""

import os
import logging
from pyftpdlib.authorizers import DummyAuthorizer
from pyftpdlib.handlers import FTPHandler
from pyftpdlib.servers import FTPServer

# Only accept file types a scanner would produce
_ALLOWED_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".pdf", ".tiff", ".tif", ".bmp"})

# Disk space thresholds (MB)
_WARN_FREE_MB = 200   # Log a warning when free space drops below this
_REFUSE_FREE_MB = 50  # Delete the just-received file when free space is critically low


class ScannerFTPHandler(FTPHandler):
    """Custom FTP handler with logging, extension filtering, and disk guards."""

    def on_file_received(self, file):
        """Called when a file upload is completed."""
        # 1. Extension whitelist — reject anything a scanner wouldn't produce
        ext = os.path.splitext(file)[1].lower()
        if ext not in _ALLOWED_EXTENSIONS:
            logging.warning(
                f"FTP: Rejected file with disallowed extension '{ext}': {file}. "
                f"Allowed: {', '.join(sorted(_ALLOWED_EXTENSIONS))}"
            )
            try:
                os.remove(file)
            except OSError as e:
                logging.error(f"FTP: Failed to remove rejected file: {e}")
            return

        # 2. Disk space guard — act after upload so we always have a statvfs target
        try:
            stat = os.statvfs(file)
            free_mb = (stat.f_bavail * stat.f_frsize) / (1024 * 1024)
            if free_mb < _REFUSE_FREE_MB:
                logging.error(
                    f"FTP: Disk critically low ({free_mb:.0f} MB free). "
                    f"Deleting received file to prevent disk exhaustion: {file}"
                )
                try:
                    os.remove(file)
                except OSError as e:
                    logging.error(f"FTP: Failed to remove file during disk guard: {e}")
                return
            if free_mb < _WARN_FREE_MB:
                logging.warning(f"FTP: Low disk space — only {free_mb:.0f} MB free.")
        except OSError:
            pass  # statvfs not available (non-Linux); skip check

        logging.info(f"FTP file received: {file}")

    def on_incomplete_file_received(self, file):
        """Called when a file upload was interrupted. Remove the partial file."""
        logging.warning(f"FTP: Upload interrupted, removing partial file: {file}")
        try:
            os.remove(file)
        except OSError as e:
            logging.error(f"FTP: Failed to remove partial file: {e}")


def start_ftp_server(
    host: str = "0.0.0.0",
    port: int = 2121,
    directory: str = "/share/scan_inbox",
    username: str = None,
    password: str = None,
):
    """
    Start FTP server for scanner uploads.
    
    Args:
        host: Bind address (default: 0.0.0.0)
        port: FTP port (default: 2121)
        directory: Upload directory (default: /share/scan_inbox)
        username: FTP username (None = anonymous)
        password: FTP password (None = anonymous)
    """
    
    # Create authorizer
    authorizer = DummyAuthorizer()
    
    # Ensure directory exists
    os.makedirs(directory, exist_ok=True)
    
    if username and password:
        # Authenticated user
        authorizer.add_user(
            username=username,
            password=password,
            homedir=directory,
            perm="elradfmw"  # Full permissions
        )
        logging.info(f"FTP: Added user '{username}' with password")
    else:
        # Anonymous user — write-only (upload files, list dirs, change dir)
        # No read/delete/rename to prevent data exfiltration or destructive operations
        authorizer.add_anonymous(
            homedir=directory,
            perm="elw"  # e=change-dir, l=list, w=store(upload)
        )
        logging.warning(
            "FTP: Anonymous access with WRITE-ONLY permissions enabled. "
            "Set ftp.username and ftp.password in config to require authentication."
        )
        logging.info("FTP: Anonymous access enabled")
    
    # Create handler
    handler = ScannerFTPHandler
    handler.authorizer = authorizer
    
    # Passive ports (for PASV mode) — 3 ports is enough for home use
    handler.passive_ports = range(30000, 30003)

    # Disconnect idle clients — prevents resource exhaustion from stale connections
    handler.timeout = 30

    # Banner
    handler.banner = "Scan Agent FTP Server ready"
    
    # Create server
    server = FTPServer((host, port), handler)
    
    # Limits
    server.max_cons = 10
    server.max_cons_per_ip = 3
    
    logging.info(f"FTP server starting on {host}:{port}")
    logging.info(f"Upload directory: {directory}")
    
    # Start server (blocking)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logging.info("FTP server shutting down")
        server.close_all()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | FTP | %(levelname)s | %(message)s"
    )
    # Read credentials from environment (set by 00-prepare.sh in HAOS)
    _username = os.environ.get("FTP_USERNAME") or None
    _password = os.environ.get("FTP_PASSWORD") or None
    _directory = os.environ.get("FTP_DIRECTORY", "/share/scan_inbox")
    start_ftp_server(
        host="0.0.0.0",
        port=2121,
        directory=_directory,
        username=_username,
        password=_password,
    )
