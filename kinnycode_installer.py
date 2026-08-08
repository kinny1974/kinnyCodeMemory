"""
KinnyCode Memory System — Windows Installer
============================================
Self-contained installer GUI (tkinter) + system tray manager.
Generates a standalone .exe via PyInstaller.

When executed:
- If not installed → shows installer wizard (4 pages)
- If already installed → launches system tray

Color palette from assets/SVGs:
  Primary Orange : #ee6309  (kinnycode-logo.svg)
  Dark Orange    : #d9430e
  Darkest        : #972c0a
  White          : #fefefe
  Accent Cyan    : #00BCD4  (present in original installer)
  BG Dark        : #1E1E2E
  Card BG        : #16162A
  Input BG       : #2D2D44
  Text Primary   : #CCCCDD
  Text Secondary : #AAAAAA
  Success Green  : #00E676
  Warning Amber  : #FFC107
  Error Red      : #D32F2F
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any

# ── Constants ──────────────────────────────────────────────────────────────
def find_venv_python(venv_path: Path) -> Path:
    """Find python.exe in venv (handles MSYS2 'bin/' vs standard 'Scripts/')."""
    for subdir in ("Scripts", "bin"):
        candidate = venv_path / subdir / "python.exe"
        if candidate.exists():
            return candidate
    # Fallback: return the standard path (let caller handle missing)
    return venv_path / "Scripts" / "python.exe"


APP_NAME = "KinnyCode Memory System"
VERSION = "2.2.0"
DEFAULT_PORT = 8006
DEFAULT_INSTALL_DIR = Path(os.environ.get("PROGRAMDATA", "C:\\ProgramData")) / "KinnyCode" / "memory"
SOURCE_DIR = Path(__file__).resolve().parent if not getattr(sys, "frozen", False) else Path(sys._MEIPASS)  # type: ignore[attr-defined]
PID_FILE = Path.home() / ".kinnycode" / "server.pid"
TRAY_SIGNAL_FILE = Path.home() / ".kinnycode" / "tray_signal.json"

# Color palette (from SVG assets)
C_BG_DARK = "#1E1E2E"
C_CARD = "#16162A"
C_INPUT_BG = "#2D2D44"
C_INPUT_BORDER = "#3D3D55"
C_TEXT = "#CCCCDD"
C_TEXT_SEC = "#AAAAAA"
C_TEXT_MUTED = "#666677"
C_ORANGE = "#ee6309"
C_ORANGE_DARK = "#d9430e"
C_ORANGE_DEEP = "#972c0a"
C_CYAN = "#00BCD4"
C_CYAN_DARK = "#006064"
C_SUCCESS = "#00E676"
C_WARNING = "#FFC107"
C_ERROR = "#D32F2F"
C_WHITE = "#fefefe"

# ── Helper: detect if already installed ────────────────────────────────────
def is_installed(install_dir: Path | None = None) -> bool:
    if install_dir is None:
        install_dir = DEFAULT_INSTALL_DIR
    memory_file = install_dir / "memory_server.py"
    return memory_file.exists()


def is_server_running(port: int = DEFAULT_PORT) -> bool:
    try:
        import httpx
        client = httpx.Client(timeout=3.0)
        resp = client.get(f"http://127.0.0.1:{port}/docs")
        return resp.status_code in (200, 307, 308)
    except Exception:
        return False


def detect_opencode() -> tuple[bool, str]:
    """Detect if opencode is installed. Returns (found, path_or_message)."""
    candidates = [
        Path(os.environ.get("USERPROFILE", "")) / ".local" / "bin" / "opencode.cmd",
        Path(os.environ.get("USERPROFILE", "")) / ".local" / "bin" / "opencode.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "opencode" / "opencode.exe",
    ]
    # Also check PATH
    for cmd in ["opencode", "opencode.cmd"]:
        try:
            result = subprocess.run(
                ["where", cmd], capture_output=True, text=True, shell=True, timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                return True, result.stdout.strip().split("\n")[0].strip()
        except Exception:
            pass

    for candidate in candidates:
        if candidate.exists():
            return True, str(candidate)
    return False, "No encontrado"


def find_all_opencodes() -> list[dict]:
    """Find ALL opencode installations on the system."""
    found: list[dict] = []
    seen: set[str] = set()

    # 1. Check PATH via 'where'
    for cmd in ["opencode", "opencode.cmd", "opencode.exe"]:
        try:
            result = subprocess.run(
                ["where", cmd], capture_output=True, text=True, shell=True, timeout=5
            )
            if result.returncode == 0:
                for line in result.stdout.strip().split("\n"):
                    line = line.strip()
                    if not line:
                        continue
                    resolved = str(Path(line).resolve()) if not line.endswith(".cmd") else line
                    if resolved not in seen:
                        seen.add(resolved)
                        found.append({"path": line, "source": "PATH"})
        except Exception:
            continue

    # 2. Scan known locations
    candidates = [
        Path(os.environ.get("USERPROFILE", "")) / ".local" / "bin" / "opencode.cmd",
        Path(os.environ.get("USERPROFILE", "")) / ".local" / "bin" / "opencode.exe",
        Path(os.environ.get("USERPROFILE", "")) / ".bun" / "bin" / "opencode.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "opencode" / "opencode.exe",
        Path(os.environ.get("APPDATA", "")) / "npm" / "opencode",
        Path(os.environ.get("APPDATA", "")) / "npm" / "opencode.cmd",
    ]
    for candidate in candidates:
        if candidate.exists():
            res = str(candidate)
            if res not in seen:
                seen.add(res)
                found.append({"path": res, "source": "Scan"})

    return found


def find_python() -> str | None:
    """Find a suitable Python 3.10+ installation."""
    for cmd in ["python", "python3", "py"]:
        try:
            result = subprocess.run(
                [cmd, "--version"], capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                version_str = result.stdout.strip() + result.stderr.strip()
                return cmd
        except Exception:
            continue
    return None


def find_all_pythons() -> list[dict]:
    """Find ALL Python 3.10+ installations on the system with path and version."""
    found: list[dict] = []
    seen_paths: set[str] = set()

    # 1. Check known commands via 'where'
    for cmd in ["python", "python3", "py"]:
        try:
            result = subprocess.run(
                ["where", cmd], capture_output=True, text=True, shell=True, timeout=5
            )
            if result.returncode == 0:
                for line in result.stdout.strip().split("\n"):
                    line = line.strip()
                    if not line or line.lower().endswith(".cmd"):
                        continue
                    exe_path = str(Path(line).resolve())
                    if exe_path in seen_paths:
                        continue
                    # Skip Windows Store placeholders
                    if "WindowsApps" in exe_path:
                        continue
                    try:
                        ver = subprocess.run(
                            [exe_path, "--version"], capture_output=True, text=True, timeout=5
                        )
                        if ver.returncode == 0:
                            ver_str = (ver.stdout + ver.stderr).strip()
                            seen_paths.add(exe_path)
                            found.append({
                                "path": exe_path,
                                "version": ver_str,
                                "source": "PATH",
                            })
                    except Exception:
                        continue
        except Exception:
            continue

    # 2. Scan common install locations
    common_dirs = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Python",
        Path("C:/Program Files/Python*"),
        Path(os.environ.get("APPDATA", "")) / "Python",
        Path("C:/msys64/mingw64/bin"),
        Path("C:/msys64/usr/bin"),
        Path("C:/cygwin64/bin"),
    ]
    from glob import glob as _glob
    for pattern in common_dirs:
        try:
            for py_dir in _glob(str(pattern)):
                py_path = Path(py_dir)
                if py_path.is_dir():
                    for exe_name in ["python.exe", "python3.exe"]:
                        exe = py_path / exe_name
                        res = str(exe.resolve())
                        if exe.exists() and res not in seen_paths:
                            try:
                                ver = subprocess.run(
                                    [str(exe), "--version"], capture_output=True, text=True, timeout=5
                                )
                                if ver.returncode == 0:
                                    ver_str = (ver.stdout + ver.stderr).strip()
                                    seen_paths.add(res)
                                    found.append({
                                        "path": res,
                                        "version": ver_str,
                                        "source": "Scan",
                                    })
                            except Exception:
                                continue
        except Exception:
            continue

    return found


# ═══════════════════════════════════════════════════════════════════════════
#  Installer Wizard GUI (tkinter)
# ═══════════════════════════════════════════════════════════════════════════

class InstallerWizard:
    """4-page installer wizard with dark theme matching SVG palette."""

    def __init__(self):
        self.root = tk.Tk()
        self.root.title(f"{APP_NAME} — Instalador v{VERSION}")
        self.root.geometry("700x620")
        self.root.resizable(False, False)
        self.root.configure(bg=C_BG_DARK)

        # Override close button
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Center window
        self.root.eval("tk::PlaceWindow . center")

        # State
        self.current_page = 0
        self.install_dir = tk.StringVar(value=str(DEFAULT_INSTALL_DIR))
        self.port = tk.StringVar(value=str(DEFAULT_PORT))
        self.create_service = tk.BooleanVar(value=True)
        self.auto_start_tray = tk.BooleanVar(value=True)
        self.opencode_found = False
        self.opencode_path = ""
        self.python_found = False
        self.python_cmd = ""
        self.all_pythons: list[dict] = []
        self.all_opencodes: list[dict] = []
        self.python_selected_var = tk.StringVar(value="Detectando...")
        self.install_success = False
        self.install_thread: threading.Thread | None = None
        self.install_log: list[str] = []

        # Log text variable for page 3
        self.log_text = tk.StringVar(value="Preparando instalación...")
        self.progress_var = tk.DoubleVar(value=0)
        self.status_var = tk.StringVar(value="")

        # Build UI
        self._build_title_bar()
        self._build_pages()
        self._build_nav_bar()
        self._show_page(0)

    # ── Title Bar ─────────────────────────────────────────────────────────
    def _build_title_bar(self):
        frame = tk.Frame(self.root, bg=C_CARD, height=40)
        frame.pack(fill=tk.X)
        frame.pack_propagate(False)

        lbl = tk.Label(
            frame, text=f"  {APP_NAME} — Instalador v{VERSION}",
            bg=C_CARD, fg=C_TEXT_MUTED, font=("Segoe UI", 10), anchor="w"
        )
        lbl.pack(side=tk.LEFT, padx=10, pady=8)

        close_btn = tk.Button(
            frame, text="\u2715", bg=C_CARD, fg=C_TEXT_MUTED,
            font=("Segoe UI", 13), bd=0, activebackground=C_ERROR,
            activeforeground=C_WHITE, cursor="hand2",
            command=self._on_close
        )
        close_btn.pack(side=tk.RIGHT, padx=2)

        # Make title bar draggable
        frame.bind("<Button-1>", self._start_move)
        frame.bind("<B1-Motion>", self._on_move)
        lbl.bind("<Button-1>", self._start_move)
        lbl.bind("<B1-Motion>", self._on_move)

    def _start_move(self, event):
        self._move_x = event.x_root
        self._move_y = event.y_root

    def _on_move(self, event):
        dx = event.x_root - self._move_x
        dy = event.y_root - self._move_y
        x = self.root.winfo_x() + dx
        y = self.root.winfo_y() + dy
        self.root.geometry(f"+{x}+{y}")
        self._move_x = event.x_root
        self._move_y = event.y_root

    # ── Pages ─────────────────────────────────────────────────────────────
    def _build_pages(self):
        self.pages_frame = tk.Frame(self.root, bg=C_BG_DARK)
        self.pages_frame.pack(fill=tk.BOTH, expand=True, padx=40, pady=(10, 0))

        self.page1 = self._build_page1()
        self.page2 = self._build_page2()
        self.page3 = self._build_page3()
        self.page4 = self._build_page4()

    # ── Page 1: Welcome ───────────────────────────────────────────────────
    def _build_page1(self) -> tk.Frame:
        frame = tk.Frame(self.pages_frame, bg=C_BG_DARK)

        tk.Label(
            frame, text="KinnyCode", font=("Segoe UI", 38, "bold"),
            bg=C_BG_DARK, fg=C_ORANGE
        ).pack(pady=(20, 0))

        tk.Label(
            frame, text="Sistema de Memoria Multicapa con RAG",
            font=("Segoe UI", 14), bg=C_BG_DARK, fg=C_TEXT
        ).pack(pady=(2, 16))

        # Logo: orange circle with </> symbol rendered via Canvas
        canvas = tk.Canvas(frame, width=80, height=80, bg=C_BG_DARK, highlightthickness=0)
        canvas.create_oval(10, 10, 70, 70, fill=C_ORANGE, outline="")
        canvas.create_text(40, 42, text="</>", font=("Consolas", 18, "bold"), fill=C_WHITE)
        canvas.pack(pady=(0, 12))

        tk.Label(
            frame,
            text=(
                "Este instalador configurará el sistema KinnyCode Memory:\n\n"
                "  • Servidor FastAPI con endpoints REST\n"
                "  • Base de datos vectorial LanceDB (embebida)\n"
                "  • Indexación semántica de código y documentos\n"
                "  • Persistencia de conversaciones con embeddings\n"
                "  • CLI `kinnycode` para gestión desde terminal\n"
                "  • Integración MCP para asistentes de código\n"
                "  • Sistema de bandeja para control del servidor"
            ),
            font=("Segoe UI", 11), bg=C_BG_DARK, fg=C_TEXT_SEC,
            justify=tk.LEFT
        ).pack(pady=(8, 0))

        tk.Label(
            frame, text=f"Versión {VERSION}",
            font=("Segoe UI", 10), bg=C_BG_DARK, fg=C_TEXT_MUTED
        ).pack(pady=(16, 0))

        return frame

    # ── Page 2: Configuration ─────────────────────────────────────────────
    def _build_page2(self) -> tk.Frame:
        frame = tk.Frame(self.pages_frame, bg=C_BG_DARK)

        tk.Label(
            frame, text="Configuración de Instalación",
            font=("Segoe UI", 18, "bold"), bg=C_BG_DARK, fg=C_CYAN
        ).pack(anchor=tk.W, pady=(0, 16))

        # Install directory
        row1 = tk.Frame(frame, bg=C_BG_DARK)
        row1.pack(fill=tk.X, pady=(0, 8))
        tk.Label(
            row1, text="Directorio de instalación:",
            font=("Segoe UI", 11), bg=C_BG_DARK, fg=C_TEXT_SEC, width=24, anchor=tk.W
        ).pack(side=tk.LEFT)

        entry_frame = tk.Frame(row1, bg=C_INPUT_BORDER)
        entry_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)
        dir_entry = tk.Entry(
            entry_frame, textvariable=self.install_dir, font=("Segoe UI", 10),
            bg=C_INPUT_BG, fg=C_TEXT, insertbackground=C_CYAN,
            bd=0, relief=tk.FLAT, highlightthickness=0
        )
        dir_entry.pack(fill=tk.X, padx=1, pady=1)

        browse_btn = tk.Button(
            row1, text="Examinar...", font=("Segoe UI", 10),
            bg=C_INPUT_BG, fg=C_CYAN, bd=1, relief=tk.FLAT,
            activebackground=C_CARD, activeforeground=C_ORANGE,
            cursor="hand2", command=self._browse_dir
        )
        browse_btn.pack(side=tk.LEFT, padx=(8, 0))

        # Port
        row2 = tk.Frame(frame, bg=C_BG_DARK)
        row2.pack(fill=tk.X, pady=(0, 8))
        tk.Label(
            row2, text="Puerto del servidor:", font=("Segoe UI", 11),
            bg=C_BG_DARK, fg=C_TEXT_SEC, width=24, anchor=tk.W
        ).pack(side=tk.LEFT)
        port_frame = tk.Frame(row2, bg=C_INPUT_BORDER)
        port_frame.pack(side=tk.LEFT)
        port_entry = tk.Entry(
            port_frame, textvariable=self.port, font=("Segoe UI", 10),
            bg=C_INPUT_BG, fg=C_TEXT, insertbackground=C_CYAN,
            bd=0, relief=tk.FLAT, width=10
        )
        port_entry.pack(padx=1, pady=1)

        # Separator
        sep = tk.Frame(frame, bg=C_INPUT_BORDER, height=1)
        sep.pack(fill=tk.X, pady=(8, 12))

        # Opencode detection
        self.opencode_section_frame = tk.Frame(frame, bg=C_BG_DARK)
        self.opencode_section_frame.pack(fill=tk.X, anchor=tk.W, pady=(0, 8))

        tk.Label(
            self.opencode_section_frame, text="Opencode detectado:",
            font=("Segoe UI", 12, "bold"), bg=C_BG_DARK, fg=C_TEXT
        ).pack(anchor=tk.W, pady=(0, 4))

        self.opencode_status_var = tk.StringVar(value="Detectando...")
        self.opencode_status_lbl = tk.Label(
            self.opencode_section_frame, textvariable=self.opencode_status_var,
            font=("Segoe UI", 11), bg=C_BG_DARK, fg=C_TEXT_SEC
        )
        self.opencode_status_lbl.pack(anchor=tk.W)

        self.opencode_list_frame = tk.Frame(self.opencode_section_frame, bg=C_BG_DARK)
        self.opencode_list_frame.pack(fill=tk.X, anchor=tk.W)

        # Python detection with dropdown
        self.python_section_frame = tk.Frame(frame, bg=C_BG_DARK)
        self.python_section_frame.pack(fill=tk.X, anchor=tk.W, pady=(4, 0))

        tk.Label(
            self.python_section_frame, text="Python a usar:",
            font=("Segoe UI", 12, "bold"), bg=C_BG_DARK, fg=C_TEXT
        ).pack(anchor=tk.W, pady=(6, 4))

        self.python_status_var = tk.StringVar(value="Detectando...")
        self.python_combo = ttk.Combobox(
            self.python_section_frame, textvariable=self.python_selected_var,
            font=("Segoe UI", 10), state="readonly", width=70
        )
        self.python_combo.pack(fill=tk.X, anchor=tk.W)
        self.python_combo.bind("<<ComboboxSelected>>", self._on_python_selected)

        self.python_detail_var = tk.StringVar(value="")
        self.python_detail_lbl = tk.Label(
            self.python_section_frame, textvariable=self.python_detail_var,
            font=("Segoe UI", 9), bg=C_BG_DARK, fg=C_TEXT_MUTED
        )
        self.python_detail_lbl.pack(anchor=tk.W, pady=(2, 0))

        # Refresh button
        refresh_btn = tk.Button(
            self.python_section_frame, text="Re-detectar", font=("Segoe UI", 9),
            bg=C_INPUT_BG, fg=C_CYAN, bd=1, relief=tk.FLAT,
            activebackground=C_CARD, activeforeground=C_ORANGE,
            cursor="hand2", command=self._run_detection
        )
        refresh_btn.pack(anchor=tk.W, pady=(4, 0))

        # Separator
        sep2 = tk.Frame(frame, bg=C_INPUT_BORDER, height=1)
        sep2.pack(fill=tk.X, pady=(8, 10))

        # Service checkbox
        svc_frame = tk.Frame(frame, bg=C_BG_DARK)
        svc_frame.pack(fill=tk.X, pady=(0, 4))
        svc_cb = tk.Checkbutton(
            svc_frame, text="Instalar como servicio de Windows (auto-inicio al iniciar sesión)",
            variable=self.create_service, font=("Segoe UI", 10),
            bg=C_BG_DARK, fg=C_TEXT, selectcolor=C_BG_DARK,
            activebackground=C_BG_DARK, activeforeground=C_TEXT,
            cursor="hand2"
        )
        svc_cb.pack(anchor=tk.W)

        # Tray checkbox
        tray_frame = tk.Frame(frame, bg=C_BG_DARK)
        tray_frame.pack(fill=tk.X, pady=(0, 4))
        tray_cb = tk.Checkbutton(
            tray_frame, text="Añadir icono de bandeja del sistema (control del servidor)",
            variable=self.auto_start_tray, font=("Segoe UI", 10),
            bg=C_BG_DARK, fg=C_TEXT, selectcolor=C_BG_DARK,
            activebackground=C_BG_DARK, activeforeground=C_TEXT,
            cursor="hand2"
        )
        tray_cb.pack(anchor=tk.W)

        return frame

    # ── Page 3: Installation Progress ─────────────────────────────────────
    def _build_page3(self) -> tk.Frame:
        frame = tk.Frame(self.pages_frame, bg=C_BG_DARK)

        tk.Label(
            frame, text="Instalando KinnyCode Memory System",
            font=("Segoe UI", 18, "bold"), bg=C_BG_DARK, fg=C_CYAN
        ).pack(anchor=tk.W, pady=(0, 4))

        self.status_label = tk.Label(
            frame, textvariable=self.status_var, font=("Segoe UI", 12),
            bg=C_BG_DARK, fg=C_TEXT_SEC, anchor=tk.W, justify=tk.LEFT
        )
        self.status_label.pack(fill=tk.X, pady=(2, 8))

        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "install.Horizontal.TProgressbar",
            background=C_CYAN, troughcolor=C_INPUT_BG, bordercolor=C_INPUT_BG,
            lightcolor=C_CYAN, darkcolor=C_CYAN
        )
        self.progress_bar = ttk.Progressbar(
            frame, variable=self.progress_var, maximum=100,
            style="install.Horizontal.TProgressbar", mode="determinate"
        )
        self.progress_bar.pack(fill=tk.X, pady=(0, 8))

        # Log text
        log_frame = tk.Frame(frame, bg=C_INPUT_BORDER)
        log_frame.pack(fill=tk.BOTH, expand=True)
        self.log_widget = tk.Text(
            log_frame, font=("Consolas", 10), bg=C_CARD, fg=C_TEXT_SEC,
            bd=0, relief=tk.FLAT, state=tk.DISABLED, wrap=tk.NONE,
            yscrollcommand=lambda *args: None, height=10
        )
        self.log_widget.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)

        # Scrollbar
        scrollbar = tk.Scrollbar(log_frame, command=self.log_widget.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_widget.configure(yscrollcommand=scrollbar.set)

        return frame

    # ── Page 4: Finish ────────────────────────────────────────────────────
    def _build_page4(self) -> tk.Frame:
        frame = tk.Frame(self.pages_frame, bg=C_BG_DARK)

        # Success checkmark
        canvas = tk.Canvas(frame, width=64, height=64, bg=C_BG_DARK, highlightthickness=0)
        canvas.create_oval(2, 2, 62, 62, fill=C_CYAN_DARK, outline="")
        canvas.create_text(32, 34, text="\u2714", font=("Segoe UI", 28, "bold"), fill=C_SUCCESS)
        canvas.pack(pady=(10, 8))

        tk.Label(
            frame, text="Instalación completada",
            font=("Segoe UI", 20, "bold"), bg=C_BG_DARK, fg=C_SUCCESS
        ).pack(pady=(0, 10))

        # Summary card
        card = tk.Frame(frame, bg=C_CARD, padx=16, pady=12)
        card.pack(fill=tk.X, padx=20)

        self.summary_vars = {
            "dir": tk.StringVar(value=""),
            "port": tk.StringVar(value=""),
            "cli": tk.StringVar(value=""),
            "svc": tk.StringVar(value=""),
            "tray": tk.StringVar(value=""),
            "opencode": tk.StringVar(value=""),
        }
        for key, var in self.summary_vars.items():
            tk.Label(
                card, textvariable=var, font=("Segoe UI", 10),
                bg=C_CARD, fg=C_TEXT_SEC, anchor=tk.W, justify=tk.LEFT
            ).pack(fill=tk.X, pady=1)

        # Next steps
        tk.Label(
            frame, text="\nPróximos pasos:",
            font=("Segoe UI", 12, "bold"), bg=C_BG_DARK, fg=C_CYAN
        ).pack(anchor=tk.W, padx=20)

        steps = [
            "1. kinnycode init      — Inicializa un proyecto",
            "2. kinnycode index     — Indexa los archivos del proyecto",
            "3. kinnycode search    — Realiza búsquedas semánticas",
        ]
        for s in steps:
            tk.Label(
                frame, text=s, font=("Consolas", 10), bg=C_BG_DARK,
                fg=C_TEXT_SEC, anchor=tk.W
            ).pack(anchor=tk.W, padx=20)

        # Launch tray button
        self.launch_btn_frame = tk.Frame(frame, bg=C_BG_DARK)
        self.launch_btn_frame.pack(pady=(16, 0))
        launch_btn = tk.Button(
            self.launch_btn_frame, text="Iniciar Sistema de Bandeja",
            font=("Segoe UI", 11, "bold"), bg=C_ORANGE, fg=C_WHITE,
            bd=0, activebackground=C_ORANGE_DARK, activeforeground=C_WHITE,
            cursor="hand2", padx=24, pady=8,
            command=lambda: self._finish_and_launch()
        )
        launch_btn.pack()

        return frame

    # ── Navigation Bar ────────────────────────────────────────────────────
    def _build_nav_bar(self):
        nav_frame = tk.Frame(self.root, bg=C_CARD, height=52)
        nav_frame.pack(fill=tk.X, side=tk.BOTTOM)
        nav_frame.pack_propagate(False)

        self.page_indicator = tk.Label(
            nav_frame, text="Paso 1 de 4", font=("Segoe UI", 10),
            bg=C_CARD, fg=C_TEXT_MUTED
        )
        self.page_indicator.pack(side=tk.LEFT, padx=14, pady=14)

        button_frame = tk.Frame(nav_frame, bg=C_CARD)
        button_frame.pack(side=tk.RIGHT, padx=12, pady=10)

        self.btn_prev = tk.Button(
            button_frame, text="\u2190 Anterior", font=("Segoe UI", 10),
            bg=C_INPUT_BG, fg=C_TEXT_SEC, bd=1, relief=tk.FLAT,
            activebackground=C_CARD, activeforeground=C_TEXT,
            cursor="hand2", command=self._go_prev, padx=10
        )

        self.btn_next = tk.Button(
            button_frame, text="Siguiente \u2192", font=("Segoe UI", 10, "bold"),
            bg=C_CYAN, fg=C_BG_DARK, bd=0, relief=tk.FLAT,
            activebackground=C_ORANGE, activeforeground=C_WHITE,
            cursor="hand2", command=self._go_next, padx=10
        )

        self.btn_install = tk.Button(
            button_frame, text="Instalar", font=("Segoe UI", 10, "bold"),
            bg=C_ORANGE, fg=C_WHITE, bd=0, relief=tk.FLAT,
            activebackground=C_ORANGE_DARK, activeforeground=C_WHITE,
            cursor="hand2", command=self._start_install, padx=10
        )

        self.btn_close_app = tk.Button(
            button_frame, text="Cerrar", font=("Segoe UI", 10, "bold"),
            bg=C_CYAN, fg=C_BG_DARK, bd=0, relief=tk.FLAT,
            activebackground=C_ORANGE, activeforeground=C_WHITE,
            cursor="hand2", command=self._on_close, padx=10
        )

        self.btn_retry = tk.Button(
            button_frame, text="Reintentar", font=("Segoe UI", 10, "bold"),
            bg=C_WARNING, fg=C_BG_DARK, bd=0, relief=tk.FLAT,
            cursor="hand2", command=self._retry_install, padx=10
        )

    # ── Page Navigation ───────────────────────────────────────────────────
    def _show_page(self, n: int):
        pages = [self.page1, self.page2, self.page3, self.page4]
        for i, p in enumerate(pages):
            if i == n:
                p.pack(fill=tk.BOTH, expand=True)
            else:
                p.pack_forget()

        self.current_page = n
        self.page_indicator.config(text=f"Paso {n + 1} de 4")

        # Button visibility
        self.btn_prev.pack_forget()
        self.btn_next.pack_forget()
        self.btn_install.pack_forget()
        self.btn_close_app.pack_forget()
        self.btn_retry.pack_forget()

        if n == 0:  # Welcome
            self.btn_next.pack(side=tk.LEFT, padx=(0, 4))
        elif n == 1:  # Config
            self.btn_prev.pack(side=tk.LEFT, padx=(0, 4))
            self.btn_install.pack(side=tk.LEFT, padx=(0, 4))
            # Run detection when landing on page 2
            self.root.after(100, self._run_detection)
        elif n == 2:  # Install progress
            # Nothing shown — install runs automatically
            pass
        elif n == 3:  # Finish
            self.btn_close_app.pack(side=tk.LEFT, padx=(0, 4))

    def _go_next(self):
        if self.current_page < 3:
            self._show_page(self.current_page + 1)

    def _go_prev(self):
        if self.current_page > 0:
            self._show_page(self.current_page - 1)

    # ── Detection ─────────────────────────────────────────────────────────
    def _run_detection(self):
        """Run opencode and Python detection on page 2."""
        # Opencode — find all
        self.all_opencodes = find_all_opencodes()
        if self.all_opencodes:
            self.opencode_found = True
            self.opencode_path = self.all_opencodes[0]["path"]
            count = len(self.all_opencodes)
            self.opencode_status_var.set(f"\u2714 {count} opencode detectado(s)")
            self.opencode_status_lbl.config(fg=C_SUCCESS)
            # Clear old list
            for w in self.opencode_list_frame.winfo_children():
                w.destroy()
            for oc in self.all_opencodes:
                src = oc.get("source", "")
                lbl = tk.Label(
                    self.opencode_list_frame,
                    text=f"    {oc['path']}  [{src}]",
                    font=("Consolas", 9), bg=C_BG_DARK, fg=C_TEXT_MUTED,
                    anchor=tk.W
                )
                lbl.pack(fill=tk.X)
        else:
            self.opencode_found = False
            self.opencode_path = ""
            self.opencode_status_var.set("\u2716 Opencode NO detectado")
            self.opencode_status_lbl.config(fg=C_WARNING)
            for w in self.opencode_list_frame.winfo_children():
                w.destroy()

        # Python — find all and populate combobox
        self.all_pythons = find_all_pythons()
        if self.all_pythons:
            self.python_found = True
            # Build display strings: "version  |  path  [source]"
            display_values = []
            for p in self.all_pythons:
                ver = p["version"]
                path = p["path"]
                src = p.get("source", "")
                display_values.append(f"{ver:30s} {path}  [{src}]")
            self.python_combo["values"] = display_values
            self.python_combo.current(0)
            self._on_python_selected()
        else:
            self.python_found = False
            self.python_cmd = ""
            self.python_combo["values"] = ["No se encontró Python 3.10+"]
            self.python_combo.current(0)
            self.python_status_var.set("\u2716 Python NO detectado — se requiere Python 3.10+")

    def _on_python_selected(self, event=None):
        """Handle Python combobox selection."""
        if not self.all_pythons:
            self.python_cmd = ""
            self.python_detail_var.set("")
            return
        idx = self.python_combo.current()
        if 0 <= idx < len(self.all_pythons):
            p = self.all_pythons[idx]
            self.python_cmd = p["path"]  # use full path for venv creation
            self.python_detail_var.set(f"Usando: {p['path']}")

    def _browse_dir(self):
        from tkinter import filedialog
        d = filedialog.askdirectory(
            title="Seleccionar directorio de instalación",
            initialdir=str(DEFAULT_INSTALL_DIR.parent)
        )
        if d:
            memory_dir = Path(d) / "memory"
            self.install_dir.set(str(memory_dir))

    # ── Installation ──────────────────────────────────────────────────────
    def _start_install(self):
        port_str = self.port.get()
        try:
            port = int(port_str)
            if port < 1 or port > 65535:
                messagebox.showwarning("Configuración", "El puerto debe estar entre 1 y 65535.")
                self.port.set(str(DEFAULT_PORT))
                return
        except ValueError:
            messagebox.showwarning("Configuración", "El puerto debe ser un número válido.")
            self.port.set(str(DEFAULT_PORT))
            return

        if not self.python_found:
            messagebox.showerror(
                "Error",
                "Python 3.10+ no encontrado.\n\n"
                "Instala Python desde https://www.python.org/downloads/\n"
                "y asegúrate de marcar 'Add Python to PATH'."
            )
            return

        self._show_page(2)
        self.install_log.clear()
        self.log_widget.config(state=tk.NORMAL)
        self.log_widget.delete("1.0", tk.END)
        self.log_widget.config(state=tk.DISABLED)
        self.progress_var.set(0)
        self.status_var.set("Preparando instalación...")

        self.install_thread = threading.Thread(target=self._run_install, daemon=True)
        self.install_thread.start()
        self._poll_install()

    def _log(self, msg: str):
        self.install_log.append(msg)

    def _flush_log(self):
        if self.install_log:
            self.log_widget.config(state=tk.NORMAL)
            for line in self.install_log:
                self.log_widget.insert(tk.END, line + "\n")
            self.install_log.clear()
            self.log_widget.see(tk.END)
            self.log_widget.config(state=tk.DISABLED)

    def _poll_install(self):
        self._flush_log()
        if self.install_thread and self.install_thread.is_alive():
            self.root.after(200, self._poll_install)
        else:
            self._flush_log()
            if self.install_success:
                self._show_page(3)
                self._populate_summary()
            else:
                # Error — show retry
                self.btn_retry.pack(side=tk.LEFT, padx=(0, 4))
                self.progress_bar.config(style="error.Horizontal.TProgressbar")
                # Make progress bar red
                s = ttk.Style()
                s.configure(
                    "error.Horizontal.TProgressbar",
                    background=C_ERROR, troughcolor=C_INPUT_BG
                )

    def _run_install(self):
        """Execute installation in background thread."""
        try:
            install_dir = Path(self.install_dir.get())
            port = int(self.port.get())
            python = self.python_cmd

            def status(msg: str):
                self.status_var.set(msg)

            def progress(val: int):
                self.progress_var.set(val)

            _sep = "═" * 56

            # ── Step 1: Create directories ────────────────────────────────
            status("Creando directorios de instalación...")
            progress(5)
            self._log(_sep)
            self._log("  PASO 1/6: Creando directorios")
            self._log(_sep)
            try:
                install_dir.mkdir(parents=True, exist_ok=True)
                self._log(f"  [OK] {install_dir}")
            except Exception as e:
                self._log(f"  [ERROR] No se pudo crear: {e}")
                raise
            progress(12)

            # ── Step 2: Create venv ───────────────────────────────────────
            status("Creando entorno virtual Python...")
            progress(15)
            self._log("")
            self._log(_sep)
            self._log("  PASO 2/6: Creando entorno virtual")
            self._log(_sep)
            venv_path = install_dir / ".venv"
            if not venv_path.exists():
                try:
                    result = subprocess.run(
                        [python, "-m", "venv", str(venv_path)],
                        capture_output=True, text=True, timeout=120
                    )
                    if result.returncode != 0:
                        self._log(f"  [ERROR] {result.stderr}")
                        raise RuntimeError("Error creando venv")
                    self._log(f"  [OK] Entorno virtual creado")
                except Exception as e:
                    self._log(f"  [ERROR] {e}")
                    raise
            else:
                self._log(f"  [i]  Entorno virtual ya existe")
            progress(20)

            python_exe = find_venv_python(venv_path)

            # ── Step 3: Install pip packages ──────────────────────────────
            status("Instalando dependencias Python (pip)...")
            progress(25)
            self._log("")
            self._log(_sep)
            self._log("  PASO 3/6: Instalando dependencias pip")
            self._log(_sep)

            req_src = SOURCE_DIR / "requirements.txt"
            req_dst = install_dir / "requirements.txt"
            if req_src.exists():
                import shutil
                shutil.copy2(str(req_src), str(req_dst))
                self._log("  [OK] requirements.txt copiado")
            else:
                self._log("  [!] requirements.txt no encontrado en origen")

            if req_dst.exists():
                self._log("  [*] Instalando paquetes (esto puede tardar varios minutos)...")
                try:
                    proc = subprocess.Popen(
                        [str(python_exe), "-m", "pip", "install", "-r", str(req_dst),
                         "--disable-pip-version-check", "--no-color", "--quiet"],
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                        text=True, cwd=str(install_dir)
                    )
                    elapsed = 0
                    for line in proc.stdout:
                        elapsed += 1
                        if elapsed % 5 == 0:
                            pct = min(25 + (elapsed // 5), 55)
                            progress(pct)
                            status(f"Instalando paquetes pip... ({elapsed * 0.5:.0f}s)")
                    proc.wait(timeout=600)
                    if proc.returncode != 0:
                        self._log(f"  [!] pip finalizó con código {proc.returncode}")
                    else:
                        self._log("  [OK] Dependencias instaladas")
                except Exception as e:
                    self._log(f"  [ERROR] {e}")
                    raise
            progress(58)

            # ── Step 4: Copy source files ─────────────────────────────────
            status("Copiando archivos de la aplicación...")
            progress(60)
            self._log("")
            self._log(_sep)
            self._log("  PASO 4/6: Copiando archivos fuente")
            self._log(_sep)

            import shutil

            files_to_copy = [
                "memory_server.py", "mcp_wrapper.py", "cli.py",
                "kinnycode_main.py", "requirements.txt", ".env.example", "opencode.json"
            ]
            for f in files_to_copy:
                src = SOURCE_DIR / f
                dst = install_dir / f
                if src.exists():
                    shutil.copy2(str(src), str(dst))
                    self._log(f"  [OK] {f}")
                else:
                    self._log(f"  [!] {f} no encontrado en origen")

            # Copy memory/ package
            memory_src = SOURCE_DIR / "memory"
            memory_dst = install_dir / "memory"
            if memory_src.is_dir():
                if memory_dst.exists():
                    shutil.rmtree(str(memory_dst), ignore_errors=True)
                shutil.copytree(str(memory_src), str(memory_dst))
                self._log("  [OK] memory/ (paquete completo)")
            else:
                self._log("  [!] memory/ no encontrado")

            # Copy assets/
            assets_src = SOURCE_DIR / "assets"
            assets_dst = install_dir / "assets"
            if assets_src.is_dir():
                if assets_dst.exists():
                    shutil.rmtree(str(assets_dst), ignore_errors=True)
                shutil.copytree(str(assets_src), str(assets_dst))
                self._log("  [OK] assets/ (iconos y logos)")

            # Copy the installer and tray scripts as well (for service setup)
            for extra in ["kinnycode_installer.py", "kinnycode_tray.py", "kinnycode_service.py"]:
                src = SOURCE_DIR / extra
                if src.exists():
                    shutil.copy2(str(src), str(install_dir / extra))

            progress(75)

            # ── Step 5: Create CLI launcher ───────────────────────────────
            status("Configurando comando CLI...")
            progress(78)
            self._log("")
            self._log(_sep)
            self._log("  PASO 5/6: Configurando CLI")
            self._log(_sep)

            local_bin = Path.home() / ".local" / "bin"
            local_bin.mkdir(parents=True, exist_ok=True)
            cli_script = install_dir / "cli.py"
            kinnycode_cmd = local_bin / "kinnycode.cmd"

            cmd_content = f'@echo off\r\n"{python_exe}" "{cli_script}" %*'
            kinnycode_cmd.write_text(cmd_content, encoding="ascii")
            self._log(f"  [OK] Creado: {kinnycode_cmd}")

            # Add to PATH
            try:
                import winreg
                user_path = ""
                try:
                    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_READ) as key:
                        user_path, _ = winreg.QueryValueEx(key, "PATH")
                except Exception:
                    pass

                if str(local_bin) not in user_path.split(";"):
                    new_path = user_path + ";" + str(local_bin) if user_path else str(local_bin)
                    try:
                        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_SET_VALUE) as key:
                            winreg.SetValueEx(key, "PATH", 0, winreg.REG_EXPAND_SZ, new_path)
                        self._log("  [OK] Añadido al PATH de usuario")
                    except Exception as e:
                        self._log(f"  [!] No se pudo añadir al PATH: {e}")
                else:
                    self._log("  [i]  Ya está en el PATH")
            except ImportError:
                self._log("  [i]  PATH actualizado solo en sesión actual")

            progress(88)

            # ── Step 6: Service + Tray ────────────────────────────────────
            status("Configurando servicio y bandeja del sistema...")
            progress(90)
            self._log("")
            self._log(_sep)
            self._log("  PASO 6/6: Configuración final")
            self._log(_sep)

            if self.create_service.get():
                try:
                    task_name = "KinnyCodeMemoryServer"
                    task_cmd = (
                        f'powershell -Command "'
                        f'$task = Get-ScheduledTask -TaskName \'{task_name}\' -ErrorAction SilentlyContinue; '
                        f'if ($task) {{ Unregister-ScheduledTask -TaskName \'{task_name}\' -Confirm:$false }}; '
                        f'$action = New-ScheduledTaskAction -Execute \'{python_exe}\' '
                        f'-Argument \'`"{cli_script}`" server start --port {port}\'; '
                        f'$trigger = New-ScheduledTaskTrigger -AtLogOn -User {os.environ.get("USERNAME", "")}; '
                        f'$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries '
                        f'-DontStopIfGoingOnBatteries -StartWhenAvailable -RestartCount 3 '
                        f'-RestartInterval (New-TimeSpan -Minutes 1); '
                        f'Register-ScheduledTask -TaskName \'{task_name}\' '
                        f'-Action $action -Trigger $trigger -Settings $settings '
                        f'-Description \'KinnyCode Memory Server\' -Force | Out-Null; '
                        f'Start-ScheduledTask -TaskName \'{task_name}\' -ErrorAction SilentlyContinue'
                        f'"'
                    )
                    result = subprocess.run(
                        ["powershell", "-Command", task_cmd],
                        capture_output=True, text=True, timeout=30
                    )
                    if result.returncode == 0:
                        self._log(f"  [OK] Servicio '{task_name}' configurado")
                    else:
                        self._log(f"  [!] {result.stderr.strip()}")
                except Exception as e:
                    self._log(f"  [!] Servicio: {e}")
            else:
                self._log("  [i]  Servicio no configurado (opción desmarcada)")

            if self.auto_start_tray.get():
                self._log("  [OK] Bandeja del sistema disponible tras reiniciar")
            else:
                self._log("  [i]  Bandeja del sistema no configurada")

            # Save install config to file
            config = {
                "install_dir": str(install_dir),
                "port": port,
                "python_exe": str(python_exe),
                "opencode_found": self.opencode_found,
                "opencode_path": self.opencode_path,
                "version": VERSION,
                "installed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            config_file = install_dir / "install_config.json"
            config_file.write_text(json.dumps(config, indent=2, ensure_ascii=False))

            # ── Write to Windows Registry ────────────────────────────────
            try:
                import kinnycode_registry as kr
                kr.write_install_config(
                    install_dir=str(install_dir),
                    port=port,
                    python_exe=str(python_exe),
                    tray_enabled=self.auto_start_tray.get(),
                    version=VERSION,
                )
                kr.register_uninstall(install_dir=str(install_dir), version=VERSION)
                self._log("  [OK] Registro de Windows actualizado")
                self._log("  [OK] Registrado en Agregar/Quitar Programas")
            except Exception as e:
                self._log(f"  [!] Registro: {e}")

            progress(100)
            status("Instalación completada.")
            self._log("")
            self._log(_sep)
            self._log("  INSTALACIÓN COMPLETADA CON ÉXITO")
            self._log(_sep)
            self._log(f"  Directorio: {install_dir}")
            self._log(f"  Puerto:     {port}")
            self._log(f"  CLI:        kinnycode")
            self._log(f"  API Docs:   http://127.0.0.1:{port}/docs")
            self._log(_sep)

            self.install_success = True

        except Exception as e:
            self._log(f"\n  [ERROR FATAL] {e}")
            self.install_success = False
            self.status_var.set(f"Error: {e}")

    def _populate_summary(self):
        install_dir = self.install_dir.get()
        port = self.port.get()
        svc = "Configurado (auto-inicio)" if self.create_service.get() else "No configurado"
        tray = "Sí" if self.auto_start_tray.get() else "No"
        opencode = f"Detectado: {self.opencode_path}" if self.opencode_found else "No detectado"

        self.summary_vars["dir"].set(f"Directorio:    {install_dir}")
        self.summary_vars["port"].set(f"Servidor:      http://127.0.0.1:{port}")
        self.summary_vars["cli"].set(f"CLI:           kinnycode (disponible en nueva terminal)")
        self.summary_vars["svc"].set(f"Servicio:      {svc}")
        self.summary_vars["tray"].set(f"Bandeja:       {tray}")
        self.summary_vars["opencode"].set(f"Opencode:      {opencode}")

        self._show_page(3)

    def _retry_install(self):
        self.btn_retry.pack_forget()
        self.install_success = False
        self._start_install()

    def _finish_and_launch(self):
        """Close wizard and optionally launch tray."""
        self.root.destroy()
        # Launch tray if requested
        if self.auto_start_tray.get():
            try:
                install_dir = Path(self.install_dir.get())
                port = int(self.port.get())
                launcher = install_dir / "kinnycode_tray.py"
                python_exe = find_venv_python(install_dir / ".venv")
                if launcher.exists() and python_exe.exists():
                    subprocess.Popen(
                        [str(python_exe), str(launcher), "--port", str(port),
                         "--install-dir", str(install_dir)],
                        creationflags=subprocess.DETACHED_PROCESS if hasattr(subprocess, "DETACHED_PROCESS") else 0,
                        close_fds=True
                    )
            except Exception:
                pass

    def _on_close(self):
        if self.install_thread and self.install_thread.is_alive():
            if messagebox.askyesno("Confirmar", "La instalación está en progreso. ¿Cancelar?"):
                pass
            else:
                return
        self.root.destroy()

    def run(self):
        self.root.mainloop()


# ═══════════════════════════════════════════════════════════════════════════
#  System Tray Application
# ═══════════════════════════════════════════════════════════════════════════

def launch_tray(install_dir: Path, port: int):
    """Launch the system tray application."""
    import subprocess
    launcher = install_dir / "kinnycode_tray.py"
    python_exe = find_venv_python(install_dir / ".venv")

    if launcher.exists() and python_exe.exists():
        subprocess.Popen(
            [str(python_exe), str(launcher), "--port", str(port),
             "--install-dir", str(install_dir)],
            creationflags=subprocess.DETACHED_PROCESS if hasattr(subprocess, "DETACHED_PROCESS") else 0,
            close_fds=True
        )
        return True
    return False


# ═══════════════════════════════════════════════════════════════════════════
#  Entry Point
# ═══════════════════════════════════════════════════════════════════════════

def main():
    """Entry point — decide between installer wizard, system tray, or uninstall."""
    import argparse

    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("--tray", action="store_true", help="Launch system tray directly")
    parser.add_argument("--uninstall", action="store_true", help="Run uninstaller")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Server port")
    parser.add_argument("--install-dir", type=str, help="Install directory")
    args = parser.parse_args()

    if args.uninstall:
        from kinnycode_uninstaller import UninstallerGUI
        install_dir = Path(args.install_dir) if args.install_dir else None
        gui = UninstallerGUI(install_dir)
        gui.run()
        return

    if args.tray:
        install_dir = Path(args.install_dir) if args.install_dir else DEFAULT_INSTALL_DIR
        port = args.port
        launch_tray(install_dir, port)
    elif is_installed():
        # Already installed — present options
        from tkinter import messagebox as _mb, Tk as _Tk
        root = _Tk()
        root.withdraw()
        result = _mb.askyesnocancel(
            APP_NAME,
            f"KinnyCode ya está instalado en {DEFAULT_INSTALL_DIR}.\n\n"
            "Selecciona una opción:\n\n"
            "  • Sí — Iniciar sistema de bandeja\n"
            "  • No — Reinstalar\n"
            "  • Cancelar — Salir",
            parent=root
        )
        root.destroy()
        if result is True:
            launch_tray(DEFAULT_INSTALL_DIR, DEFAULT_PORT)
        elif result is False:
            wizard = InstallerWizard()
            wizard.run()
        # result is None (Cancel) — just exit
    else:
        wizard = InstallerWizard()
        wizard.run()


if __name__ == "__main__":
    main()
