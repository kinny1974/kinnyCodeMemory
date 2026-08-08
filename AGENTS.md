# AGENTS.md — Guía para Agentes de Código

## Proyecto

KinnyCode Memory System — Sistema de memoria multicapa con RAG para asistentes de código AI.

## Estructura del Proyecto

```
C:\ProgramData\KinnyCode\memory\
├── memory_server.py          # FastAPI server (entry point principal)
├── mcp_wrapper.py            # Servidor MCP stdio (15 herramientas)
├── cli.py                    # CLI kinnycode
├── kinnycode_main.py         # Entry point unificado (PyInstaller)
├── kinnycode_installer.py    # Instalador GUI tkinter
├── kinnycode_tray.py         # Bandeja del sistema Win32
├── kinnycode_service.py      # Servicio Windows (Task Scheduler)
├── memory/                   # Paquete Python
│   ├── __init__.py           # API pública
│   ├── memory_manager.py     # Orquestador L1-L4
│   ├── client.py             # Cliente HTTP
│   ├── mscore.py             # M_score Ebbinghaus
│   ├── document_loader.py    # PDF/MD/TXT loaders
│   ├── change_detector.py    # Detección de cambios
│   ├── file_watcher.py       # Monitoreo de archivos
│   ├── conversation_store.py # Conversaciones
│   ├── project_rules.py      # Reglas de proyecto
│   ├── hash_cache.py         # Cache de hashes
│   └── ignore_patterns.py    # Patrones de exclusión
├── lancedb_memory_db/        # Base de datos LanceDB
├── assets/                   # SVGs e iconos
├── requirements.txt          # Dependencias Python
├── .env.example              # Template de configuración
└── opencode.json             # Config MCP para Opencode
```

## Convenciones

### Python
- Python 3.10+ (usa `X | Y` en lugar de `Optional[X]` o `Union[X, Y]`)
- Type hints en todas las funciones públicas
- Docstrings en formato Google para funciones/métodos
- Logging con `logging.getLogger(__name__)`
- No agregar comentarios a menos que se solicite
- Seguir el estilo existente del archivo al editar

### Naming
- Funciones/métodos: `snake_case`
- Clases: `PascalCase`
- Constantes: `UPPER_SNAKE_CASE`
- Privados: prefijo `_`
- MCP tools: `snake_case` en español

### Archivos de configuración
- `.env` — Variables de entorno (no commitear)
- `.kinnycode/memory.json` — Metadata del proyecto
- `.kinnycode/rules.md` — Reglas del proyecto
- `.kinnycode/ignore` — Patrones de exclusión
- `opencode.json` — Config MCP

## Stack Tecnológico

- **Server:** FastAPI + Uvicorn
- **Vector DB:** LanceDB (embebida, local disk)
- **Embeddings:** sentence-transformers all-MiniLM-L6-v2 (dim 384, CPU)
- **Protocolo:** MCP (Model Context Protocol) via stdio
- **CLI:** argparse + httpx
- **GUI:** tkinter (instalador), Win32 API (bandeja)
- **Persistencia:** SQLite WAL (conversaciones), LanceDB (vectores)

## Reglas de Desarrollo

1. **No romper la API MCP** — Las 15 herramientas MCP son el contrato principal con los agentes.
2. **Multi-proyecto** — Todos los endpoints aceptan `project_id` para aislamiento.
3. **Graceful fallback** — Si langchain no está disponible, usar el splitter genérico.
4. **Embeddings locale** — Nunca depender de APIs externas para embeddings.
5. **Cambios incrementales** — Usar content_hash para evitar re-indexación innecesaria.
6. **Plataforma** — El server funciona en cualquier OS; la bandeja y servicio son Windows-only.

## Puntos de Entrada

| Componente | Comando |
|------------|---------|
| Servidor | `uvicorn memory_server:app --host 127.0.0.1 --port 8006` |
| CLI | `python cli.py <comando>` |
| MCP | `python mcp_wrapper.py` (stdio) |
| Instalador | `python kinnycode_installer.py` |
| Bandeja | `python kinnycode_tray.py --port 8006` |
| Servicio | `python kinnycode_service.py create/start/stop/status` |

## Endpoints Principales del Server

### Código (L3)
- `POST /index-file` — Indexar archivo individual
- `POST /reindex-file` — Re-indexar si hash cambió
- `POST /index-project` — Batch indexing
- `POST /index-file-paths` — Indexar por rutas de disco
- `POST /semantic-search` — Búsqueda semántica

### Documentos (L4)
- `POST /index-document` — Indexar PDF/MD/TXT
- `POST /load-book` — Alias de index-document
- `POST /search-documents` — Buscar en documentos
- `GET /list-documents` — Listar documentos
- `DELETE /delete-document` — Eliminar documento
- `POST /index-documents-batch` — Batch de documentos

### Conversaciones (L2)
- `POST /save-conversation` — Guardar historial
- `POST /load-conversation` — Recuperar historial

### Decisiones (L2)
- `POST /remember-decision` — Guardar decisión

### Tareas (L5)
- `POST /tasks/upsert` — Crear/actualizar
- `GET /tasks` — Listar
- `GET /tasks/{id}` — Obtener
- `DELETE /tasks/{id}` — Eliminar
- `POST /tasks/search` — Búsqueda semántica

### Contexto
- `POST /retrieve-context` — RAG completo (todas las capas)
- `POST /project-info` — Estadísticas
- `POST /clear-project` — Limpiar datos del proyecto
- `POST /session-context` — Contexto proactivo de sesión
- `POST /consolidate` — Consolidación de memoria

## M_score (Fórmula de Relevancia)

```python
M_score = similarity × e^(-t/lambda_days) + w_freq × access_frequency
```

- `lambda_days` = 30 (constant)
- `w_freq` = 0.5 (peso de frecuencia)
- Persistido en `mscore_state.json`

## Notas de Implementación

- LanceDB almacena vectores en disco local (`lancedb_memory_db/`)
- El modelo de embeddings se carga lazy (primera query tarda ~10s)
- El `PollingChangeDetector` escanea cada 3s con triple validación: mtime/size → SHA256 → DedupLock
- El MCP wrapper usa `httpx.AsyncClient` para comunicarse con el server FastAPI
- El instalador crea un venv aislado en `.venv/` dentro del directorio de instalación
