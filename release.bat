@echo off
REM ═══════════════════════════════════════════════════════════════
REM  KinnyCode Memory - Quick Release Script (Windows)
REM ═══════════════════════════════════════════════════════════════

echo.
echo  ╔══════════════════════════════════════════════════════════╗
echo  ║       KinnyCode Memory - Release Builder                ║
echo  ╚══════════════════════════════════════════════════════════╝
echo.

REM Activate venv
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
) else (
    echo Creando entorno virtual...
    python -m venv .venv
    call .venv\Scripts\activate.bat
    pip install pyinstaller pystray Pillow httpx fastapi uvicorn jinja2 python-multipart
)

REM Build release
echo.
echo Creando paquetes de release...
echo.

python release.py --all

echo.
echo ════════════════════════════════════════════════════════════
echo  Release completado! Revisa la carpeta: release\
echo ════════════════════════════════════════════════════════════
echo.

pause
