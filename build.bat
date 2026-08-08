@echo off
REM ═══════════════════════════════════════════════════════════════
REM  KinnyCode Memory - Quick Build Script (Windows)
REM ═══════════════════════════════════════════════════════════════

echo.
echo  ╔══════════════════════════════════════════════════════════╗
echo  ║       KinnyCode Memory - Build Ejecutables              ║
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

REM Build
echo.
echo Compilando ejecutables...
echo.

python build.py --all

echo.
echo ════════════════════════════════════════════════════════════
echo  Build completado! Revisa la carpeta: dist\
echo ════════════════════════════════════════════════════════════
echo.

pause
