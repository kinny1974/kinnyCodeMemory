#!/usr/bin/env python3
"""
KinnyCode Memory System - Cross-Platform Installer
===================================================
GUI installer for Windows and Linux.
Allows selecting destination folder, port, network binding,
and service installation options.

Usage:
    python installer.py
"""

import os
import sys
import platform
import shutil
import subprocess
import json
from pathlib import Path
from typing import Optional

# ═══════════════════════════════════════════════════════════════════════
#  tkinter GUI
# ═══════════════════════════════════════════════════════════════════════

try:
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
    HAS_TKINTER = True
except ImportError:
    HAS_TKINTER = False


# ═══════════════════════════════════════════════════════════════════════
#  Constants
# ═══════════════════════════════════════════════════════════════════════

APP_NAME = "KinnyCode Memory System"
APP_VERSION = "1.0.0"
DEFAULT_PORT = 8007
DEFAULT_HOST = "127.0.0.1"
VENV_DIR = ".venv"
CONFIG_FILE = ".env"
SOURCE_DIR = Path(__file__).parent

PLATFORM = platform.system().lower()  # 'windows', 'linux', 'darwin'
FROZEN = getattr(sys, 'frozen', False)


# ═══════════════════════════════════════════════════════════════════════
#  Helpers for PyInstaller frozen mode
# ═══════════════════════════════════════════════════════════════════════


def _get_source_dir() -> Path:
    """Return the directory containing source files.

    When running from PyInstaller --onefile, ``__file__`` points to the
    temporary extraction folder which does NOT contain the project sources.
    In that case we fall back to the directory that holds the executable
    itself (i.e. where the user extracted the ZIP).
    """
    if FROZEN:
        return Path(sys.executable).parent
    return SOURCE_DIR


def _find_python3() -> str:
    """Find a usable ``python3`` (or ``python``) interpreter.

    PyInstaller bundles its own interpreter via ``sys.executable`` but that
    binary **cannot** be used to create virtual-environments.  We therefore
    search for a system Python on ``PATH``.
    """
    for name in ("python3", "python"):
        path = shutil.which(name)
        if path:
            return path
    # Last resort – hope sys.executable is real Python (native script mode)
    return sys.executable


# ═══════════════════════════════════════════════════════════════════════
#  Service Manager
# ═══════════════════════════════════════════════════════════════════════


class ServiceManager:
    """Manages system service installation for Windows and Linux."""

    @staticmethod
    def install_windows(target_dir: str, port: int, host: str) -> bool:
        """Install as Windows service using Task Scheduler."""
        try:
            service_name = "KinnyCodeMemory"
            python_exe = os.path.join(target_dir, VENV_DIR, "Scripts", "python.exe")
            server_script = os.path.join(target_dir, "memory_server.py")

            # Create batch file for service
            batch_content = f'''@echo off
cd /d "{target_dir}"
"{python_exe}" "{server_script}"
'''
            batch_path = os.path.join(target_dir, "start_service.bat")
            with open(batch_path, "w") as f:
                f.write(batch_content)

            # Create task via schtasks
            task_cmd = f'''
schtasks /create /tn "{service_name}" /tr "{batch_path}" /sc onstart /ru SYSTEM /rl HIGHEST /f
'''
            result = subprocess.run(
                task_cmd, shell=True, capture_output=True, text=True
            )
            return result.returncode == 0

        except Exception as e:
            print(f"Error installing Windows service: {e}")
            return False

    @staticmethod
    def install_linux(target_dir: str, port: int, host: str) -> bool:
        """Install as systemd service."""
        try:
            service_name = "kinnycodememory"
            python_exe = os.path.join(target_dir, VENV_DIR, "bin", "python3")
            server_script = os.path.join(target_dir, "memory_server.py")

            service_content = f'''[Unit]
Description=KinnyCode Memory System
After=network.target

[Service]
Type=simple
User={os.getenv('USER', 'root')}
WorkingDirectory={target_dir}
ExecStart={python_exe} {server_script}
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
'''
            service_path = f"/etc/systemd/system/{service_name}.service"
            with open(service_path, "w") as f:
                f.write(service_content)

            # Enable and start service
            subprocess.run(["systemctl", "daemon-reload"], check=True)
            subprocess.run(["systemctl", "enable", service_name], check=True)
            subprocess.run(["systemctl", "start", service_name], check=True)

            return True

        except Exception as e:
            print(f"Error installing Linux service: {e}")
            return False

    @staticmethod
    def uninstall_windows() -> bool:
        """Remove Windows service."""
        try:
            subprocess.run(
                'schtasks /delete /tn "KinnyCodeMemory" /f',
                shell=True, capture_output=True
            )
            return True
        except Exception:
            return False

    @staticmethod
    def uninstall_linux() -> bool:
        """Remove systemd service."""
        try:
            service_name = "kinnycodememory"
            subprocess.run(["systemctl", "stop", service_name], capture_output=True)
            subprocess.run(["systemctl", "disable", service_name], capture_output=True)
            service_path = f"/etc/systemd/system/{service_name}.service"
            if os.path.exists(service_path):
                os.remove(service_path)
            subprocess.run(["systemctl", "daemon-reload"], capture_output=True)
            return True
        except Exception:
            return False


