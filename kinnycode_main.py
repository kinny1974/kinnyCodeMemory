"""
KinnyCode Unified Entry Point — Standalone executable entry.

Handles both server and CLI commands from a single binary.
Designed for PyInstaller packaging (--onefile / --onedir).

IMPORTANT: When bundled with PyInstaller, the server is started via
uvicorn.run() in-process (NOT subprocess) because sys.executable
points to the standalone binary.

Usage:
    kinnycode server start       # Start server in background thread
    kinnycode server stop        # Stop the server
    kinnycode server status      # Check server status
    kinnycode init [path]        # Initialize a project
    kinnycode index [path]       # Index project files
    kinnycode search <query>     # Semantic search
    kinnycode status [path]      # Show project stats
    kinnycode uninstall          # Remove KinnyCode
"""

from __future__ import annotations

import argparse
import os
import sys
import threading
import time
from pathlib import Path

SERVER_URL = os.environ.get("MEMORY_SERVER_URL", "http://127.0.0.1:8006")


def _is_bundled() -> bool:
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")


def _get_app_dir() -> Path:
    if _is_bundled():
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


def _start_server_direct(host: str = "127.0.0.1", port: int = 8006):
    """Start the FastAPI server in-process via uvicorn.run()."""
    import uvicorn

    # Add the app directory to path so memory_server can be imported
    app_dir = _get_app_dir()
    sys.path.insert(0, str(app_dir))

    from memory_server import app

    uvicorn.run(app, host=host, port=port, log_level="info")


def _start_server_background(host: str = "127.0.0.1", port: int = 8006) -> threading.Thread:
    """Start server in a background daemon thread."""
    t = threading.Thread(target=_start_server_direct, args=(host, port), daemon=True)
    t.start()
    return t


def cmd_server_start(args):
    """Start the memory server."""
    import httpx

    try:
        client = httpx.Client(timeout=5.0)
        resp = client.get(f"{SERVER_URL}/docs")
        if resp.status_code in (200, 307, 308):
            print(f"[i] Memory server is already running at {SERVER_URL}")
            return
    except Exception:
        pass

    host = getattr(args, "host", "127.0.0.1")
    port = getattr(args, "port", 8006)

    print(f"[*] Starting KinnyCode Memory Server on http://{host}:{port}")
    print(f"    Embedding model: all-MiniLM-L6-v2 (first load may take a moment)")

    _start_server_background(host, port)

    # Wait for server to come up
    spinner = ["\u25d0", "\u25d3", "\u25d1", "\u25d2"]
    start_time = time.time()
    timeout = 120
    i = 0

    while (time.time() - start_time) < timeout:
        time.sleep(0.5)
        i += 1
        elapsed = int(time.time() - start_time)
        sys.stdout.write(f"\r  {spinner[i % 4]} Loading... {elapsed}s")
        sys.stdout.flush()

        try:
            client = httpx.Client(timeout=2.0)
            resp = client.get(f"{SERVER_URL}/docs")
            if resp.status_code in (200, 307, 308):
                sys.stdout.write("\r" + " " * 60 + "\r")
                sys.stdout.flush()
                print(f"[+] Server started successfully on {SERVER_URL}")
                print(f"    API Docs: {SERVER_URL}/docs")
                return
        except Exception:
            pass

    sys.stdout.write("\r" + " " * 60 + "\r")
    sys.stdout.flush()
    print(f"[!] Server may still be loading. Check: {SERVER_URL}/docs")


def cmd_server_stop(args):
    """Stop the memory server."""
    import httpx

    server_url = SERVER_URL.rstrip("/")

    try:
        client = httpx.Client(timeout=5.0)
        resp = client.post(f"{server_url}/shutdown")
        print(f"[+] Server shutdown requested: {resp.text}")
        return
    except Exception:
        pass

    # Fallback: try the PID file
    pid_file = Path.home() / ".kinnycode" / "server.pid"
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            import signal
            import platform

            if platform.system() == "Windows":
                import subprocess
                subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                               capture_output=True)
            else:
                os.kill(pid, signal.SIGTERM)
            pid_file.unlink()
            print(f"[+] Server stopped (PID: {pid})")
            return
        except Exception as exc:
            print(f"[!] Could not stop PID: {exc}")

    print("[!] Server not found running.")


def cmd_server_status(args):
    """Check server status."""
    import httpx

    try:
        client = httpx.Client(timeout=5.0)
        resp = client.get(f"{SERVER_URL}/docs")
        if resp.status_code in (200, 307, 308):
            print(f"[+] Server: RUNNING")
            print(f"    URL: {SERVER_URL}")
            print(f"    API Docs: {SERVER_URL}/docs")
            return
    except Exception:
        pass

    print(f"[-] Server: NOT RUNNING")
    print(f"    Expected at: {SERVER_URL}")


# ═══════════════════════════════════════════════════════════════════════════
# Delegate to cli.py for other commands via the REST API
# ═══════════════════════════════════════════════════════════════════════════

def _delegate_to_cli():
    """Import and run cli.py for full command handling."""
    app_dir = _get_app_dir()
    sys.path.insert(0, str(app_dir))
    import cli
    cli.main()


def main():
    parser = argparse.ArgumentParser(
        prog="kinnycode",
        description="KinnyCode Multi-Layer Memory System",
    )
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # server subcommands
    server_parser = subparsers.add_parser("server", help="Server management")
    server_subs = server_parser.add_subparsers(dest="server_command")

    start_p = server_subs.add_parser("start", help="Start the memory server")
    start_p.add_argument("--host", default="127.0.0.1")
    start_p.add_argument("--port", type=int, default=8006)

    server_subs.add_parser("stop", help="Stop the memory server")
    server_subs.add_parser("status", help="Check server status")

    # Other commands
    subparsers.add_parser("init", help="Initialize project")
    subparsers.add_parser("index", help="Index project files")
    subparsers.add_parser("search", help="Semantic search")
    subparsers.add_parser("status", help="Project status")
    subparsers.add_parser("uninstall", help="Uninstall KinnyCode")

    args = parser.parse_args()

    if args.command == "server":
        if args.server_command == "start":
            cmd_server_start(args)
        elif args.server_command == "stop":
            cmd_server_stop(args)
        elif args.server_command == "status":
            cmd_server_status(args)
        else:
            parser.print_help()
    elif args.command is None:
        parser.print_help()
    else:
        # Delegate to cli.py for full handling
        _delegate_to_cli()


if __name__ == "__main__":
    main()
