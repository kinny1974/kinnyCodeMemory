#!/usr/bin/env python3
"""
KinnyCode Memory System - Build Script
=======================================
Creates standalone executables for Windows (.exe) and Linux (.run)

Usage:
    python build.py                    # Build for current platform
    python build.py --installer        # Build installer with GUI
    python build.py --tray             # Build system tray app
    python build.py --all              # Build everything
    python build.py --clean            # Clean build artifacts
"""

import os
import sys
import shutil
import subprocess
import platform
from pathlib import Path

# ═══════════════════════════════════════════════════════════════════════
#  Configuration
# ═══════════════════════════════════════════════════════════════════════

APP_NAME = "KinnyCodeMemory"
APP_VERSION = "1.0.0"
BUILD_DIR = Path(__file__).parent / "build"
DIST_DIR = Path(__file__).parent / "dist"
ICON_PATH = Path(__file__).parent / "assets" / "icon.ico"

PLATFORM = platform.system().lower()


# ═══════════════════════════════════════════════════════════════════════
#  PyInstaller Builder
# ═══════════════════════════════════════════════════════════════════════


class PyInstallerBuilder:
    """Handles PyInstaller builds."""

    def __init__(self):
        self.pyinstaller = self._find_pyinstaller()

    def _find_pyinstaller(self) -> str:
        """Find PyInstaller executable."""
        # Try to find in venv
        if PLATFORM == "windows":
            venv_pyinstaller = Path(__file__).parent / ".venv" / "Scripts" / "pyinstaller.exe"
        else:
            venv_pyinstaller = Path(__file__).parent / ".venv" / "bin" / "pyinstaller"

        if venv_pyinstaller.exists():
            return str(venv_pyinstaller)

        # Try system-wide
        try:
            subprocess.run(
                [sys.executable, "-m", "PyInstaller", "--version"],
                capture_output=True,
                check=True
            )
            return f"{sys.executable} -m PyInstaller"
        except (subprocess.CalledProcessError, FileNotFoundError):
            raise RuntimeError(
                "PyInstaller not found. Install with: pip install pyinstaller"
            )

    def _run_pyinstaller(self, args: list[str]):
        """Run PyInstaller with arguments."""
        if " -m PyInstaller" in self.pyinstaller:
            cmd = [sys.executable, "-m", "PyInstaller"] + args
        else:
            cmd = [self.pyinstaller] + args

        print(f"Running: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            print(f"Error: {result.stderr}")
            raise RuntimeError("PyInstaller build failed")

        print(result.stdout)
        return result

    def build_server(self):
        """Build memory server executable."""
        print(f"\n{'='*60}")
        print(f"  Building {APP_NAME} Server")
        print(f"{'='*60}\n")

        args = [
            "--name", APP_NAME,
            "--onefile",
            "--console",
            "--noconfirm",
            "--clean",
            "--strip",
            # Exclude heavy unnecessary modules
            "--exclude-module", "tkinter",
            "--exclude-module", "matplotlib",
            "--exclude-module", "scipy",
            "--exclude-module", "numpy.tests",
            "--exclude-module", "pandas.tests",
            "--exclude-module", "torch.distributed",
            "--exclude-module", "torch.testing",
            # Hidden imports
            "--hidden-import", "uvicorn.logging",
            "--hidden-import", "uvicorn.loops",
            "--hidden-import", "uvicorn.protocols.http",
            "--hidden-import", "uvicorn.protocols.websockets",
            "--hidden-import", "uvicorn.lifespan",
            "--hidden-import", "lancedb",
            "--hidden-import", "sentence_transformers",
            "--hidden-import", "fastapi",
            "--hidden-import", "pydantic",
            # Collect data files
            "--collect-data", "lancedb",
            "--collect-data", "sentence_transformers",
        ]

        # Add icon if exists
        if ICON_PATH.exists():
            args.extend(["--icon", str(ICON_PATH)])

        # Add runtime hook for imports
        args.extend([
            "--runtime-hook", str(self._create_runtime_hook()),
        ])

        # Entry point
        args.append("memory_server.py")

        self._run_pyinstaller(args)

        # Rename output
        src = DIST_DIR / ("memory_server.exe" if PLATFORM == "windows" else "memory_server")
        dst = DIST_DIR / (f"{APP_NAME}-Server.exe" if PLATFORM == "windows" else f"{APP_NAME}-Server")

        if src.exists():
            src.rename(dst)
            print(f"\n[OK] Built: {dst}")

    def build_installer(self):
        """Build installer with GUI."""
        print(f"\n{'='*60}")
        print(f"  Building {APP_NAME} Installer")
        print(f"{'='*60}\n")

        args = [
            "--name", f"{APP_NAME}-Installer",
            "--onefile",
            "--windowed",  # No console window
            "--noconfirm",
            "--clean",
            # Hidden imports
            "--hidden-import", "tkinter",
            "--hidden-import", "tkinter.ttk",
            "--hidden-import", "tkinter.filedialog",
            "--hidden-import", "tkinter.messagebox",
        ]

        # Add icon if exists
        if ICON_PATH.exists():
            args.extend(["--icon", str(ICON_PATH)])

        # Entry point
        args.append("installer.py")

        self._run_pyinstaller(args)

        # Rename output
        ext = ".exe" if PLATFORM == "windows" else ""
        src = DIST_DIR / f"{APP_NAME}-Installer{ext}"
        dst = DIST_DIR / f"{APP_NAME}-Installer-v{APP_VERSION}{ext}"

        if src.exists():
            src.rename(dst)
            print(f"\n[OK] Built: {dst}")

    def build_tray(self):
        """Build system tray application."""
        print(f"\n{'='*60}")
        print(f"  Building {APP_NAME} System Tray")
        print(f"{'='*60}\n")

        args = [
            "--name", f"{APP_NAME}-Tray",
            "--onefile",
            "--windowed",  # No console window
            "--noconfirm",
            "--clean",
            # Hidden imports
            "--hidden-import", "pystray",
            "--hidden-import", "PIL",
            "--hidden-import", "PIL.Image",
            "--hidden-import", "PIL.ImageDraw",
            "--hidden-import", "PIL.ImageFont",
            "--hidden-import", "httpx",
        ]

        # Add icon if exists
        if ICON_PATH.exists():
            args.extend(["--icon", str(ICON_PATH)])

        # Entry point
        args.append("tray_app.py")

        self._run_pyinstaller(args)

        # Rename output
        ext = ".exe" if PLATFORM == "windows" else ""
        src = DIST_DIR / f"{APP_NAME}-Tray{ext}"
        dst = DIST_DIR / f"{APP_NAME}-Tray-v{APP_VERSION}{ext}"

        if src.exists():
            src.rename(dst)
            print(f"\n[OK] Built: {dst}")

    def build_web_ui(self):
        """Build Web UI server."""
        print(f"\n{'='*60}")
        print(f"  Building {APP_NAME} Web UI")
        print(f"{'='*60}\n")

        # Create a wrapper script that imports web_app
        wrapper_content = '''#!/usr/bin/env python3
"""Wrapper for Web UI"""
import sys
import os

# Add web directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'web'))

# Import and run
from web_app import app
import uvicorn

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=19090)
'''
        wrapper_path = BUILD_DIR / "web_ui_wrapper.py"
        wrapper_path.parent.mkdir(exist_ok=True)
        wrapper_path.write_text(wrapper_content)

        args = [
            "--name", f"{APP_NAME}-WebUI",
            "--onefile",
            "--console",
            "--noconfirm",
            "--clean",
            # Hidden imports
            "--hidden-import", "fastapi",
            "--hidden-import", "uvicorn",
            "--hidden-import", "jinja2",
            "--hidden-import", "httpx",
            "--hidden-import", "multipart",
            # Collect data files (templates)
            "--add-data", f"web/templates{os.pathsep}web/templates",
            "--add-data", f"web/static{os.pathsep}web/static",
        ]

        # Add icon if exists
        if ICON_PATH.exists():
            args.extend(["--icon", str(ICON_PATH)])

        # Entry point
        args.append(str(wrapper_path))

        self._run_pyinstaller(args)

        # Rename output
        ext = ".exe" if PLATFORM == "windows" else ""
        src = DIST_DIR / f"{APP_NAME}-WebUI{ext}"
        dst = DIST_DIR / f"{APP_NAME}-WebUI-v{APP_VERSION}{ext}"

        if src.exists():
            src.rename(dst)
            print(f"\n[OK] Built: {dst}")

    def _create_runtime_hook(self) -> Path:
        """Create runtime hook for imports."""
        hook_content = '''
import sys
import os

# Ensure memory package is importable
memory_dir = os.path.join(os.path.dirname(sys.executable), 'memory')
if os.path.exists(memory_dir):
    sys.path.insert(0, os.path.dirname(memory_dir))
'''
        hook_path = BUILD_DIR / "runtime_hook.py"
        hook_path.parent.mkdir(exist_ok=True)
        hook_path.write_text(hook_content)
        return hook_path


# ═══════════════════════════════════════════════════════════════════════
#  NSIS Installer Builder (Windows)
# ═══════════════════════════════════════════════════════════════════════


class NSISBuilder:
    """Creates Windows installer using NSIS."""

    def __init__(self):
        self.nsis = self._find_nsis()

    def _find_nsis(self) -> str:
        """Find NSIS executable."""
        possible_paths = [
            r"C:\Program Files (x86)\NSIS\makensis.exe",
            r"C:\Program Files\NSIS\makensis.exe",
            "makensis.exe",  # In PATH
        ]

        for path in possible_paths:
            if os.path.exists(path):
                return path

        return None

    def create_installer(self):
        """Create Windows installer."""
        if not self.nsis:
            print("NSIS not found. Skipping Windows installer creation.")
            print("Install NSIS from: https://nsis.sourceforge.io/")
            return

        print(f"\n{'='*60}")
        print(f"  Creating Windows Installer")
        print(f"{'='*60}\n")

        # Generate NSIS script
        nsis_script = self._generate_nsis_script()
        script_path = BUILD_DIR / "installer.nsi"
        script_path.write_text(nsis_script)

        # Run NSIS
        result = subprocess.run(
            [self.nsis, str(script_path)],
            capture_output=True,
            text=True
        )

        if result.returncode == 0:
            installer_path = DIST_DIR / f"{APP_NAME}-Setup-v{APP_VERSION}.exe"
            print(f"\n[OK] Installer created: {installer_path}")
        else:
            print(f"Error: {result.stderr}")

    def _generate_nsis_script(self) -> str:
        """Generate NSIS installer script."""
        return f'''
!include "MUI2.nsh"

; General
Name "{APP_NAME}"
OutFile "{DIST_DIR}\\{APP_NAME}-Setup-v{APP_VERSION}.exe"
InstallDir "$PROGRAMFILES\\{APP_NAME}"
InstallDirRegKey HKLM "Software\\{APP_NAME}" "InstallDir"

; Interface
!define MUI_ABORTWARNING
!define MUI_ICON "${{ICON_PATH}}"

; Pages
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "LICENSE.txt"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

; Languages
!insertmacro MUI_LANGUAGE "Spanish"

; Installer Sections
Section "Instalar"
    SetOutPath "$INSTDIR"

    ; Copy files
    File "{DIST_DIR}\\{APP_NAME}-Server.exe"
    File "{DIST_DIR}\\{APP_NAME}-Installer.exe"
    File "{DIST_DIR}\\{APP_NAME}-Tray.exe"
    File "{DIST_DIR}\\{APP_NAME}-WebUI.exe"

    ; Copy web UI templates
    SetOutPath "$INSTDIR\\web"
    File /r "web\\templates\\*.*"

    ; Create uninstaller
    WriteUninstaller "$INSTDIR\\Uninstall.exe"

    ; Registry
    WriteRegStr HKLM "Software\\{APP_NAME}" "InstallDir" "$INSTDIR"
    WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{APP_NAME}" "DisplayName" "{APP_NAME}"
    WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{APP_NAME}" "UninstallString" '"$INSTDIR\\Uninstall.exe"'

    ; Create shortcuts
    CreateDirectory "$SMPROGRAMS\\{APP_NAME}"
    CreateShortCut "$SMPROGRAMS\\{APP_NAME}\\{APP_NAME}.lnk" "$INSTDIR\\{APP_NAME}-Tray.exe"
    CreateShortCut "$SMPROGRAMS\\{APP_NAME}\\Uninstall.lnk" "$INSTDIR\\Uninstall.exe"
    CreateShortCut "$DESKTOP\\{APP_NAME}.lnk" "$INSTDIR\\{APP_NAME}-Tray.exe"
SectionEnd

; Uninstaller Section
Section "Desinstalar"
    Delete "$INSTDIR\\{APP_NAME}-Server.exe"
    Delete "$INSTDIR\\{APP_NAME}-Installer.exe"
    Delete "$INSTDIR\\{APP_NAME}-Tray.exe"
    Delete "$INSTDIR\\{APP_NAME}-WebUI.exe"
    Delete "$INSTDIR\\Uninstall.exe"
    RMDir /r "$INSTDIR\\web"
    RMDir "$INSTDIR"

    Delete "$SMPROGRAMS\\{APP_NAME}\\{APP_NAME}.lnk"
    Delete "$SMPROGRAMS\\{APP_NAME}\\Uninstall.lnk"
    RMDir "$SMPROGRAMS\\{APP_NAME}"
    Delete "$DESKTOP\\{APP_NAME}.lnk"

    DeleteRegKey HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{APP_NAME}"
    DeleteRegKey HKLM "Software\\{APP_NAME}"
SectionEnd
'''


# ═══════════════════════════════════════════════════════════════════════
#  Linux AppImage Builder
# ═══════════════════════════════════════════════════════════════════════


class AppImageBuilder:
    """Creates Linux AppImage."""

    def create_appimage(self):
        """Create AppImage package."""
        print(f"\n{'='*60}")
        print(f"  Creating Linux AppImage")
        print(f"{'='*60}\n")

        # Create AppDir structure
        appdir = BUILD_DIR / "AppDir"
        appdir.mkdir(parents=True, exist_ok=True)

        # Create desktop file
        desktop_content = f'''[Desktop Entry]
Type=Application
Name={APP_NAME}
Exec={APP_NAME}
Icon=kinnycodememory
Categories=Development;
'''
        (appdir / f"{APP_NAME.lower()}.desktop").write_text(desktop_content)

        # Create wrapper script
        wrapper_content = f'''#!/bin/bash
DIR="$(cd "$(dirname "{{BASH_SOURCE[0]}}" )" && pwd)"
exec "$DIR/{APP_NAME}" "$@"
'''
        wrapper_path = appdir / APP_NAME
        wrapper_path.write_text(wrapper_content)
        wrapper_path.chmod(0o755)

        # Copy executable
        exe_src = DIST_DIR / APP_NAME
        if exe_src.exists():
            shutil.copy2(exe_src, appdir / APP_NAME)

        # Create AppRun
        apprun_content = f'''#!/bin/bash
SELF=$(readlink -f "$0")
HERE=${{SELF%/*}}
export PATH="${{HERE}}/bin:${{PATH}}"
exec "${{HERE}}/{APP_NAME}" "$@"
'''
        apprun_path = appdir / "AppRun"
        apprun_path.write_text(apprun_content)
        apprun_path.chmod(0o755)

        print(f"AppDir created at: {appdir}")
        print("To create AppImage, use appimagetool:")
        print(f"  appimagetool {appdir} {DIST_DIR}/{APP_NAME}-{APP_VERSION}-x86_64.AppImage")


# ═══════════════════════════════════════════════════════════════════════
#  Main Build Script
# ═══════════════════════════════════════════════════════════════════════


def install_pyinstaller():
    """Install PyInstaller if not present."""
    try:
        import PyInstaller
        print(f"PyInstaller {PyInstaller.__version__} found")
    except ImportError:
        print("Installing PyInstaller...")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "pyinstaller"],
            check=True
        )
        print("PyInstaller installed")


