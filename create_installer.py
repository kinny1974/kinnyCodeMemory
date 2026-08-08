#!/usr/bin/env python3
"""
KinnyCode Memory - Self-Extracting Installer
=============================================
Creates a single executable that extracts and installs the application.

Usage:
    python create_installer.py
"""

import os
import sys
import shutil
import zipfile
import tempfile
from pathlib import Path

# ═══════════════════════════════════════════════════════════════════════
#  Configuration
# ═══════════════════════════════════════════════════════════════════════

APP_NAME = "KinnyCodeMemory"
APP_VERSION = "1.0.0"
FILES_TO_INCLUDE = [
    "memory_server.py",
    "mcp_wrapper.py",
    "cli.py",
    "kinnycode_main.py",
    "installer.py",
    "tray_app.py",
    "memory/",
    "web/",
    "assets/",
    "requirements.txt",
    ".env.example",
    "README.md",
]


# ═══════════════════════════════════════════════════════════════════════
#  Installer Creator
# ═══════════════════════════════════════════════════════════════════════


class InstallerCreator:
    """Creates self-extracting installer."""

    def __init__(self):
        self.source_dir = Path(__file__).parent
        self.dist_dir = self.source_dir / "dist"
        self.build_dir = self.source_dir / "build"

    def create_zip_package(self) -> Path:
        """Create ZIP package of all files."""
        print("\n📦 Creando paquete ZIP...")

        self.build_dir.mkdir(exist_ok=True)
        zip_path = self.build_dir / f"{APP_NAME}-v{APP_VERSION}.zip"

        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for item in FILES_TO_INCLUDE:
                source = self.source_dir / item
                if source.is_dir():
                    for file in source.rglob("*"):
                        if file.is_file():
                            arcname = file.relative_to(self.source_dir)
                            zf.write(file, arcname)
                elif source.is_file():
                    arcname = source.relative_to(self.source_dir)
                    zf.write(source, arcname)

        print(f"✓ Paquete creado: {zip_path}")
        return zip_path

    def create_installer_script(self, zip_path: Path) -> Path:
        """Create installer script that extracts and sets up."""
        print("\n📝 Creando script de instalación...")

        # Read ZIP as bytes
        zip_bytes = zip_path.read_bytes()

        # Create installer script
        script_content = f'''#!/usr/bin/env python3
"""
{APP_NAME} v{APP_VERSION} - Instalador Auto-Extraíble
=====================================================
Ejecuta este archivo para instalar {APP_NAME}.
"""

import os
import sys
import zipfile
import tempfile
import subprocess
import shutil
from pathlib import Path

# Configuration
APP_NAME = "{APP_NAME}"
VERSION = "{APP_VERSION}"
DEFAULT_DIR = Path.home() / APP_NAME

# Embedded ZIP data (base64 encoded)
import base64
ZIP_DATA = """{self._bytes_to_base64(zip_bytes)}"""

def extract_installer():
    """Extract files to temp directory."""
    print(f"\\n{'='*60}")
    print(f"  {APP_NAME} v{{VERSION}} - Instalador")
    print(f"{'='*60}\\n")

    # Decode ZIP
    zip_bytes = base64.b64decode(ZIP_DATA)

    # Create temp directory
    temp_dir = Path(tempfile.mkdtemp(prefix="kinnycodememory_"))
    zip_path = temp_dir / "app.zip"
    zip_path.write_bytes(zip_bytes)

    return temp_dir, zip_path

def select_directory():
    """Ask user for installation directory."""
    print(f"\\nDirectorio de instalación:")
    print(f"  Predeterminado: {{DEFAULT_DIR}}")

    custom = input("\\n¿Usar directorio personalizado? (s/N): ").strip().lower()

    if custom == 's':
        dir_path = input("Ruta: ").strip()
        return Path(dir_path)
    else:
        return DEFAULT_DIR

def extract_files(zip_path: Path, target_dir: Path):
    """Extract all files to target directory."""
    print(f"\\nExtrayendo archivos a: {{target_dir}}")

    target_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path, 'r') as zf:
        zf.extractall(target_dir)

    print(f"✓ Archivos extraídos")

def create_venv(target_dir: Path):
    """Create virtual environment and install dependencies."""
    print("\\nCreando entorno virtual...")

    venv_dir = target_dir / ".venv"
    subprocess.run(
        [sys.executable, "-m", "venv", str(venv_dir)],
        check=True
    )

    # Install dependencies
    if sys.platform == 'win32':
        pip = venv_dir / "Scripts" / "pip.exe"
    else:
        pip = venv_dir / "bin" / "pip"

    print("Instalando dependencias...")
    subprocess.run(
        [str(pip), "install", "-r", str(target_dir / "requirements.txt")],
        capture_output=True
    )

    print("✓ Entorno virtual creado")

def create_shortcut(target_dir: Path):
    """Create desktop shortcut."""
    print("\\nCreando acceso directo...")

    if sys.platform == 'win32':
        desktop = Path.home() / "Desktop"
        shortcut = desktop / f"{{APP_NAME}}.lnk"

        # Create VBS script
        vbs = f"""
Set WshShell = WScript.CreateObject("WScript.Shell")
Set shortcut = WshShell.CreateShortcut("{shortcut}")
shortcut.TargetPath = "{target_dir / 'tray_app.exe'}"
shortcut.WorkingDirectory = "{target_dir}"
shortcut.Description = "{APP_NAME}"
shortcut.Save
"""
        vbs_path = target_dir / "_shortcut.vbs"
        vbs_path.write_text(vbs)
        subprocess.run(["cscript", str(vbs_path)], capture_output=True)
        vbs_path.unlink()
    else:
        desktop = Path.home() / "Desktop"
        desktop_file = desktop / f"{{APP_NAME.lower()}}.desktop"
        content = f"""[Desktop Entry]
Name={APP_NAME}
Exec={target_dir / 'tray_app'}
Icon={target_dir / 'assets/icon.png'}
Terminal=false
Type=Application
"""
        desktop_file.write_text(content)
        os.chmod(desktop_file, 0o755)

    print("✓ Acceso directo creado")

def main():
    """Main installer logic."""
    temp_dir, zip_path = extract_installer()

    try:
        # Select directory
        target_dir = select_directory()

        # Confirm
        print(f"\\n{'─'*60}")
        print(f"Instalando en: {{target_dir}}")
        print(f"{'─'*60}")

        confirm = input("\\n¿Continuar? (S/n): ").strip().lower()
        if confirm == 'n':
            print("Instalación cancelada.")
            return

        # Extract files
        extract_files(zip_path, target_dir)

        # Create venv
        create_venv(target_dir)

        # Create shortcut
        create_shortcut(target_dir)

        # Success
        print(f"\\n{'='*60}")
        print(f"  ¡Instalación completada!")
        print(f"\\n  Para iniciar:")
        print(f"    cd {{target_dir}}")
        print(f"    python memory_server.py")
        print(f"\\n  O ejecuta: {{target_dir}}/tray_app.py")
        print(f"{'='*60}\\n")

    finally:
        # Cleanup
        shutil.rmtree(temp_dir, ignore_errors=True)

if __name__ == "__main__":
    main()
'''

        script_path = self.dist_dir / f"{APP_NAME}-Setup-v{APP_VERSION}.py"
        script_path.write_text(script_content)
        os.chmod(script_path, 0o755)

        print(f"✓ Instalador creado: {script_path}")
        return script_path

    def _bytes_to_base64(self, data: bytes) -> str:
        """Convert bytes to base64 string."""
        import base64
        return base64.b64encode(data).decode('ascii')

    def create(self):
        """Create complete installer package."""
        print(f"\n{'='*60}")
        print(f"  {APP_NAME} - Creando Instalador")
        print(f"{'='*60}")

        # Ensure dist dir exists
        self.dist_dir.mkdir(exist_ok=True)

        # Create ZIP package
        zip_path = self.create_zip_package()

        # Create installer script
        installer_path = self.create_installer_script(zip_path)

        print(f"\n{'='*60}")
        print(f"  ¡Listo!")
        print(f"\\n  Para distribuir:")
        print(f"    1. Envía: {{installer_path}}")
        print(f"    2. El usuario ejecuta: python {{installer_path.name}}")
        print(f"{'='*60}\\n")


# ═══════════════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════════════


if __name__ == "__main__":
    creator = InstallerCreator()
    creator.create()