# ═══════════════════════════════════════════════════════════════════════
#  Installer Core
# ═══════════════════════════════════════════════════════════════════════


class KinnyCodeInstaller:
    """Main installer logic."""

    def __init__(self):
        self.target_dir: Optional[str] = None
        self.port: int = DEFAULT_PORT
        self.host: str = DEFAULT_HOST
        self.install_service: bool = False
        self.install_shortcut: bool = True
        self.progress_callback = None

    def set_progress_callback(self, callback):
        """Set callback for progress updates."""
        self.progress_callback = callback

    def _report(self, message: str, progress: int = 0):
        """Report progress."""
        if self.progress_callback:
            self.progress_callback(message, progress)
        else:
            print(f"[{progress}%] {message}")

    def validate_target(self, path: str) -> tuple[bool, str]:
        """Validate target directory."""
        if not path:
            return False, "Selecciona una carpeta de destino"

        target = Path(path)
        if target.exists():
            # Check if it's writable
            try:
                test_file = target / ".write_test"
                test_file.write_text("test")
                test_file.unlink()
            except PermissionError:
                return False, "No hay permisos de escritura en esta carpeta"
        else:
            # Check parent is writable
            try:
                target.mkdir(parents=True, exist_ok=True)
            except PermissionError:
                return False, "No hay permisos para crear la carpeta"

        return True, "OK"

    def validate_port(self, port: int) -> tuple[bool, str]:
        """Validate port number."""
        if not (1024 <= port <= 65535):
            return False, "Puerto debe estar entre 1024 y 65535"
        return True, "OK"

    def copy_files(self, target_dir: str) -> bool:
        """Copy application files to target directory."""
        target = Path(target_dir)
        source = _get_source_dir()

        # Files and directories to copy
        items_to_copy = [
            "memory_server.py",
            "mcp_wrapper.py",
            "cli.py",
            "kinnycode_main.py",
            "memory/",
            "assets/",
            "requirements.txt",
            ".env.example",
            "AGENTS.md",
        ]

        for item in items_to_copy:
            src = source / item
            dst = target / item

            if src.is_dir():
                if dst.exists():
                    shutil.rmtree(dst)
                shutil.copytree(src, dst)
                self._report(f"Copiando {item}/...", 0)
            elif src.is_file():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                self._report(f"Copiando {item}...", 0)
            else:
                self._report(f"Saltando {item} (no encontrado)", 0)

        return True

    def create_venv(self, target_dir: str) -> bool:
        """Create virtual environment and install dependencies."""
        target = Path(target_dir)
        venv_path = target / VENV_DIR

        self._report("Creando entorno virtual...", 30)

        # Create venv — use system Python, NOT sys.executable from PyInstaller
        python3 = _find_python3()
        subprocess.run(
            [python3, "-m", "venv", str(venv_path)],
            check=True, capture_output=True
        )

        # Determine pip path
        if PLATFORM == "windows":
            pip_exe = venv_path / "Scripts" / "pip.exe"
        else:
            pip_exe = venv_path / "bin" / "pip"

        self._report("Instalando dependencias...", 50)

        # Upgrade pip first
        subprocess.run(
            [str(pip_exe), "install", "--upgrade", "pip"],
            capture_output=True
        )

        # Install requirements
        req_file = target / "requirements.txt"
        if req_file.exists():
            subprocess.run(
                [str(pip_exe), "install", "-r", str(req_file)],
                capture_output=True
            )

        self._report("Dependencias instaladas", 70)
        return True

    def create_config(self, target_dir: str) -> bool:
        """Create initial configuration file."""
        target = Path(target_dir)
        config_path = target / CONFIG_FILE

        env_example = target / ".env.example"
        if env_example.exists():
            config_content = env_example.read_text()
        else:
            config_content = "# KinnyCode Memory System Configuration\n"

        # Update config with user selections
        config_content += f"\n# Installer Configuration\n"
        config_content += f"KINNYCODE_PORT={self.port}\n"
        config_content += f"KINNYCODE_HOST={self.host}\n"
        config_content += f"KINNYCODE_DIR={target_dir}\n"

        config_path.write_text(config_content)
        self._report("Configuración creada", 80)
        return True

    def create_shortcut(self, target_dir: str) -> bool:
        """Create desktop shortcut."""
        if PLATFORM == "windows":
            return self._create_windows_shortcut(target_dir)
        elif PLATFORM == "linux":
            return self._create_linux_shortcut(target_dir)
        return False

    def _create_windows_shortcut(self, target_dir: str) -> bool:
        """Create Windows desktop shortcut."""
        try:
            desktop = Path(os.path.expanduser("~/Desktop"))
            shortcut_path = desktop / "KinnyCode Memory System.lnk"

            # Create VBS script to make shortcut
            vbs_content = f'''
Set WshShell = WScript.CreateObject("WScript.Shell")
Set shortcut = WshShell.CreateShortcut("{shortcut_path}")
shortcut.TargetPath = "{target_dir}\\start_service.bat"
shortcut.WorkingDirectory = "{target_dir}"
shortcut.Description = "KinnyCode Memory System"
shortcut.Save
'''
            vbs_path = target_dir / "_create_shortcut.vbs"
            vbs_path.write_text(vbs_content)

            subprocess.run(["cscript", str(vbs_path)], capture_output=True)
            vbs_path.unlink()

            return True
        except Exception as e:
            print(f"Error creating shortcut: {e}")
            return False

    def _create_linux_shortcut(self, target_dir: str) -> bool:
        """Create Linux .desktop file."""
        try:
            desktop_dir = Path(os.path.expanduser("~/Desktop"))
            desktop_file = desktop_dir / "kinnycodememory.desktop"

            content = f'''[Desktop Entry]
Name=KinnyCode Memory System
Comment=Multi-layer memory system with RAG
Exec={target_dir}/{VENV_DIR}/bin/python {target_dir}/memory_server.py
Icon={target_dir}/assets/icon.png
Terminal=true
Type=Application
Categories=Development;
'''
            desktop_file.write_text(content)
            os.chmod(desktop_file, 0o755)

            return True
        except Exception as e:
            print(f"Error creating shortcut: {e}")
            return False

    def install(self) -> bool:
        """Run full installation."""
        try:
            self._report("Iniciando instalación...", 0)

            # Validate
            valid, msg = self.validate_target(self.target_dir)
            if not valid:
                self._report(f"Error: {msg}", 0)
                return False

            valid, msg = self.validate_port(self.port)
            if not valid:
                self._report(f"Error: {msg}", 0)
                return False

            # Copy files
            self._report("Copiando archivos...", 10)
            self.copy_files(self.target_dir)

            # Create venv and install deps
            self.create_venv(self.target_dir)

            # Create config
            self.create_config(self.target_dir)

            # Create shortcut
            if self.install_shortcut:
                self._report("Creando acceso directo...", 85)
                self.create_shortcut(self.target_dir)

            # Install service
            if self.install_service:
                self._report("Instalando servicio...", 90)
                if PLATFORM == "windows":
                    ServiceManager.install_windows(
                        self.target_dir, self.port, self.host
                    )
                elif PLATFORM == "linux":
                    ServiceManager.install_linux(
                        self.target_dir, self.port, self.host
                    )

            self._report("Instalación completada!", 100)
            return True

        except Exception as e:
            self._report(f"Error durante instalación: {e}", 0)
            return False


