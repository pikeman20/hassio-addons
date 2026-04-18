"""
Simple FTP server for receiving scanner uploads.
Built on pyftpdlib for lightweight operation.
"""

import os
import logging
from pyftpdlib.authorizers import DummyAuthorizer
from pyftpdlib.handlers import FTPHandler
from pyftpdlib.servers import FTPServer


class ScannerFTPHandler(FTPHandler):
    """Custom FTP handler with logging."""
    
    def on_file_received(self, file):
        """Called when a file upload is completed."""
        logging.info(f"FTP file received: {file}")
    
    def on_incomplete_file_received(self, file):
        """Called when a file upload was interrupted."""
        logging.warning(f"FTP incomplete file: {file}")


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
        # Anonymous user
        authorizer.add_anonymous(
            homedir=directory,
            perm="elradfmw"  # Full permissions for anonymous
        )
        logging.info("FTP: Anonymous access enabled")
    
    # Create handler
    handler = ScannerFTPHandler
    handler.authorizer = authorizer
    
    # Passive ports (for PASV mode) — 3 ports is enough for home use
    handler.passive_ports = range(30000, 30003)
    
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
