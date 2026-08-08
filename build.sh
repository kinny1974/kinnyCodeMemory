#!/bin/bash
# ═══════════════════════════════════════════════════════════════
#  KinnyCode Memory - Quick Build Script (Linux)
# ═══════════════════════════════════════════════════════════════

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║       KinnyCode Memory - Build Ejecutables              ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# Activate venv
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
else
    echo "Creando entorno virtual..."
    python3 -m venv .venv
    source .venv/bin/activate
    pip install pyinstaller pystray Pillow httpx fastapi uvicorn jinja2 python-multipart
fi

# Build
echo ""
echo "Compilando ejecutables..."
echo ""

python build.py --all

echo ""
echo "════════════════════════════════════════════════════════════"
echo " Build completado! Revisa la carpeta: dist/"
echo "════════════════════════════════════════════════════════════"
echo ""

# Make executables runnable
chmod +x dist/* 2>/dev/null

ls -lh dist/
