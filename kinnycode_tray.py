"""
KinnyCode Memory System — System Tray Application
===================================================
Windows system tray icon with menu:
  - Server: Start / Stop / Restart
  - Change port
  - Open API docs in browser
  - Open install folder
  - Status check
  - Exit

Uses raw Win32 API for the system tray (no pystray/Pillow dependency).
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import json

if not hasattr(ctypes.wintypes, "ULONG_PTR"):
    ctypes.wintypes.ULONG_PTR = ctypes.c_size_t
if not hasattr(ctypes.wintypes, "HCURSOR"):
    ctypes.wintypes.HCURSOR = ctypes.wintypes.HANDLE
if not hasattr(ctypes.wintypes, "HBRUSH"):
    ctypes.wintypes.HBRUSH = ctypes.wintypes.HANDLE
if not hasattr(ctypes.wintypes, "HINSTANCE"):
    ctypes.wintypes.HINSTANCE = ctypes.wintypes.HANDLE
import os
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

def find_venv_python(venv_path: Path) -> Path:
    """Find python.exe in venv (handles MSYS2 'bin/' vs standard 'Scripts/')."""
    for subdir in ("Scripts", "bin"):
        candidate = venv_path / subdir / "python.exe"
        if candidate.exists():
            return candidate
    return venv_path / "Scripts" / "python.exe"

# ═══════════════════════════════════════════════════════════════════════════
#  Win32 API definitions
# ═══════════════════════════════════════════════════════════════════════════

# Constants
WM_USER = 0x0400
WM_TRAY_ICON = WM_USER + 1
WM_COMMAND = 0x0111
WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_QUIT = 0x0012

# Tray icon
NIM_ADD = 0x00000000
NIM_MODIFY = 0x00000001
NIM_DELETE = 0x00000002
NIM_SETVERSION = 0x00000004
NIF_MESSAGE = 0x00000001
NIF_ICON = 0x00000002
NIF_TIP = 0x00000004
NIF_INFO = 0x00000010
NIF_STATE = 0x00000008
NIF_GUID = 0x00000020
NIIF_NONE = 0x00000000
NIIF_INFO = 0x00000001
NIIF_WARNING = 0x00000002
NIIF_ERROR = 0x00000003
NIIF_USER = 0x00000004
NIIF_NOSOUND = 0x00000010

# Window styles
WS_OVERLAPPED = 0x00000000
WS_POPUP = 0x80000000
CW_USEDEFAULT = 0x80000000

# Icon types
IDI_APPLICATION = 32512
IDI_INFORMATION = 32516
IDI_WARNING = 32515
IDI_ERROR = 32513
LR_DEFAULTCOLOR = 0x00000000
IMAGE_ICON = 1

# Menu
MF_STRING = 0x00000000
MF_SEPARATOR = 0x00000800
MF_DISABLED = 0x00000002
MF_GRAYED = 0x00000001
MF_DEFAULT = 0x00001000
MF_POPUP = 0x00000010
TPM_BOTTOMALIGN = 0x00000020
TPM_LEFTALIGN = 0x00000000
TPM_RIGHTBUTTON = 0x00000002

# ═══════════════════════════════════════════════════════════════════════════
#  Win32 structures
# ═══════════════════════════════════════════════════════════════════════════

class NOTIFYICONDATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.wintypes.DWORD),
        ("hWnd", ctypes.wintypes.HWND),
        ("uID", ctypes.wintypes.UINT),
        ("uFlags", ctypes.wintypes.UINT),
        ("uCallbackMessage", ctypes.wintypes.UINT),
        ("hIcon", ctypes.wintypes.HICON),
        ("szTip", ctypes.c_wchar * 128),
        ("dwState", ctypes.wintypes.DWORD),
        ("dwStateMask", ctypes.wintypes.DWORD),
        ("szInfo", ctypes.c_wchar * 256),
        ("uVersion", ctypes.wintypes.UINT),
        ("szInfoTitle", ctypes.c_wchar * 64),
        ("dwInfoFlags", ctypes.wintypes.DWORD),
        ("guidItem", ctypes.c_byte * 16),
        ("hBalloonIcon", ctypes.wintypes.HICON),
    ]

class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", ctypes.wintypes.UINT),
        ("lpfnWndProc", ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.wintypes.HWND, ctypes.wintypes.UINT, ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM)),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", ctypes.wintypes.HINSTANCE),
        ("hIcon", ctypes.wintypes.HICON),
        ("hCursor", ctypes.wintypes.HCURSOR),
        ("hbrBackground", ctypes.wintypes.HBRUSH),
        ("lpszMenuName", ctypes.wintypes.LPCWSTR),
        ("lpszClassName", ctypes.wintypes.LPCWSTR),
    ]

class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", ctypes.wintypes.HWND),
        ("message", ctypes.wintypes.UINT),
        ("wParam", ctypes.wintypes.WPARAM),
        ("lParam", ctypes.wintypes.LPARAM),
        ("time", ctypes.wintypes.DWORD),
        ("pt", POINT),
    ]

class MENUITEMINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.wintypes.DWORD),
        ("fMask", ctypes.wintypes.DWORD),
        ("fType", ctypes.wintypes.DWORD),
        ("fState", ctypes.wintypes.DWORD),
        ("wID", ctypes.wintypes.UINT),
        ("hSubMenu", ctypes.wintypes.HMENU),
        ("hbmpChecked", ctypes.wintypes.HBITMAP),
        ("hbmpUnchecked", ctypes.wintypes.HBITMAP),
        ("dwItemData", ctypes.wintypes.ULONG_PTR),
        ("dwTypeData", ctypes.wintypes.LPWSTR),
        ("cch", ctypes.wintypes.UINT),
        ("hbmpItem", ctypes.wintypes.HBITMAP),
    ]


# ═══════════════════════════════════════════════════════════════════════════
#  System Tray Application
# ═══════════════════════════════════════════════════════════════════════════

class KinnyCodeTray:
    """Windows system tray manager for KinnyCode Memory Server."""

    MENU_IDS = {
        1000: "status",
        1001: "separator1",
        1002: "start",
        1003: "stop",
        1004: "restart",
        1005: "separator2",
        1006: "change_port",
        1007: "separator3",
        1008: "open_docs",
        1009: "open_folder",
        1010: "separator4",
        1011: "exit_app",
    }

    def __init__(self, install_dir: Path, port: int = 8006):
        self.install_dir = install_dir
        self.port = port
        self.python_exe = find_venv_python(install_dir / ".venv")
        self.cli_script = install_dir / "cli.py"
        self.hwnd = None
        self.running = True
        self.server_running = False
        self._monitor_thread: threading.Thread | None = None
        self._icon_path = install_dir / "assets" / "kinnycode.ico"

        # Load DLLs
        self.user32 = ctypes.windll.user32
        self.shell32 = ctypes.windll.shell32
        self.kernel32 = ctypes.windll.kernel32

        # Fix argtypes for 64-bit safety
        self.user32.DefWindowProcW.argtypes = [
            ctypes.wintypes.HWND, ctypes.wintypes.UINT,
            ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM,
        ]
        self.user32.DefWindowProcW.restype = ctypes.c_long

    def _is_server_running(self) -> bool:
        try:
            import socket
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(1)
            result = s.connect_ex(("127.0.0.1", self.port))
            s.close()
            return result == 0
        except Exception:
            return False

    def _tooltip(self) -> str:
        status = "[ON]" if self._is_server_running() else "[OFF]"
        return f"KinnyCode Memory - {status} :{self.port}"

    # ── Server control ────────────────────────────────────────────────────
    def start_server(self):
        if self._is_server_running():
            self._notify("Servidor ya está en ejecución", f"Puerto {self.port}")
            return

        try:
            if self.python_exe.exists() and self.cli_script.exists():
                subprocess.Popen(
                    [str(self.python_exe), str(self.cli_script), "server", "start",
                     "--port", str(self.port)],
                    creationflags=subprocess.DETACHED_PROCESS if hasattr(subprocess, "DETACHED_PROCESS") else 0,
                    close_fds=True,
                )
                self._notify("Iniciando servidor...", f"http://127.0.0.1:{self.port}")
            else:
                self._notify("Error", "No se encontró Python o cli.py", error=True)
        except Exception as e:
            self._notify("Error al iniciar", str(e), error=True)

    def stop_server(self):
        if not self._is_server_running():
            self._notify("Servidor no está en ejecución", "")
            return

        try:
            if self.python_exe.exists() and self.cli_script.exists():
                subprocess.run(
                    [str(self.python_exe), str(self.cli_script), "server", "stop"],
                    capture_output=True, timeout=10
                )
                self._notify("Servidor detenido", "")
            else:
                # Fallback: kill by port
                subprocess.run(
                    ["powershell", "-Command",
                     f"$c = Get-NetTCPConnection -LocalPort {self.port} -ErrorAction SilentlyContinue; "
                     f"if ($c) {{ Stop-Process -Id $c.OwningProcess -Force }}"],
                    capture_output=True, timeout=10
                )
                self._notify("Servidor detenido (force)", "")
        except Exception as e:
            self._notify("Error al detener", str(e), error=True)

    def restart_server(self):
        self.stop_server()
        time.sleep(1.5)
        self.start_server()

    def change_port(self):
        """Open a dialog to change port - use MessageBox + simple input."""
        import tkinter as tk
        from tkinter import simpledialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        new_port_str = simpledialog.askstring(
            "Cambiar Puerto",
            f"Puerto actual: {self.port}\nNuevo puerto:",
            initialvalue=str(self.port),
            parent=root
        )
        root.destroy()

        if new_port_str:
            try:
                new_port = int(new_port_str)
                if 1 <= new_port <= 65535:
                    old_port = self.port
                    self.port = new_port
                    # Update registry
                    self._update_registry_port(new_port)
                    self._update_tip()
                    self._notify("Puerto actualizado",
                                 f"{old_port} → {new_port}\nReinicia el servidor para aplicar")
                else:
                    self._notify("Puerto inválido", "Debe estar entre 1-65535", error=True)
            except ValueError:
                self._notify("Puerto inválido", "Debe ser un número", error=True)

    def _update_registry_port(self, port: int):
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                r"Software\KinnyCode\Memory", 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, "Port", 0, winreg.REG_DWORD, port)
        except Exception:
            pass

    def open_api_docs(self):
        webbrowser.open(f"http://127.0.0.1:{self.port}/docs")

    def open_folder(self):
        os.startfile(str(self.install_dir))

    # ── Notification ──────────────────────────────────────────────────────
    def _notify(self, title: str, message: str, error: bool = False):
        if self.hwnd:
            flags = NIIF_ERROR if error else NIIF_INFO
            nid = NOTIFYICONDATA()
            nid.cbSize = ctypes.sizeof(NOTIFYICONDATA)
            nid.hWnd = self.hwnd
            nid.uID = 1
            nid.uFlags = NIF_INFO
            nid.szInfoTitle = title
            nid.szInfo = message
            nid.dwInfoFlags = flags
            self.shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid))

    # ── Tray icon management ──────────────────────────────────────────────
    def _create_icon(self):
        """Create or update the tray icon."""
        # Load custom ICO file
        if self._icon_path.exists():
            icon_handle = self.user32.LoadImageW(
                0, str(self._icon_path), IMAGE_ICON, 0, 0, 0x00000010
            )
        else:
            icon_handle = self.user32.LoadIconW(0, IDI_APPLICATION)

        nid = NOTIFYICONDATA()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATA)
        nid.hWnd = self.hwnd
        nid.uID = 1
        nid.uFlags = NIF_ICON | NIF_MESSAGE | NIF_TIP
        nid.uCallbackMessage = WM_TRAY_ICON
        nid.hIcon = icon_handle
        nid.szTip = self._tooltip()
        self.shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid))

    def _update_tip(self):
        if self.hwnd:
            # Recreate icon with new tooltip
            self._create_icon()

    def _remove_icon(self):
        if self.hwnd:
            nid = NOTIFYICONDATA()
            nid.cbSize = ctypes.sizeof(NOTIFYICONDATA)
            nid.hWnd = self.hwnd
            nid.uID = 1
            self.shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nid))

    # ── Context menu ──────────────────────────────────────────────────────
    def _show_menu(self):
        # Create popup menu
        menu = self.user32.CreatePopupMenu()

        # Status line (current port + running state)
        status_text = f"Puerto: {self.port} — {'● En ejecución' if self._is_server_running() else '○ Detenido'}"
        self.user32.AppendMenuW(menu, MF_STRING | MF_GRAYED, 1000, status_text)
        self.user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)

        # Server control
        self.user32.AppendMenuW(menu, MF_STRING, 1002, "▶  Iniciar servidor")
        self.user32.AppendMenuW(menu, MF_STRING, 1003, "■  Detener servidor")
        self.user32.AppendMenuW(menu, MF_STRING, 1004, "↻  Reiniciar servidor")
        self.user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)

        # Settings
        self.user32.AppendMenuW(menu, MF_STRING, 1006, "⚙  Cambiar puerto...")
        self.user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)

        # Tools
        self.user32.AppendMenuW(menu, MF_STRING, 1008, "📖  Abrir API docs")
        self.user32.AppendMenuW(menu, MF_STRING, 1009, "📁  Abrir carpeta de instalación")
        self.user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)

        # Exit
        self.user32.AppendMenuW(menu, MF_STRING, 1011, "✕  Salir")

        # Get cursor position
        point = POINT()
        self.user32.GetCursorPos(ctypes.byref(point))

        # Required: set foreground window so menu closes properly
        self.user32.SetForegroundWindow(self.hwnd)

        # Show menu
        self.user32.TrackPopupMenu(
            menu, TPM_BOTTOMALIGN | TPM_LEFTALIGN | TPM_RIGHTBUTTON,
            point.x, point.y, 0, self.hwnd, None
        )

    # ── Window procedure ──────────────────────────────────────────────────
    def _window_proc(self, hwnd, msg, wparam, lparam):
        if msg == WM_TRAY_ICON:
            if lparam == 0x0205:  # WM_RBUTTONUP
                self._show_menu()
            elif lparam == 0x0204:  # WM_RBUTTONDOWN
                pass
            elif lparam == 0x0203:  # WM_LBUTTONDBLCLK
                self.open_api_docs()

        elif msg == WM_COMMAND:
            cmd_id = wparam
            self._handle_command(cmd_id)

        elif msg == WM_DESTROY:
            self._remove_icon()
            self.user32.PostQuitMessage(0)
            self.running = False

        return self.user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _handle_command(self, cmd_id: int):
        action = self.MENU_IDS.get(cmd_id, "")
        if action == "start":
            self.start_server()
        elif action == "stop":
            self.stop_server()
        elif action == "restart":
            self.restart_server()
        elif action == "change_port":
            self.change_port()
        elif action == "open_docs":
            self.open_api_docs()
        elif action == "open_folder":
            self.open_folder()
        elif action == "exit_app":
            self._remove_icon()
            self.running = False
            self.user32.PostQuitMessage(0)

        self._update_tip()

    # ── Monitor thread ────────────────────────────────────────────────────
    def _monitor_loop(self):
        """Periodically update tooltip based on server status."""
        while self.running:
            time.sleep(5)
            if self.running:
                self._update_tip()

    # ── Main message loop ─────────────────────────────────────────────────
    def run(self):
        """Run the system tray message loop."""
        # Register window class
        wndclass = WNDCLASSW()
        wndclass.lpfnWndProc = ctypes.WINFUNCTYPE(
            ctypes.c_long, ctypes.wintypes.HWND, ctypes.c_uint,
            ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM
        )(self._window_proc)
        wndclass.hInstance = self.kernel32.GetModuleHandleW(0)
        wndclass.lpszClassName = "KinnyCodeMemoryTrayClass"

        if not self.user32.RegisterClassW(ctypes.byref(wndclass)):
            self.user32.MessageBoxW(0, "Error registrando la clase de ventana",
                                    "Error", 0x10)
            return

        # Create hidden window
        self.hwnd = self.user32.CreateWindowExW(
            0, "KinnyCodeMemoryTrayClass", "KinnyCode Memory",
            0, 0, 0, 0, 0, 0, 0, wndclass.hInstance, 0
        )

        if not self.hwnd:
            self.user32.MessageBoxW(0, "Error creando la ventana",
                                    "Error", 0x10)
            return

        # Create tray icon
        self._create_icon()

        # Start monitor thread
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()

        # Message loop
        msg = MSG()
        while self.running:
            result = self.user32.GetMessageW(ctypes.byref(msg), 0, 0, 0)
            if result in (0, -1):
                break
            self.user32.TranslateMessage(ctypes.byref(msg))
            self.user32.DispatchMessageW(ctypes.byref(msg))


# ═══════════════════════════════════════════════════════════════════════════
#  Entry point
# ═══════════════════════════════════════════════════════════════════════════

def main():
    import argparse
    parser = argparse.ArgumentParser(description="KinnyCode System Tray")
    parser.add_argument("--port", type=int, default=8006, help="Server port")
    parser.add_argument("--install-dir", type=str,
                        default=str(Path(os.environ.get("PROGRAMDATA", "C:\\ProgramData")) /
                                    "KinnyCode" / "memory"),
                        help="Install directory")
    args = parser.parse_args()

    install_dir = Path(args.install_dir)
    port = args.port

    # Try to read from registry/install_config
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\KinnyCode\Memory", 0, winreg.KEY_READ) as key:
            port_val, _ = winreg.QueryValueEx(key, "Port")
            port = int(port_val)
            dir_val, _ = winreg.QueryValueEx(key, "InstallDir")
            install_dir = Path(dir_val)
    except Exception:
        pass

    tray = KinnyCodeTray(install_dir, port)
    tray.run()


if __name__ == "__main__":
    main()
