#!/bin/bash
# ═══════════════════════════════════════════════════════════════
#  KinnyCode Memory - Quick Release Script (Linux)
# ═══════════════════════════════════════════════════════════════

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║       KinnyCode Memory - Release Builder                ║"
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

# Build release
echo ""
echo "Creando paquetes de release..."
echo ""

python3 release.py --all

echo ""
echo "════════════════════════════════════════════════════════════"
echo " Release completado! Revisa la carpeta: release/"
echo "════════════════════════════════════════════════════════════"
echo ""

# List files
ls -lh release/