def clean_build():
    """Clean build artifacts."""
    print("\nCleaning build artifacts...")
    for dir_name in ["build", "dist", "*.spec"]:
        for path in Path(".").glob(dir_name):
            if path.is_dir():
                shutil.rmtree(path)
                print(f"Removed: {path}")
            else:
                path.unlink()
                print(f"Removed: {path}")
    print("Clean complete")


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description=f"{APP_NAME} Build Script"
    )
    parser.add_argument(
        "--installer", action="store_true",
        help="Build installer with GUI"
    )
    parser.add_argument(
        "--tray", action="store_true",
        help="Build system tray app"
    )
    parser.add_argument(
        "--webui", action="store_true",
        help="Build Web UI server"
    )
    parser.add_argument(
        "--server", action="store_true",
        help="Build memory server"
    )
    parser.add_argument(
        "--all", action="store_true",
        help="Build everything"
    )
    parser.add_argument(
        "--clean", action="store_true",
        help="Clean build artifacts"
    )
    parser.add_argument(
        "--nsis", action="store_true",
        help="Create Windows installer with NSIS"
    )
    parser.add_argument(
        "--appimage", action="store_true",
        help="Create Linux AppImage structure"
    )

    args = parser.parse_args()

    # Clean if requested
    if args.clean:
        clean_build()
        return

    # Default to building server
    if not any([args.installer, args.tray, args.webui, args.server, args.all, args.nsis, args.appimage]):
        args.server = True

    # Ensure build dirs exist
    BUILD_DIR.mkdir(exist_ok=True)
    DIST_DIR.mkdir(exist_ok=True)

    # Install PyInstaller
    install_pyinstaller()

    # Create builder
    builder = PyInstallerBuilder()

    # Build requested components
    try:
        if args.all or args.server:
            builder.build_server()

        if args.all or args.installer:
            builder.build_installer()

        if args.all or args.tray:
            builder.build_tray()

        if args.all or args.webui:
            builder.build_web_ui()

        # Create platform installer
        if args.nsis and PLATFORM == "windows":
            nsis = NSISBuilder()
            nsis.create_installer()

        if args.appimage and PLATFORM == "linux":
            appimage = AppImageBuilder()
            appimage.create_appimage()

        print(f"\n{'='*60}")
        print(f"  Build Complete!")
        print(f"  Output: {DIST_DIR.absolute()}")
        print(f"{'='*60}\n")

        # List built files
        print("Built files:")
        for f in DIST_DIR.iterdir():
            if f.is_file():
                size_mb = f.stat().st_size / (1024 * 1024)
                print(f"  {f.name} ({size_mb:.1f} MB)")

    except Exception as e:
        print(f"\nError: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
