# 🧠 KinnyCode Memory System

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111+-green.svg)](https://fastapi.tiangolo.com)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Sistema de memoria multicapa con RAG (Retrieval-Augmented Generation) para asistentes de código AI. Almacena, indexa y recupera contexto de código, documentos y conversaciones.

![KinnyCode Memory](https://via.placeholder.com/800x200/1e293b/38bdf8?text=KinnyCode+Memory+System)

## ✨ Características

- **Multicapa**: Memoria de código (L3), documentos (L4), conversaciones (L2), tareas (L5)
- **RAG Completo**: Búsqueda semántica con embeddings de alta calidad
- **Multi-formato**: Soporte para PDF, EPUB, DOCX, ODF, XLS, CSV, Markdown, TXT
- **Multi-proyecto**: Aislamiento completo entre proyectos
- **M_score**: Algoritmo de relevancia basado en similitud, tiempo y frecuencia
- **Embeddings Locales**: Modelo all-MiniLM-L6-v2 (sin dependencias externas)
- **Web UI**: Interfaz web para gestión y consultas
- **Cross-platform**: Windows, Linux, macOS

## 🚀 Inicio Rápido

### Instalación con pip

```bash
# Clonar el repositorio
git clone https://github.com/kinny1974/kinnycodememory.git
cd kinnycodememory

# Crear entorno virtual
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows

# Instalar dependencias
pip install -r requirements.txt

# Iniciar servidor
python memory_server.py
```

### Instalador (Windows/Linux)

```bash
# Ejecutar instalador GUI
python installer.py

# O modo CLI
python installer.py --cli
```

### Ejecutables Standalone

```bash
# Compilar ejecutables
python build.py --all

# Los ejecutables estarán en dist/
```

## 📦 Distribución

### Opción 1: Ejecutables Standalone

```bash
# Windows
build.bat

# Linux
./build.sh
```

### Opción 2: Release Packages

```bash
# Crear paquetes de release
python release.py --all

# Resultado en release/
# ├── KinnyCodeMemory-Windows-x64-v1.0.0.zip
# ├── KinnyCodeMemory-Linux-x64-v1.0.0.zip
# └── KinnyCodeMemory-Source-v1.0.0.tar.gz
```

### Opción 3: Instalador Auto-Extraíble

```bash
python create_installer.py
```

### Opción 4: GitHub Releases

1. Crear tag:
```bash
git tag v1.0.0
git push origin v1.0.0
```

2. GitHub Actions creará automáticamente:
- `KinnyCodeMemory-Windows-x64.zip`
- `KinnyCodeMemory-Linux-x64.zip`
- `KinnyCodeMemory-Source.tar.gz`

---

## 🚀 Downloads

| Plataforma | Archivo | Descripción |
|------------|---------|-------------|
| 🪟 Windows | [KinnyCodeMemory-Windows-x64.zip](https://github.com/kinny1974/kinnycodememory/releases/latest) | Ejecutables standalone |
| 🐧 Linux | [KinnyCodeMemory-Linux-x64.zip](https://github.com/kinny1974/kinnycodememory/releases/latest) | Ejecutables standalone |
| 📦 Source | [KinnyCodeMemory-Source.tar.gz](https://github.com/kinny1974/kinnycodememory/releases/latest) | Código fuente |

---

## 📖 Uso

### API REST

```bash
# Health check
curl http://localhost:8007/health

# Indexar documento
curl -X POST http://localhost:8007/index-document \
  -H "Content-Type: application/json" \
  -d '{"file_path": "/ruta/documento.pdf", "project_id": "mi-proyecto"}'

# Búsqueda semántica
curl -X POST http://localhost:8007/search-documents \
  -H "Content-Type: application/json" \
  -d '{"query": "cómo crear un botón", "project_id": "mi-proyecto", "top_k": 5}'

# RAG Context
curl -X POST http://localhost:8007/retrieve-context \
  -H "Content-Type: application/json" \
  -d '{"prompt": "¿Cómo manejar eventos en PyQt?", "project_id": "mi-proyecto"}'
```

### Web UI

```bash
# Iniciar Web UI
python web/web_app.py --port 19090

# Abrir http://localhost:19090
```

### MCP (Model Context Protocol)

```json
{
  "mcpServers": {
    "kinnycode-memory": {
      "command": "python",
      "args": ["mcp_wrapper.py"],
      "env": {
        "KINNYCODE_HOST": "127.0.0.1",
        "KINNYCODE_PORT": "8007"
      }
    }
  }
}
```

## 🏗️ Arquitectura

```
┌─────────────────────────────────────────────────────────────┐
│                    Client Layer                              │
├─────────────────────────────────────────────────────────────┤
│  MCP Wrapper │ CLI │ Web UI │ API REST │ Python Client      │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   Memory Server (FastAPI)                    │
├─────────────────────────────────────────────────────────────┤
│  Endpoints │ Auth │ Rate Limiting │ CORS │ Validation       │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   Memory Manager                            │
├─────────────────────────────────────────────────────────────┤
│  L1: Runtime │ L2: Conversations │ L3: Code │ L4: Docs │ L5│
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   Storage Layer                              │
├─────────────────────────────────────────────────────────────┤
│  LanceDB (Vectors) │ SQLite (Metadata) │ File System        │
└─────────────────────────────────────────────────────────────┘
```

## 📁 Estructura del Proyecto

```
kinnycodememory/
├── memory_server.py          # Servidor FastAPI principal
├── mcp_wrapper.py            # Servidor MCP (Model Context Protocol)
├── cli.py                    # Interfaz de línea de comandos
├── installer.py              # Instalador GUI cross-platform
├── tray_app.py               # Bandeja del sistema
├── build.py                  # Script de build para ejecutables
├── memory/                   # Paquete principal
│   ├── __init__.py           # API pública
│   ├── memory_manager.py     # Orquestador de memoria
│   ├── indexation_service.py # Servicio de indexación
│   ├── embedding_cache.py    # Cache de embeddings
│   ├── document_loader.py    # Cargadores multi-formato
│   ├── monitoring.py         # Health/Metrics/Ready
│   ├── validation.py         # Validación de inputs
│   └── client.py             # Cliente HTTP
├── web/                      # Interfaz Web
│   ├── web_app.py            # Servidor Web UI
│   └── templates/            # Templates HTML
├── assets/                   # Iconos e imágenes
├── requirements.txt          # Dependencias
└── tests/                    # Tests unitarios
```

## 🔧 Configuración

### Variables de Entorno

```bash
# Archivo .env
KINNYCODE_HOST=127.0.0.1
KINNYCODE_PORT=8007
KINNYCODE_DB_PATH=./lancedb_memory_db
KINNYCODE_EMBEDDING_MODEL=all-MiniLM-L6-v2
KINNYCODE_CHUNK_SIZE=1000
KINNYCODE_CHUNK_OVERLAP=200
```

### Endpoints Principales

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| GET | `/health` | Health check |
| GET | `/metrics` | Métricas del servidor |
| POST | `/index-file` | Indexar archivo de código |
| POST | `/index-document` | Indexar documento |
| POST | `/search-documents` | Búsqueda semántica |
| POST | `/retrieve-context` | RAG completo |
| POST | `/project-info` | Info del proyecto |
| GET | `/list-documents` | Listar documentos |

## 🧪 Testing

```bash
# Ejecutar tests
pytest tests/

# Con cobertura
pytest tests/ --cov=memory --cov-report=html

# Ver reporte
open htmlcov/index.html
```

## 📦 Distribución

### Windows
```bash
# Crear instalador
python build.py --nsis
# Resultado: dist/KinnyCodeMemory-Setup-v1.0.0.exe
```

### Linux
```bash
# Crear ejecutables
python build.py --all
chmod +x dist/*
```

### Cross-platform
```bash
# Crear instalador auto-extraíble
python create_installer.py
# Resultado: dist/KinnyCodeMemory-Setup-v1.0.0.py
```

## 🤝 Contribuir

Ver [CONTRIBUTING.md](CONTRIBUTING.md) para guías de contribución.

## 📄 Licencia

Este proyecto está bajo la Licencia MIT - ver [LICENSE](LICENSE) para detalles.

## 🔗 Enlaces

- [Documentación API](http://localhost:8007/docs)
- [Problemas](https://github.com/kinny1974/kinnycodememory/issues)
- [Pull Requests](https://github.com/kinny1974/kinnycodememory/pulls)

## ⭐ Soerte

Si este proyecto te es útil, por favor danos una ⭐ en GitHub!