# ═══════════════════════════════════════════════════════════════════════
#  GUI
# ═══════════════════════════════════════════════════════════════════════


class InstallerGUI:
    """Tkinter GUI for the installer."""

    def __init__(self):
        self.installer = KinnyCodeInstaller()
        self.root = tk.Tk()
        self.root.title(f"{APP_NAME} - Instalador v{APP_VERSION}")
        self.root.geometry("600x550")
        self.root.resizable(False, False)

        # Center window
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth() - 600) // 2
        y = (self.root.winfo_screenheight() - 550) // 2
        self.root.geometry(f"+{x}+{y}")

        self._create_widgets()

    def _create_widgets(self):
        """Create all GUI widgets."""
        # Main frame
        main_frame = ttk.Frame(self.root, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Title
        title_label = ttk.Label(
            main_frame,
            text=APP_NAME,
            font=("Segoe UI", 16, "bold")
        )
        title_label.pack(pady=(0, 5))

        subtitle_label = ttk.Label(
            main_frame,
            text=f"Instalador v{APP_VERSION} — {PLATFORM.title()}",
            font=("Segoe UI", 10)
        )
        subtitle_label.pack(pady=(0, 20))

        # Notebook for sections
        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        # ── Tab 1: Destination ──
        tab_dest = ttk.Frame(notebook, padding="15")
        notebook.add(tab_dest, text=" Destino ")

        ttk.Label(tab_dest, text="Carpeta de destino:").pack(anchor=tk.W)
        dest_frame = ttk.Frame(tab_dest)
        dest_frame.pack(fill=tk.X, pady=(5, 15))

        self.dest_var = tk.StringVar(
            value=str(Path.home() / "KinnyCodeMemory")
        )
        dest_entry = ttk.Entry(dest_frame, textvariable=self.dest_var, width=50)
        dest_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))

        ttk.Button(
            dest_frame, text="Examinar...", command=self._browse_folder
        ).pack(side=tk.RIGHT)

        # ── Tab 2: Network ──
        tab_network = ttk.Frame(notebook, padding="15")
        notebook.add(tab_network, text=" Red ")

        ttk.Label(tab_network, text="Puerto del servidor:").pack(anchor=tk.W)
        self.port_var = tk.StringVar(value=str(DEFAULT_PORT))
        port_entry = ttk.Entry(
            tab_network, textvariable=self.port_var, width=10
        )
        port_entry.pack(anchor=tk.W, pady=(5, 15))

        ttk.Label(tab_network, text="Escuchar en:").pack(anchor=tk.W)
        self.host_var = tk.StringVar(value=DEFAULT_HOST)
        host_frame = ttk.Frame(tab_network)
        host_frame.pack(fill=tk.X, pady=(5, 15))

        ttk.Radiobutton(
            host_frame, text="Solo localhost (127.0.0.1)",
            variable=self.host_var, value="127.0.0.1"
        ).pack(anchor=tk.W)
        ttk.Radiobutton(
            host_frame, text="Todas las redes (0.0.0.0)",
            variable=self.host_var, value="0.0.0.0"
        ).pack(anchor=tk.W)

        # ── Tab 3: Options ──
        tab_options = ttk.Frame(notebook, padding="15")
        notebook.add(tab_options, text=" Opciones ")

        self.service_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            tab_options,
            text="Instalar como servicio del sistema",
            variable=self.service_var
        ).pack(anchor=tk.W, pady=(0, 10))

        self.shortcut_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            tab_options,
            text="Crear acceso directo en el escritorio",
            variable=self.shortcut_var
        ).pack(anchor=tk.W, pady=(0, 10))

        # Service note
        service_note = ttk.Label(
            tab_options,
            text="Nota: El servicio se ejecutará automáticamente al iniciar el sistema.",
            foreground="gray"
        )
        service_note.pack(anchor=tk.W)

        # ── Progress ──
        progress_frame = ttk.Frame(main_frame)
        progress_frame.pack(fill=tk.X, pady=(0, 10))

        self.progress_var = tk.StringVar(value="Listo para instalar")
        ttk.Label(progress_frame, textvariable=self.progress_var).pack(anchor=tk.W)

        self.progress_bar = ttk.Progressbar(
            progress_frame, mode="determinate", length=400
        )
        self.progress_bar.pack(fill=tk.X, pady=(5, 0))

        # ── Buttons ──
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X)

        ttk.Button(
            btn_frame, text="Cancelar", command=self.root.destroy
        ).pack(side=tk.RIGHT, padx=(5, 0))

        ttk.Button(
            btn_frame, text="Instalar", command=self._install
        ).pack(side=tk.RIGHT)

        ttk.Button(
            btn_frame, text="Desinstalar servicio", command=self._uninstall_service
        ).pack(side=tk.LEFT)

    def _browse_folder(self):
        """Open folder browser dialog."""
        folder = filedialog.askdirectory(
            title="Seleccionar carpeta de destino"
        )
        if folder:
            self.dest_var.set(folder)

    def _update_progress(self, message: str, progress: int):
        """Update progress bar and message."""
        self.progress_var.set(message)
        self.progress_bar["value"] = progress
        self.root.update_idletasks()

    def _install(self):
        """Run installation."""
        # Gather settings
        self.installer.target_dir = self.dest_var.get()

        try:
            self.installer.port = int(self.port_var.get())
        except ValueError:
            messagebox.showerror("Error", "Puerto inválido")
            return

        self.installer.host = self.host_var.get()
        self.installer.install_service = self.service_var.get()
        self.installer.install_shortcut = self.shortcut_var.get()

        # Set progress callback
        self.installer.set_progress_callback(self._update_progress)

        # Run installation
        self.root.config(cursor="watch")
        success = self.installer.install()
        self.root.config(cursor="")

        if success:
            messagebox.showinfo(
                "Instalación Completada",
                f"{APP_NAME} se instaló correctamente en:\n\n"
                f"{self.installer.target_dir}\n\n"
                f"Servidor disponible en: http://{self.installer.host}:{self.installer.port}"
            )
            self.root.destroy()
        else:
            messagebox.showerror(
                "Error de Instalación",
                "Hubo un error durante la instalación.\n"
                "Revisa la consola para más detalles."
            )

    def _uninstall_service(self):
        """Uninstall system service."""
        if PLATFORM == "windows":
            ServiceManager.uninstall_windows()
        elif PLATFORM == "linux":
            ServiceManager.uninstall_linux()
        messagebox.showinfo("Desinstalar", "Servicio desinstalado correctamente")

    def run(self):
        """Start the GUI."""
        self.root.mainloop()


