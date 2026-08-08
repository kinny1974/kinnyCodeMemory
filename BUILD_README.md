# KinnyCode Memory - Build & Distribute

## 📦 Opciones de Empaquetado

### Opción 1: Ejecutables Standalone (Recomendado)

Crea archivos `.exe` (Windows) o ejecutables (Linux) independientes.

#### Windows:
```batch
# Doble clic en build.bat
# O desde consola:
python build.py --all
```

#### Linux:
```bash
# Ejecutar:
chmod +x build.sh
./build.sh
# O desde consola:
python3 build.py --all
```

#### Resultado:
```
dist/
├── KinnyCodeMemory-Server.exe      # Servidor principal
├── KinnyCodeMemory-Installer.exe   # Instalador GUI
├── KinnyCodeMemory-Tray.exe        # Bandeja del sistema
└── KinnyCodeMemory-WebUI.exe       # Interfaz web
```

---

### Opción 2: Instalador Auto-Extraíble

Crea un solo archivo `.py` que instala todo.

```bash
python create_installer.py
```

#### Resultado:
```
dist/KinnyCodeMemory-Setup-v1.0.0.py
```

El usuario ejecuta:
```bash
python KinnyCodeMemory-Setup-v1.0.0.py
```

---

### Opción 3: Paquete ZIP

Crea un archivo ZIP con todo incluido.

```bash
python create_installer.py
```

---

## 🔧 Prerrequisitos para Build

### Windows:
- Python 3.10+
- PyInstaller: `pip install pyinstaller`
- (Opcional) NSIS para instalador Windows: https://nsis.sourceforge.io/

### Linux:
- Python 3.10+
- PyInstaller: `pip install pyinstaller`
- (Opcional) appimagetool para AppImage

---

## 📋 Comandos de Build

```bash
# Build solo el servidor
python build.py --server

# Build solo el instalador GUI
python build.py --installer

# Build solo la bandeja del sistema
python build.py --tray

# Build solo la Web UI
python build.py --webui

# Build todo
python build.py --all

# Limpiar archivos de build
python build.py --clean

# Crear instalador Windows (requiere NSIS)
python build.py --nsis

# Crear estructura AppImage (Linux)
python build.py --appimage
```

---

## 🚀 Distribución

### Para Windows:
1. Ejecutar `python build.py --all`
2. Los ejecutables quedan en `dist/`
3. Opcionalmente: `python build.py --nsis` para crear instalador `.exe`

### Para Linux:
1. Ejecutar `python3 build.py --all`
2. Los ejecutables quedan en `dist/`
3. Opcionalmente crear AppImage con `appimagetool`

### Distribución cruzada:
1. Ejecutar `python create_installer.py`
2. Enviar el archivo `.py` generado
3. El usuario ejecuta: `python KinnyCodeMemory-Setup-v1.0.0.py`

---

## 📁 Estructura del Proyecto

```
kinnyCodeMemory/
├── memory_server.py          # Servidor principal
├── installer.py              # Instalador GUI
├── tray_app.py               # Bandeja del sistema
├── build.py                  # Script de build
├── build.bat                 # Build Windows
├── build.sh                  # Build Linux
├── create_installer.py       # Crear instalador auto-extraíble
├── requirements.txt          # Dependencias
├── memory/                   # Paquete principal
├── web/                      # Web UI
│   ├── web_app.py
│   └── templates/
├── assets/                   # Iconos e imágenes
├── build/                    # Archivos temporales de build
└── dist/                     # Ejecutables generados
```

---

## 🔨 Solución de Problemas

### PyInstaller no encuentra módulos:
```bash
pip install --upgrade pyinstaller
python build.py --clean
python build.py --all
```

### Error de permisos (Linux):
```bash
chmod +x dist/*
```

### NSIS no encontrado:
Descargar e instalar desde: https://nsis.sourceforge.io/

### AppImage no funciona:
```bash
chmod +x dist/*.AppImage
```

---

## 📝 Notas

- Los ejecutables incluyen Python embebido (~10-50 MB)
- La primera ejecución puede tardar en cargar el modelo de embeddings
- El modelo se descarga automáticamente en la primera uso (~90 MB)
