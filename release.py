#!/usr/bin/env python3
"""
KinnyCode Memory - Release Builder
===================================
Creates release packages for Windows and Linux.

Usage:
    python release.py                    # Build for current platform
    python release.py --all              # Build for all platforms
    python release.py --windows          # Build Windows package
    python release.py --linux            # Build Linux package
    python release.py --source           # Create source archive
"""

import os
import sys
import shutil
import subprocess
import platform
import zipfile
import tarfile
from pathlib import Path
from datetime import datetime

# ═══════════════════════════════════════════════════════════════════════
#  Configuration
# ═══════════════════════════════════════════════════════════════════════

APP_NAME = "KinnyCodeMemory"
VERSION = "1.0.0"
BUILD_DIR = Path(__file__).parent / "build"
DIST_DIR = Path(__file__).parent / "dist"
RELEASE_DIR = Path(__file__).parent / "release"

PLATFORM = platform.system().lower()


# ═══════════════════════════════════════════════════════════════════════
#  Release Builder
# ═══════════════════════════════════════════════════════════════════════


class ReleaseBuilder:
    """Creates release packages."""

    def __init__(self):
        self.build_dir = BUILD_DIR
        self.dist_dir = DIST_DIR
        self.release_dir = RELEASE_DIR

    def clean(self):
        """Clean build artifacts."""
        print("\n🧹 Limpiando artefactos...")
        for dir_path in [self.build_dir, self.dist_dir, self.release_dir]:
            if dir_path.exists():
                shutil.rmtree(dir_path)
        print("✓ Limpieza completada")

    def build_executables(self):
        """Build executables using PyInstaller."""
        print("\n🔨 Compilando ejecutables...")

        # Install PyInstaller if needed
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "pyinstaller"],
            capture_output=True
        )

        # Run build script
        result = subprocess.run(
            [sys.executable, "build.py", "--all"],
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            print(f"Error: {result.stderr}")
            return False

        print("✓ Ejecutables compilados")
        return True

    def create_windows_package(self) -> Path:
        """Create Windows release package."""
        print("\n🪟 Creando paquete Windows...")

        self.release_dir.mkdir(exist_ok=True)
        zip_path = self.release_dir / f"{APP_NAME}-Windows-x64-v{VERSION}.zip"

        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            # Add executables
            for exe in self.dist_dir.glob("*.exe"):
                zf.write(exe, exe.name)

            # Add web templates
            web_templates = Path(__file__).parent / "web" / "templates"
            if web_templates.exists():
                for template in web_templates.glob("*.html"):
                    zf.write(template, f"web/templates/{template.name}")

            # Add requirements
            req_file = Path(__file__).parent / "requirements.txt"
            if req_file.exists():
                zf.write(req_file, "requirements.txt")

            # Add example env
            env_file = Path(__file__).parent / ".env.example"
            if env_file.exists():
                zf.write(env_file, ".env.example")

            # Add README
            readme = Path(__file__).parent / "README.md"
            if readme.exists():
                zf.write(readme, "README.md")

            # Add batch launcher
            launcher_content = f'''@echo off
echo ╔══════════════════════════════════════════════════════════╗
echo ║       {APP_NAME} v{VERSION}                              ║
echo ╚══════════════════════════════════════════════════════════╝
echo.
echo Iniciando servidor...
echo.
{APP_NAME}-Server.exe
pause
'''
            launcher_path = self.build_dir / "start.bat"
            launcher_path.write_text(launcher_content)
            zf.write(launcher_path, "start.bat")

        print(f"✓ Paquete Windows: {zip_path}")
        return zip_path

    def create_linux_package(self) -> Path:
        """Create Linux release package."""
        print("\n🐧 Creando paquete Linux...")

        self.release_dir.mkdir(exist_ok=True)
        zip_path = self.release_dir / f"{APP_NAME}-Linux-x64-v{VERSION}.zip"

        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            # Add executables
            for exe in self.dist_dir.glob("*"):
                if exe.is_file() and not exe.suffix == '.exe':
                    zf.write(exe, exe.name)

            # Add web templates
            web_templates = Path(__file__).parent / "web" / "templates"
            if web_templates.exists():
                for template in web_templates.glob("*.html"):
                    zf.write(template, f"web/templates/{template.name}")

            # Add requirements
            req_file = Path(__file__).parent / "requirements.txt"
            if req_file.exists():
                zf.write(req_file, "requirements.txt")

            # Add example env
            env_file = Path(__file__).parent / ".env.example"
            if env_file.exists():
                zf.write(env_file, ".env.example")

            # Add README
            readme = Path(__file__).parent / "README.md"
            if readme.exists():
                zf.write(readme, "README.md")

            # Add shell launcher
            launcher_content = f'''#!/bin/bash
echo "╔══════════════════════════════════════════════════════════╗"
echo "║       {APP_NAME} v{VERSION}                              ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
echo "Iniciando servidor..."
echo ""
./{APP_NAME}-Server
'''
            launcher_path = self.build_dir / "start.sh"
            launcher_path.write_text(launcher_content)
            os.chmod(launcher_path, 0o755)
            zf.write(launcher_path, "start.sh")

        print(f"✓ Paquete Linux: {zip_path}")
        return zip_path

    def create_source_package(self) -> Path:
        """Create source code archive."""
        print("\n📦 Creando paquete fuente...")

        self.release_dir.mkdir(exist_ok=True)
        tar_path = self.release_dir / f"{APP_NAME}-Source-v{VERSION}.tar.gz"

        # Files/dirs to exclude
        exclude_dirs = {
            '.opencode', '.kinnycode', '.venv', 'venv',
            'dist', 'build', 'release', '__pycache__',
            'lancedb_memory_db', 'uploads', 'temp', 'tmp',
            'test', 'eitl-artifacts', '.git'
        }

        exclude_files = {
            '.env', '.env.local', '*.pyc', '*.pyo',
            '*.exe', '*.spec', '*.log'
        }

        with tarfile.open(tar_path, 'w:gz') as tar:
            source_dir = Path(__file__).parent

            for item in source_dir.rglob("*"):
                # Skip excluded directories
                if any(excluded in item.parts for excluded in exclude_dirs):
                    continue

                # Skip excluded files
                if item.name in exclude_files or item.suffix == '.pyc':
                    continue

                # Skip .git directory
                if '.git' in item.parts:
                    continue

                if item.is_file():
                    arcname = item.relative_to(source_dir.parent)
                    tar.add(item, arcname=arcname)

        print(f"✓ Paquete fuente: {tar_path}")
        return tar_path

    def create_all(self):
        """Create all release packages."""
        print(f"\n{'='*60}")
        print(f"  {APP_NAME} v{VERSION} - Release Builder")
        print(f"{'='*60}")

        # Clean
        self.clean()

        # Build executables
        if not self.build_executables():
            print("\n❌ Error compilando ejecutables")
            return

        # Create packages
        packages = []

        if PLATFORM == "windows":
            packages.append(self.create_windows_package())
        elif PLATFORM == "linux":
            packages.append(self.create_linux_package())
        else:
            packages.append(self.create_windows_package())
            packages.append(self.create_linux_package())

        packages.append(self.create_source_package())

        # Summary
        print(f"\n{'='*60}")
        print(f"  ✅ Release packages creados!")
        print(f"{'='*60}")
        print(f"\n📦 Archivos generados en: {self.release_dir}/")
        print()

        for pkg in packages:
            if pkg.exists():
                size_mb = pkg.stat().st_size / (1024 * 1024)
                print(f"  • {pkg.name} ({size_mb:.1f} MB)")

        print(f"\n📋 Para crear un release en GitHub:")
        print(f"   1. Crear tag: git tag v{VERSION}")
        print(f"   2. Push tag: git push origin v{VERSION}")
        print(f"   3. GitHub Actions creará el release automáticamente")
        print()


# ═══════════════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════════════


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description=f"{APP_NAME} Release Builder"
    )
    parser.add_argument(
        "--all", action="store_true",
        help="Build all packages"
    )
    parser.add_argument(
        "--windows", action="store_true",
        help="Build Windows package"
    )
    parser.add_argument(
        "--linux", action="store_true",
        help="Build Linux package"
    )
    parser.add_argument(
        "--source", action="store_true",
        help="Build source package"
    )
    parser.add_argument(
        "--clean", action="store_true",
        help="Clean build artifacts"
    )

    args = parser.parse_args()

    builder = ReleaseBuilder()

    if args.clean:
        builder.clean()
        return

    if args.all or args.windows or args.linux or args.source:
        if args.windows:
            builder.create_windows_package()
        if args.linux:
            builder.create_linux_package()
        if args.source:
            builder.create_source_package()
    else:
        builder.create_all()


if __name__ == "__main__":
    main()