# ═══════════════════════════════════════════════════════════════════════
#  CLI Installer (fallback without GUI)
# ═══════════════════════════════════════════════════════════════════════


class InstallerCLI:
    """Command-line installer for headless systems."""

    def __init__(self):
        self.installer = KinnyCodeInstaller()

    def run(self):
        """Run interactive CLI installation."""
        print(f"\n{'='*60}")
        print(f"  {APP_NAME} — Instalador CLI v{APP_VERSION}")
        print(f"{'='*60}\n")

        # Get target directory
        default_dir = str(Path.home() / "KinnyCodeMemory")
        target = input(f"Carpeta de destino [{default_dir}]: ").strip()
        self.installer.target_dir = target or default_dir

        # Get port
        port_str = input(f"Puerto [{DEFAULT_PORT}]: ").strip()
        self.installer.port = int(port_str) if port_str else DEFAULT_PORT

        # Get host
        print("\nOpciones de red:")
        print("  1) Solo localhost (127.0.0.1) - Recomendado para desarrollo")
        print("  2) Todas las redes (0.0.0.0) - Accesible desde otros equipos")
        host_choice = input("Selección [1]: ").strip()
        self.installer.host = "0.0.0.0" if host_choice == "2" else DEFAULT_HOST

        # Service installation
        service = input("\n¿Instalar como servicio del sistema? (s/N): ").strip()
        self.installer.install_service = service.lower() == "s"

        # Shortcut
        shortcut = input("¿Crear acceso directo? (S/n): ").strip()
        self.installer.install_shortcut = shortcut.lower() != "n"

        # Confirm
        print(f"\n{'─'*60}")
        print(f"Destino:     {self.installer.target_dir}")
        print(f"Puerto:      {self.installer.port}")
        print(f"Host:        {self.installer.host}")
        print(f"Servicio:    {'Sí' if self.installer.install_service else 'No'}")
        print(f"Shortcut:    {'Sí' if self.installer.install_shortcut else 'No'}")
        print(f"{'─'*60}")

        confirm = input("\n¿Proceder con la instalación? (S/n): ").strip()
        if confirm.lower() == "n":
            print("Instalación cancelada.")
            return

        # Set progress callback
        self.installer.set_progress_callback(
            lambda msg, prog: print(f"  [{prog:3d}%] {msg}")
        )

        # Run
        success = self.installer.install()

        if success:
            print(f"\n{'='*60}")
            print(f"  ¡Instalación completada!")
            print(f"  Servidor: http://{self.installer.host}:{self.installer.port}")
            print(f"{'='*60}\n")
        else:
            print("\nError durante la instalación.")


# ═══════════════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════════════


def main():
    """Entry point."""
    if "--cli" in sys.argv or not HAS_TKINTER:
        installer = InstallerCLI()
        installer.run()
    else:
        app = InstallerGUI()
        app.run()


if __name__ == "__main__":
    main()
