#!/usr/bin/env python3
"""
Plug-and-play orchestrator: starts scan agent + FTP + web UI.

Usage:
    python run.py              # Start everything
    python run.py --no-ftp     # Skip FTP server
    python run.py --no-web     # Skip web UI
    python run.py --setup      # Create config + dirs only
    python run.py --config X   # Use custom config
"""
from __future__ import annotations

import argparse
import os
import sys
import threading
from pathlib import Path

from src.orchestrator_utils import (
    check_port_available, create_default_config, install_service,
    log_event, print_banner, setup_log_dir,
    setup_orchestrator_log, setup_signal_handlers, spawn_child,
    stream_child_output, terminate_children, validate_prerequisites,
    _enable_ansi_windows,
)


def create_default_directories(config_path: str = None):
    """Create default directories based on config.yaml."""
    subdirs = {
        "scan_duplex": "scan_duplex", "copy_duplex": "copy_duplex",
        "scan_document": "scan_document", "card_2in1": "card_2in1",
        "confirm": "confirm", "confirm_print": "confirm_print",
        "reject": "reject", "test_print": "test_print"
    }
    inbox_base = "./scan_inbox"
    output_dir = "./scan_out"

    if config_path and Path(config_path).exists():
        try:
            import yaml
            with open(config_path, 'r') as f:
                cfg = yaml.safe_load(f)
            inbox_base = cfg.get('inbox_base', inbox_base)
            output_dir = cfg.get('output_dir', output_dir)
            subdirs = cfg.get('subdirs', subdirs)
        except Exception as e:
            print(f"Warning: Could not parse config: {e}, using defaults")

    for key in subdirs:
        Path(os.path.join(inbox_base, subdirs[key])).mkdir(parents=True, exist_ok=True)
    Path(output_dir).mkdir(parents=True, exist_ok=True)


def main():
    parser = argparse.ArgumentParser(description="Scan Agent Orchestrator")
    parser.add_argument('--no-ftp', action='store_true', help='Skip FTP server')
    parser.add_argument('--no-web', action='store_true', help='Skip web UI')
    parser.add_argument('--setup', action='store_true', help='Create config + dirs only')
    parser.add_argument('--config', type=str, default=None, help='Path to config file')
    parser.add_argument('--install-service', action='store_true', help='Install as systemd service')
    args = parser.parse_args()

    # Enable ANSI colors on Windows 10+
    _enable_ansi_windows()

    # Auto-config
    config_path = args.config or "config.local.yaml"
    if not Path(config_path).exists():
        config_path = create_default_config()
    create_default_directories(config_path)

    if args.setup:
        print("\nSetup complete! Edit config.local.yaml, then run: python run.py")
        return

    if args.install_service:
        install_service()
        return

    # Validate prerequisites and ports
    validate_prerequisites()
    if not args.no_ftp:
        check_port_available(2121, "FTP Server")
    if not args.no_web:
        check_port_available(8099, "Web UI")

    # Setup logging directory (for orchestrator log only)
    log_dir = setup_log_dir()
    orch_log = setup_orchestrator_log(log_dir)

    # Spawn children and prepare streaming
    children = []          # list of (name, proc, stdout_pipe)
    stream_threads = []    # list of threading.Thread for stdout streaming
    services = []          # list of (display_name, info) for banner

    # Scan agent (always runs)
    agent_cmd = [sys.executable, "-m", "src.main", "--config", config_path]
    name, proc, pipe = spawn_child("agent", agent_cmd)
    children.append((name, proc, pipe))
    if pipe:
        t = threading.Thread(target=stream_child_output, args=(name, pipe), daemon=True)
        t.start()
        stream_threads.append(t)
    services.append(("Scan Agent", f"watching {config_path}"))

    # FTP server (optional)
    if not args.no_ftp:
        ftp_cmd = [sys.executable, "-m", "src.agent.ftp_server"]
        name, proc, pipe = spawn_child("ftp", ftp_cmd)
        children.append((name, proc, pipe))
        if pipe:
            t = threading.Thread(target=stream_child_output, args=(name, pipe), daemon=True)
            t.start()
            stream_threads.append(t)
        services.append(("FTP Server", "ftp://0.0.0.0:2121"))

    # Web UI (optional)
    if not args.no_web:
        web_cmd = [sys.executable, "-m", "src.web_ui_server"]
        name, proc, pipe = spawn_child("web", web_cmd)
        children.append((name, proc, pipe))
        if pipe:
            t = threading.Thread(target=stream_child_output, args=(name, pipe), daemon=True)
            t.start()
            stream_threads.append(t)
        services.append(("Web UI", "http://localhost:8099 (browser)"))

    # Banner and signal handlers
    print_banner(services, config_path)
    log_event(orch_log, f"Started {len(children)} services")

    shutdown_event = threading.Event()
    setup_signal_handlers(shutdown_event)

    # Monitor loop
    exit_code = 0
    try:
        while not shutdown_event.is_set():
            for name, proc, _ in children:
                ret = proc.poll()
                if ret is not None:
                    log_event(orch_log, f"ERROR: {name} exited unexpectedly (code {ret})")
                    exit_code = 1
                    shutdown_event.set()
                    break
            shutdown_event.wait(timeout=1.0)
    except KeyboardInterrupt:
        pass

    # Shutdown
    log_event(orch_log, "Shutting down all services...")
    terminate_children(children, lambda msg: log_event(orch_log, msg))

    # Close orchestrator log
    orch_log.close()

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
