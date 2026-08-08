#!/usr/bin/env python3
"""
KinnyCode Memory System - System Tray Application
===================================================
Cross-platform system tray icon for Windows and Linux.
Provides quick access to server status, web UI, and controls.

Usage:
    python tray_app.py [--port PORT] [--host HOST]
"""

import os
import sys
import platform
import signal
import subprocess
import webbrowser
import time
import threading
from pathlib import Path
from typing import Optional

try:
    import pystray
    from pystray import MenuItem, Icon
    HAS_PYSTRAY = True
except ImportError:
    HAS_PYSTRAY = False

try:
    from PIL import Image, ImageDraw, ImageFont
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

import httpx


# ═══════════════════════════════════════════════════════════════════════
#  Constants
# ═══════════════════════════════════════════════════════════════════════

APP_NAME = "KinnyCode Memory"
DEFAULT_PORT = 8007
DEFAULT_HOST = "127.0.0.1"
CHECK_INTERVAL = 5  # seconds between health checks

PLATFORM = platform.system().lower()


# ═══════════════════════════════════════════════════════════════════════
#  Icon Generator
# ═══════════════════════════════════════════════════════════════════════


def create_icon_image(status: str = "running") -> Optional[Image.Image]:
    """Create a simple tray icon programmatically."""
    if not HAS_PIL:
        return None

    # Create 64x64 icon
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Color based on status
    colors = {
        "running": (76, 175, 80),    # Green
        "stopped": (244, 67, 54),    # Red
        "starting": (255, 193, 7),   # Yellow
    }
    color = colors.get(status, (158, 158, 158))  # Gray default

    # Draw circle
    draw.ellipse([4, 4, 60, 60], fill=color)

    # Draw "K" letter
    try:
        font = ImageFont.truetype("arial.ttf", 32)
    except (IOError, OSError):
        font = ImageFont.load_default()

    draw.text((20, 14), "K", fill="white", font=font)

    return img


# ═══════════════════════════════════════════════════════════════════════
#  Server Monitor
# ═══════════════════════════════════════════════════════════════════════


class ServerMonitor:
    """Monitors the memory server health."""

    def __init__(self, host: str, port: int):
        self.base_url = f"http://{host}:{port}"
        self.is_running = False
        self.process: Optional[subprocess.Popen] = None
        self._callback = None

    def set_callback(self, callback):
        """Set callback for status changes."""
        self._callback = callback

    def check_health(self) -> bool:
        """Check if server is responding."""
        try:
            with httpx.Client(timeout=3.0) as client:
                resp = client.get(f"{self.base_url}/health")
                was_running = self.is_running
                self.is_running = resp.status_code == 200

                if was_running != self.is_running and self._callback:
                    self._callback(self.is_running)

                return self.is_running
        except Exception:
            was_running = self.is_running
            self.is_running = False

            if was_running != self.is_running and self._callback:
                self._callback(False)

            return False

    def start_server(self, server_dir: str):
        """Start the memory server."""
        if self.is_running:
            return

        if PLATFORM == "windows":
            python_exe = os.path.join(server_dir, ".venv", "Scripts", "python.exe")
        else:
            python_exe = os.path.join(server_dir, ".venv", "bin", "python3")

        server_script = os.path.join(server_dir, "memory_server.py")

        if not os.path.exists(python_exe):
            print(f"Python not found: {python_exe}")
            return

        self.process = subprocess.Popen(
            [python_exe, server_script],
            cwd=server_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=(
                subprocess.CREATE_NO_WINDOW if PLATFORM == "windows" else 0
            )
        )

        # Wait for server to start
        for _ in range(10):
            time.sleep(1)
            if self.check_health():
                break

    def stop_server(self):
        """Stop the memory server."""
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.process = None
            self.is_running = False


# ═══════════════════════════════════════════════════════════════════════
#  Tray Application
# ═══════════════════════════════════════════════════════════════════════


class KinnyCodeTray:
    """System tray application."""

    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT):
        self.host = host
        self.port = port
        self.monitor = ServerMonitor(host, port)
        self.monitor.set_callback(self._on_status_change)
        self.icon: Optional[Icon] = None
        self._running = False

    def _on_status_change(self, is_running: bool):
        """Handle server status change."""
        if self.icon:
            status = "running" if is_running else "stopped"
            self.icon.icon = create_icon_image(status)
            self.icon.title = f"{APP_NAME} — {'En ejecución' if is_running else 'Detenido'}"

    def _open_web_ui(self):
        """Open web UI in default browser."""
        webbrowser.open(f"http://{self.host}:{self.port}")

    def _open_docs(self):
        """Open API docs in default browser."""
        webbrowser.open(f"http://{self.host}:{self.port}/docs")

    def _check_health(self):
        """Manually check server health."""
        is_running = self.monitor.check_health()
        status = "en ejecución" if is_running else "detenido"
        if self.icon:
            self.icon.notify(
                f"Servidor {status}",
                APP_NAME
            )

    def _start_server(self):
        """Start the server."""
        server_dir = str(Path(__file__).parent)
        self.monitor.start_server(server_dir)

    def _stop_server(self):
        """Stop the server."""
        self.monitor.stop_server()

    def _restart_server(self):
        """Restart the server."""
        self.monitor.stop_server()
        time.sleep(1)
        self._start_server()

    def _exit(self):
        """Exit the tray application."""
        self._running = False
        if self.icon:
            self.icon.stop()

    def _create_menu(self):
        """Create the tray menu."""
        return pystray.Menu(
            MenuItem(
                f"{'🟢' if self.monitor.is_running else '🔴'} Servidor: "
                f"{'En ejecución' if self.monitor.is_running else 'Detenido'}",
                None,
                enabled=False
            ),
            pystray.Menu.SEPARATOR,
            MenuItem("Abrir Web UI", self._open_web_ui),
            MenuItem("Abrir API Docs", self._open_docs),
            pystray.Menu.SEPARATOR,
            MenuItem("Verificar Estado", self._check_health),
            MenuItem("Iniciar Servidor", self._start_server),
            MenuItem("Detener Servidor", self._stop_server),
            MenuItem("Reiniciar Servidor", self._restart_server),
            pystray.Menu.SEPARATOR,
            MenuItem("Salir", self._exit),
        )

    def _health_checker_loop(self):
        """Background thread for health checks."""
        while self._running:
            self.monitor.check_health()
            time.sleep(CHECK_INTERVAL)

    def run(self):
        """Run the tray application."""
        if not HAS_PYSTRAY:
            print("Error: pystray not installed. Run: pip install pystray")
            sys.exit(1)

        if not HAS_PIL:
            print("Warning: Pillow not installed. Using default icon.")
            print("Run: pip install Pillow")

        self._running = True

        # Create icon
        icon_image = create_icon_image("starting")
        self.icon = Icon(
            APP_NAME,
            icon_image,
            f"{APP_NAME} — Iniciando...",
            self._create_menu()
        )

        # Start health checker
        health_thread = threading.Thread(
            target=self._health_checker_loop,
            daemon=True
        )
        health_thread.start()

        # Run tray
        try:
            self.icon.run()
        except Exception as e:
            print(f"Error: {e}")
        finally:
            self._running = False


# ═══════════════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════════════


def main():
    """Entry point."""
    import argparse

    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--host", default=DEFAULT_HOST)
    args = parser.parse_args()

    tray = KinnyCodeTray(host=args.host, port=args.port)
    tray.run()


if __name__ == "__main__":
    main()
