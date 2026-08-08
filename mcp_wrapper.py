"""
MCP Wrapper for KinnyCode Multi-Layer Memory Server (LanceDB).

Exposes 11 MCP tools that map to the FastAPI memory_server.py endpoints:
  - Code indexing:  indexar_archivo, indexar_proyecto
  - Code search:    buscar_codigo
  - RAG context:    recuperar_contexto
  - Decisions:      guardar_decision
  - Conversations:  guardar_conversacion, cargar_conversacion
  - Documents:      indexar_documento, buscar_documentos, listar_documentos
  - Project:        info_proyecto

All tools are project-scoped via auto-detected project_id.
Results are filtered to the current project namespace.

Server name:  KinnyCode-Memory-RAG
Base URL:     http://127.0.0.1:8007
Transport:    stdio (MCP protocol)
"""

import asyncio
import hashlib
import json
import os
from pathlib import Path

import httpx
from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp import types

# ── Server identity ─────────────────────────────────────────────────
server = Server("KinnyCode-Memory-RAG")
BASE_URL = "http://127.0.0.1:8007"


# ── Project ID detection ────────────────────────────────────────────
def _get_project_id() -> str:
    """Auto-detect project_id from environment, .kinnycode config, or CWD hash.

    Resolution order:
        1. ``KINNYCODE_PROJECT_ID`` environment variable (explicit override).
        2. ``.kinnycode/memory.json`` in the current working directory tree.
        3. SHA-256 hash of the resolved current working directory (first 16 hex chars).

    Returns:
        A stable, unique project identifier string.
    """
    # 1. Check environment variable
    env_id = os.environ.get("KINNYCODE_PROJECT_ID", "")
    if env_id:
        return env_id

    # 2. Walk up from CWD looking for .kinnycode/memory.json
    current = Path.cwd().resolve()
    for _ in range(10):
        config_file = current / ".kinnycode" / "memory.json"
        if config_file.is_file():
            try:
                import json as _json
                data = _json.loads(config_file.read_text(encoding="utf-8"))
                pid = data.get("project_id", "")
                if pid:
                    return pid
            except Exception:
                pass
        parent = current.parent
        if parent == current:
            break
        current = parent

    # 3. Fallback: derive from CWD hash
    cwd = str(Path.cwd().resolve())
    return hashlib.sha256(cwd.encode()).hexdigest()[:16]


# ═══════════════════════════════════════════════════════════════════════
#  Tool definitions
# ═══════════════════════════════════════════════════════════════════════
@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """Register all available MCP tools with their JSON schemas."""
    return [
        # ── 1. Code file indexing ──────────────────────────────────
        types.Tool(
            name="indexar_archivo",
            description=(
                "Indexa un archivo de código fuente en la base de conocimiento "
                "RAG (Capa 3 — memoria a largo plazo). El contenido se divide "
                "en fragmentos (chunks) y se generan embeddings para búsqueda "
                "semántica posterior. Los resultados están acotados al proyecto "
                "actual (detectado automáticamente del directorio de trabajo)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Ruta del archivo de código a indexar (ej: 'src/main.py')."
                    },
                    "content": {
                        "type": "string",
                        "description": "Contenido completo del archivo de código fuente."
                    },
                    "language": {
                        "type": "string",
                        "description": (
                            "Lenguaje de programación del archivo "
                            "(ej: 'python', 'javascript', 'typescript', 'rust', 'go')."
                        ),
                    },
                },
                "required": ["file_path", "content", "language"],
            },
        ),
        # ── 2. Batch project indexing ──────────────────────────────
        types.Tool(
            name="indexar_proyecto",
            description=(
                "Indexa múltiples archivos de código en lote dentro de la base "
                "de conocimiento RAG. Opcionalmente, limpia todo el codebase "
                "antes de indexar para empezar desde cero. La operación está "
                "acotada al proyecto actual."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "files": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "file_path": {
                                    "type": "string",
                                    "description": "Ruta del archivo."
                                },
                                "content": {
                                    "type": "string",
                                    "description": "Contenido del archivo."
                                },
                                "language": {
                                    "type": "string",
                                    "description": "Lenguaje de programación."
                                },
                            },
                            "required": ["file_path", "content", "language"],
                        },
                        "description": "Lista de archivos a indexar (con contenido embebido). Usa file_paths en su lugar para evitar limites de tamaño."
                    },
                    "file_paths": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Lista de rutas absolutas de archivos. El servidor lee el contenido del disco. Preferido sobre 'files' para proyectos grandes."
                    },
                    "clear_first": {
                        "type": "boolean",
                        "description": (
                            "Si es true, elimina todos los archivos indexados "
                            "previamente antes de indexar el lote."
                        ),
                        "default": False,
                    },
                },
                "required": [],
            },
        ),
        # ── 3. Semantic code search ────────────────────────────────
        types.Tool(
            name="buscar_codigo",
            description=(
                "Realiza una búsqueda semántica sobre todo el código fuente "
                "indexado dentro del proyecto actual. Devuelve fragmentos de "
                "código relevantes ordenados por similitud semántica, con ruta "
                "del archivo, lenguaje y puntuación de relevancia."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "Consulta de búsqueda en lenguaje natural o "
                            "fragmento de código (ej: 'cómo se conecta a la base de datos')."
                        ),
                    },
                    "n_results": {
                        "type": "integer",
                        "description": "Número máximo de resultados a devolver.",
                        "default": 10,
                    },
                },
                "required": ["query"],
            },
        ),
        # ── 4. Full RAG context retrieval ──────────────────────────
        types.Tool(
            name="recuperar_contexto",
            description=(
                "Recupera contexto relevante de TODAS las capas de memoria "
                "(conversaciones recientes, decisiones de arquitectura previas, "
                "y fragmentos de código relacionados) para enriquecer la "
                "generación aumentada por recuperación (RAG). Los resultados "
                "están acotados al proyecto actual."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Consulta para recuperar contexto relevante de todas las capas."
                    },
                    "n_results": {
                        "type": "integer",
                        "description": "Número de fragmentos de código a incluir en el contexto.",
                        "default": 5,
                    },
                },
                "required": ["query"],
            },
        ),
        # ── 5. Architecture decision storage ───────────────────────
        types.Tool(
            name="guardar_decision",
            description=(
                "Almacena una decisión de arquitectura o diseño en la Capa 2 "
                "de memoria (medio plazo). Esta decisión se indexa semánticamente "
                "y puede recuperarse en futuras consultas de contexto. La decisión "
                "se asocia al proyecto actual."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "decision": {
                        "type": "string",
                        "description": "La decisión de arquitectura, diseño o refactorización tomada."
                    },
                    "context": {
                        "type": "string",
                        "description": (
                            "Contexto y motivación que llevaron a tomar esta decisión "
                            "(alternativas consideradas, trade-offs, restricciones)."
                        ),
                    },
                },
                "required": ["decision", "context"],
            },
        ),
        # ── 6. Save conversation ───────────────────────────────────
        types.Tool(
            name="guardar_conversacion",
            description=(
                "Persiste el historial completo de una conversación de agente "
                "en la Capa 1 de memoria (corto plazo). Los mensajes se indexan "
                "con embeddings para búsqueda semántica futura. La conversación "
                "se asocia al proyecto actual."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Identificador único de la sesión de conversación."
                    },
                    "messages": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "role": {
                                    "type": "string",
                                    "description": "Rol del mensaje ('user', 'assistant', 'system')."
                                },
                                "content": {
                                    "type": "string",
                                    "description": "Contenido textual del mensaje."
                                },
                            },
                            "required": ["role", "content"],
                        },
                        "description": "Lista de mensajes que componen la conversación."
                    },
                    "summarise": {
                        "type": "boolean",
                        "description": "Si es true, genera un resumen de la conversación al guardarla.",
                        "default": False,
                    },
                },
                "required": ["session_id", "messages"],
            },
        ),
        # ── 7. Load conversation ───────────────────────────────────
        types.Tool(
            name="cargar_conversacion",
            description=(
                "Carga el historial de conversación de una sesión previamente "
                "guardada en la memoria a corto plazo. Devuelve los mensajes "
                "en orden cronológico. La búsqueda está acotada al proyecto actual."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Identificador único de la sesión de conversación a recuperar."
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Número máximo de turnos de conversación a devolver.",
                        "default": 20,
                    },
                },
                "required": ["session_id"],
            },
        ),
        # ── 8. Index document/book ─────────────────────────────────
        types.Tool(
            name="indexar_documento",
            description=(
                "Indexa un documento, libro, paper o archivo de texto "
                "(PDF, Markdown, texto plano) en la Capa 4 de memoria "
                "documental para búsqueda semántica. El documento se asocia "
                "al proyecto actual."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Ruta absoluta o relativa del archivo de documento."
                    },
                    "doc_type": {
                        "type": "string",
                        "description": (
                            "Tipo de documento (ej: 'pdf', 'markdown', 'text', "
                            "'book', 'paper'). Se infiere de la extensión si no se especifica."
                        ),
                    },
                },
                "required": ["file_path"],
            },
        ),
        # ── 9. Semantic document search ────────────────────────────
        types.Tool(
            name="buscar_documentos",
            description=(
                "Realiza una búsqueda semántica sobre todos los documentos "
                "indexados (libros, PDFs, papers) en la Capa 4 documental. "
                "Permite filtrar por tipo de documento. La búsqueda está "
                "acotada al proyecto actual."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Consulta de búsqueda en lenguaje natural."
                    },
                    "n_results": {
                        "type": "integer",
                        "description": "Número máximo de resultados a devolver.",
                        "default": 5,
                    },
                    "doc_type": {
                        "type": "string",
                        "description": "Filtrar resultados por tipo de documento (opcional)."
                    },
                },
                "required": ["query"],
            },
        ),
        # ── 10. List indexed documents ─────────────────────────────
        types.Tool(
            name="listar_documentos",
            description=(
                "Lista todos los documentos indexados en la base de conocimiento "
                "documental (Capa 4) dentro del proyecto actual, mostrando ruta, "
                "tipo y estado de cada uno."
            ),
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
        # ── 11. Project info / statistics ──────────────────────────
        types.Tool(
            name="info_proyecto",
            description=(
                "Obtiene estadísticas del proyecto actual en la memoria: "
                "chunks de código indexados, documentos, conversaciones "
                "guardadas y decisiones de arquitectura registradas."
            ),
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
        # ── 12. Task management ──────────────────────────────────
        types.Tool(
            name="registrar_tarea",
            description=(
                "Registra o actualiza una tarea pendiente en el sistema de "
                "memoria agentiva. Las tareas se indexan semánticamente y "
                "pueden buscarse por estado, prioridad o contenido. Usa esta "
                "herramienta para que los agentes recuerden trabajo pendiente "
                "entre sesiones."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "ID de tarea existente para actualizar (omitir para crear nueva)."
                    },
                    "title": {
                        "type": "string",
                        "description": "Título descriptivo de la tarea."
                    },
                    "description": {
                        "type": "string",
                        "description": "Descripción detallada de qué hay que hacer.",
                        "default": "",
                    },
                    "context": {
                        "type": "string",
                        "description": "Contexto y motivación de por qué se creó esta tarea.",
                        "default": "",
                    },
                    "status": {
                        "type": "string",
                        "enum": ["pending", "in_progress", "completed", "cancelled"],
                        "description": "Estado actual de la tarea.",
                        "default": "pending",
                    },
                    "priority": {
                        "type": "string",
                        "enum": ["high", "medium", "low"],
                        "description": "Prioridad de la tarea.",
                        "default": "medium",
                    },
                    "dependencies": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Lista de IDs de tareas de las que depende esta tarea.",
                        "default": [],
                    },
                },
                "required": ["title"],
            },
        ),
        # ── 13. List tasks ────────────────────────────────────────
        types.Tool(
            name="listar_tareas",
            description=(
                "Lista las tareas registradas por los agentes en el sistema "
                "de memoria agentiva. Permite filtrar por estado y prioridad. "
                "Las tareas se asocian al proyecto actual."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["pending", "in_progress", "completed", "cancelled"],
                        "description": "Filtrar por estado de tarea.",
                    },
                    "priority": {
                        "type": "string",
                        "enum": ["high", "medium", "low"],
                        "description": "Filtrar por nivel de prioridad.",
                    },
                },
                "required": [],
            },
        ),
        # ── 14. Search tasks ──────────────────────────────────────
        types.Tool(
            name="buscar_tareas",
            description=(
                "Búsqueda semántica de tareas en el sistema de memoria agentiva. "
                "Encuentra tareas relacionadas semánticamente con la consulta, "
                "incluso si no coinciden las palabras exactas."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Consulta de búsqueda semántica (ej: 'tests unitarios', 'migración')."
                    },
                    "n_results": {
                        "type": "integer",
                        "description": "Número máximo de resultados.",
                        "default": 5,
                    },
                    "status": {
                        "type": "string",
                        "enum": ["pending", "in_progress", "completed", "cancelled"],
                        "description": "Filtrar resultados por estado.",
                    },
                },
                "required": ["query"],
            },
        ),
        # ── 15. Session context ──────────────────────────────────
        types.Tool(
            name="contexto_sesion",
            description=(
                "Recupera contexto proactivo de sesión: tareas pendientes, "
                "decisiones recientes y fragmentos de código relevantes. "
                "Diseñado para inyectar en el system prompt al inicio de sesión."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "include_tasks": {
                        "type": "boolean",
                        "description": "Incluir tareas pendientes.",
                        "default": True,
                    },
                    "include_decisions": {
                        "type": "boolean",
                        "description": "Incluir decisiones de arquitectura recientes.",
                        "default": True,
                    },
                    "include_code": {
                        "type": "boolean",
                        "description": "Incluir fragmentos de código relevantes.",
                        "default": False,
                    },
                    "include_documents": {
                        "type": "boolean",
                        "description": "Incluir documentos relevantes.",
                        "default": False,
                    },
                },
                "required": [],
            },
        ),
        # ── 16. Memory consolidation ──────────────────────────────
        types.Tool(
            name="consolidar_memoria",
            description=(
                "Ejecuta la consolidación de memoria agentiva: detecta tareas "
                "que llevan tiempo sin actualizarse y las re-promociona como "
                "recordatorio, y aplica el decaimiento M_score de Ebbinghaus "
                "a los fragmentos de código indexados."
            ),
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
    ]


# ═══════════════════════════════════════════════════════════════════════
#  Tool execution handler
# ═══════════════════════════════════════════════════════════════════════
@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict | None
) -> list[types.TextContent]:
    """Dispatch tool calls to the appropriate memory server endpoint.

    Args:
        name: The MCP tool name requested by the client.
        arguments: Keyword arguments passed from the client.

    Returns:
        A list containing a single TextContent with the result or error.
    """
    if arguments is None:
        arguments = {}

    async with httpx.AsyncClient() as client:
        try:
            # ── 1. indexar_archivo → POST /index-file ──────────────
            if name == "indexar_archivo":
                file_path = arguments.get("file_path")
                content = arguments.get("content")
                language = arguments.get("language")

                if not file_path:
                    return [types.TextContent(type="text", text="Error: Se requiere el parametro 'file_path'.")]

                if content and language:
                    payload = {
                        "file_path": file_path, "content": content,
                        "language": language, "project_id": _get_project_id(),
                    }
                    resp = await client.post(f"{BASE_URL}/index-file", json=payload)
                    resp.raise_for_status()
                    data = resp.json()
                else:
                    payload = {
                        "file_paths": [file_path],
                        "clear_first": False,
                        "project_id": _get_project_id(),
                    }
                    resp = await client.post(f"{BASE_URL}/index-file-paths", json=payload)
                    resp.raise_for_status()
                    data = resp.json()

                return [
                    types.TextContent(
                        type="text",
                        text=(
                            f"Archivo '{file_path}' indexado correctamente.\n"
                            f"   Fragmentos generados: {data.get('chunks_indexed', 0)}\n"
                            f"   Hash de contenido:   {data.get('content_hash', 'N/A')}"
                        ),
                    )
                ]

            # ── 2. indexar_proyecto → POST /index-file-paths or /index-project
            elif name == "indexar_proyecto":
                file_paths = arguments.get("file_paths", [])
                files = arguments.get("files", [])
                clear_first = arguments.get("clear_first", False)
                pid = _get_project_id()

                if not file_paths and not files:
                    return [types.TextContent(type="text", text="Error: Se requiere 'file_paths' o 'files'.")]

                if file_paths:
                    payload = {"file_paths": file_paths, "clear_first": clear_first, "project_id": pid}
                    resp = await client.post(f"{BASE_URL}/index-file-paths", json=payload, timeout=300)
                    resp.raise_for_status()
                    data = resp.json()
                    errors = data.get("errors", [])
                    msg = f"Proyecto indexado (via paths).\n   Archivos: {data.get('files_indexed', 0)}, Fragmentos: {data.get('chunks_indexed', 0)}"
                    if errors:
                        msg += f"\n   Errores: {len(errors)}"
                        for e in errors[:5]:
                            msg += f"\n   - {e.get('file_path', '?')}: {e.get('error', '?')}"
                    return [types.TextContent(type="text", text=msg)]

                MAX_PAYLOAD = 60000
                batches = []
                current_batch = []
                current_size = 0
                for f in files:
                    fsize = len(json.dumps(f))
                    if current_batch and current_size + fsize > MAX_PAYLOAD:
                        batches.append(current_batch)
                        current_batch = []
                        current_size = 0
                    current_batch.append(f)
                    current_size += fsize
                if current_batch:
                    batches.append(current_batch)

                total_files = 0
                total_chunks = 0
                for i, batch in enumerate(batches):
                    payload = {"files": batch, "clear_first": (clear_first and i == 0), "project_id": pid}
                    resp = await client.post(f"{BASE_URL}/index-project", json=payload, timeout=300)
                    resp.raise_for_status()
                    data = resp.json()
                    total_files += data.get("files_indexed", 0)
                    total_chunks += data.get("chunks_indexed", 0)

                msg = f"Proyecto indexado correctamente.\n   Archivos procesados: {total_files}\n   Fragmentos totales:  {total_chunks}"
                if len(batches) > 1:
                    msg += f"\n   Lotes utilizados: {len(batches)} (auto-batching activo)"
                return [types.TextContent(type="text", text=msg)]

            # ── 3. buscar_codigo → POST /semantic-search ──────────
            elif name == "buscar_codigo":
                query = arguments.get("query")
                if not query:
                    return [
                        types.TextContent(
                            type="text",
                            text="Error: Se requiere el parámetro 'query'.",
                        )
                    ]

                n_results = arguments.get("n_results", 10)
                payload = {
                    "prompt": query,
                    "n_results": n_results,
                    "project_id": _get_project_id(),
                }
                resp = await client.post(f"{BASE_URL}/semantic-search", json=payload)
                resp.raise_for_status()
                data = resp.json()

                return [
                    types.TextContent(
                        type="text",
                        text=json.dumps(data, ensure_ascii=False, indent=2),
                    )
                ]

            # ── 4. recuperar_contexto → POST /retrieve-context ────
            elif name == "recuperar_contexto":
                query = arguments.get("query")
                if not query:
                    return [
                        types.TextContent(
                            type="text",
                            text="Error: Se requiere el parámetro 'query'.",
                        )
                    ]

                n_results = arguments.get("n_results", 5)
                payload = {
                    "prompt": query,
                    "n_results": n_results,
                    "project_id": _get_project_id(),
                }
                resp = await client.post(f"{BASE_URL}/retrieve-context", json=payload)
                resp.raise_for_status()
                data = resp.json()

                return [
                    types.TextContent(
                        type="text",
                        text=data.get("context", "No se encontró contexto relevante."),
                    )
                ]

            # ── 5. guardar_decision → POST /remember-decision ──────
            elif name == "guardar_decision":
                decision = arguments.get("decision")
                context = arguments.get("context")

                if not decision or not context:
                    return [
                        types.TextContent(
                            type="text",
                            text="Error: Se requieren los parámetros 'decision' y 'context'.",
                        )
                    ]

                payload = {
                    "key_decision": decision,
                    "context": context,
                    "project_id": _get_project_id(),
                }
                resp = await client.post(
                    f"{BASE_URL}/remember-decision", json=payload
                )
                resp.raise_for_status()
                data = resp.json()

                return [
                    types.TextContent(
                        type="text",
                        text=f"✅ Decisión guardada exitosamente con ID: {data.get('id', 'desconocido')}",
                    )
                ]

            # ── 6. guardar_conversacion → POST /save-conversation ─
            elif name == "guardar_conversacion":
                session_id = arguments.get("session_id")
                messages = arguments.get("messages", [])
                summarise = arguments.get("summarise", False)

                if not session_id or not messages:
                    return [
                        types.TextContent(
                            type="text",
                            text="Error: Se requieren los parámetros 'session_id' y 'messages'.",
                        )
                    ]

                payload = {
                    "session_id": session_id,
                    "messages": messages,
                    "summarise": summarise,
                    "project_id": _get_project_id(),
                }
                resp = await client.post(
                    f"{BASE_URL}/save-conversation", json=payload
                )
                resp.raise_for_status()
                data = resp.json()

                return [
                    types.TextContent(
                        type="text",
                        text=f"✅ Conversación '{session_id}' guardada: {data.get('turns', 0)} turnos persistidos.",
                    )
                ]

            # ── 7. cargar_conversacion → POST /load-conversation ──
            elif name == "cargar_conversacion":
                session_id = arguments.get("session_id")
                if not session_id:
                    return [
                        types.TextContent(
                            type="text",
                            text="Error: Se requiere el parámetro 'session_id'.",
                        )
                    ]

                limit = arguments.get("limit", 20)
                payload = {
                    "session_id": session_id,
                    "limit": limit,
                    "summary_only": False,
                    "project_id": _get_project_id(),
                }
                resp = await client.post(
                    f"{BASE_URL}/load-conversation", json=payload
                )
                resp.raise_for_status()
                data = resp.json()

                return [
                    types.TextContent(
                        type="text",
                        text=json.dumps(data, ensure_ascii=False, indent=2),
                    )
                ]

            # ── 8. indexar_documento → POST /index-document ────────
            elif name == "indexar_documento":
                file_path = arguments.get("file_path")
                if not file_path:
                    return [
                        types.TextContent(
                            type="text",
                            text="Error: Se requiere el parámetro 'file_path'.",
                        )
                    ]

                payload: dict = {
                    "file_path": file_path,
                    "project_id": _get_project_id(),
                }
                doc_type = arguments.get("doc_type")
                if doc_type:
                    payload["doc_type"] = doc_type

                resp = await client.post(f"{BASE_URL}/index-document", json=payload)
                resp.raise_for_status()
                data = resp.json()

                return [
                    types.TextContent(
                        type="text",
                        text=(
                            f"✅ Documento indexado:\n"
                            f"{json.dumps(data, ensure_ascii=False, indent=2)}"
                        ),
                    )
                ]

            # ── 9. buscar_documentos → POST /search-documents ──────
            elif name == "buscar_documentos":
                query = arguments.get("query")
                if not query:
                    return [
                        types.TextContent(
                            type="text",
                            text="Error: Se requiere el parámetro 'query'.",
                        )
                    ]

                n_results = arguments.get("n_results", 5)
                payload: dict = {
                    "query": query,
                    "n_results": n_results,
                    "project_id": _get_project_id(),
                }
                doc_type = arguments.get("doc_type")
                if doc_type:
                    payload["doc_type"] = doc_type

                resp = await client.post(
                    f"{BASE_URL}/search-documents", json=payload
                )
                resp.raise_for_status()
                data = resp.json()

                return [
                    types.TextContent(
                        type="text",
                        text=json.dumps(data, ensure_ascii=False, indent=2),
                    )
                ]

            # ── 10. listar_documentos → GET /list-documents ────────
            elif name == "listar_documentos":
                resp = await client.get(
                    f"{BASE_URL}/list-documents",
                    params={"project_id": _get_project_id()},
                )
                resp.raise_for_status()
                data = resp.json()

                return [
                    types.TextContent(
                        type="text",
                        text=json.dumps(data, ensure_ascii=False, indent=2),
                    )
                ]

            # ── 11. info_proyecto → POST /project-info ─────────────
            elif name == "info_proyecto":
                payload = {"project_id": _get_project_id()}
                resp = await client.post(f"{BASE_URL}/project-info", json=payload)
                resp.raise_for_status()
                data = resp.json()
                stats = data.get("stats", {})
                pid = data.get("project_id", "")
                text = f"Proyecto: {pid}\n"
                text += f"  Chunks de código: {stats.get('code_chunks', 0)}\n"
                text += f"  Chunks de documentos: {stats.get('document_chunks', 0)}\n"
                text += f"  Conversaciones: {stats.get('conversations', 0)}\n"
                text += f"  Decisiones: {stats.get('decisions', 0)}\n"
                text += f"  Tareas: {stats.get('tasks', 0)}"
                return [
                    types.TextContent(
                        type="text",
                        text=text,
                    )
                ]

            # ── 12. registrar_tarea → POST /tasks/upsert ──────────
            elif name == "registrar_tarea":
                title = arguments.get("title")
                if not title:
                    return [types.TextContent(
                        type="text",
                        text="Error: Se requiere el parametro 'title'."
                    )]

                payload = {
                    "title": title,
                    "description": arguments.get("description", ""),
                    "context": arguments.get("context", ""),
                    "status": arguments.get("status", "pending"),
                    "priority": arguments.get("priority", "medium"),
                    "dependencies": arguments.get("dependencies", []),
                    "project_id": _get_project_id(),
                }
                task_id = arguments.get("task_id")
                if task_id:
                    payload["task_id"] = task_id

                resp = await client.post(f"{BASE_URL}/tasks/upsert", json=payload)
                resp.raise_for_status()
                data = resp.json()
                return [types.TextContent(
                    type="text",
                    text=(
                        f"Tarea {data.get('status', 'guardada')}: {data.get('task_id', '?')}\n"
                        f"  Titulo: {data.get('title', title)}"
                    ),
                )]

            # ── 13. listar_tareas → GET /tasks ────────────────────
            elif name == "listar_tareas":
                params = {"project_id": _get_project_id()}
                st = arguments.get("status")
                pr = arguments.get("priority")
                if st:
                    params["status"] = st
                if pr:
                    params["priority"] = pr
                resp = await client.get(f"{BASE_URL}/tasks", params=params)
                resp.raise_for_status()
                data = resp.json()
                tasks = data.get("tasks", [])
                if not tasks:
                    return [types.TextContent(
                        type="text",
                        text="No hay tareas registradas."
                    )]
                text = f"Tareas ({data.get('count', 0)}):\n"
                for t in tasks:
                    status_icon = {"pending": "[ ]", "in_progress": "[~]", "completed": "[x]", "cancelled": "[-]"}
                    icon = status_icon.get(t["status"], "[?]")
                    text += f"  {icon} [{t['priority']}] {t['title']}  ({t['id']})\n"
                return [types.TextContent(type="text", text=text)]

            # ── 14. buscar_tareas → POST /tasks/search ────────────
            elif name == "buscar_tareas":
                query = arguments.get("query")
                if not query:
                    return [types.TextContent(
                        type="text",
                        text="Error: Se requiere el parametro 'query'."
                    )]
                payload = {
                    "query": query,
                    "n_results": arguments.get("n_results", 5),
                    "project_id": _get_project_id(),
                }
                st = arguments.get("status")
                if st:
                    payload["status"] = st
                resp = await client.post(f"{BASE_URL}/tasks/search", json=payload)
                resp.raise_for_status()
                data = resp.json()
                return [types.TextContent(
                    type="text",
                    text=json.dumps(data, ensure_ascii=False, indent=2),
                )]

            # ── 15. contexto_sesion → POST /session-context ───────
            elif name == "contexto_sesion":
                payload = {
                    "project_id": _get_project_id(),
                    "include_tasks": arguments.get("include_tasks", True),
                    "include_decisions": arguments.get("include_decisions", True),
                    "include_code": arguments.get("include_code", False),
                    "include_documents": arguments.get("include_documents", False),
                    "n_results": 5,
                }
                resp = await client.post(f"{BASE_URL}/session-context", json=payload)
                resp.raise_for_status()
                data = resp.json()
                ctx = data.get("context", "")
                if not ctx.strip():
                    return [types.TextContent(type="text", text="No hay contexto de sesión disponible.")]
                return [types.TextContent(type="text", text=ctx)]

            # ── 16. consolidar_memoria → POST /consolidate ────────
            elif name == "consolidar_memoria":
                payload = {"project_id": _get_project_id()}
                resp = await client.post(f"{BASE_URL}/consolidate", json=payload)
                resp.raise_for_status()
                data = resp.json()
                report = "\n".join(f"  - {r}" for r in data.get("report", []))
                text = (
                    f"Consolidacion completada.\n"
                    f"  Tareas obsoletas: {data.get('stale_tasks_found', 0)}\n"
                    f"  Re-promocionadas: {data.get('tasks_re_promoted', 0)}\n"
                    f"Reporte:\n{report}"
                )
                return [types.TextContent(type="text", text=text)]

            # ── Unknown tool ───────────────────────────────────────
            else:
                return [
                    types.TextContent(
                        type="text",
                        text=f"Error: Herramienta desconocida '{name}'. Las herramientas disponibles son: indexar_archivo, indexar_proyecto, buscar_codigo, recuperar_contexto, guardar_decision, guardar_conversacion, cargar_conversacion, indexar_documento, buscar_documentos, listar_documentos, info_proyecto, registrar_tarea, listar_tareas, buscar_tareas, contexto_sesion, consolidar_memoria.",
                    )
                ]

        # ── Structured error handling ──────────────────────────────
        except httpx.ConnectError:
            return [
                types.TextContent(
                    type="text",
                    text=(
                    "Error de conexión: No se puede conectar al servidor de "
                    "memoria en http://127.0.0.1:8006.\n"
                    "Asegúrate de que memory_server.py esté en ejecución:\n"
                    "  uvicorn memory_server:app --host 127.0.0.1 --port 8006"
                    ),
                )
            ]

        except httpx.TimeoutException:
            return [
                types.TextContent(
                    type="text",
                    text="Error: Timeout al comunicarse con el servidor de memoria. El servidor podría estar sobrecargado.",
                )
            ]

        except httpx.HTTPStatusError as exc:
            detail = ""
            try:
                detail = exc.response.json().get("detail", str(exc))
            except Exception:
                detail = str(exc)
            return [
                types.TextContent(
                    type="text",
                    text=f"Error del servidor (HTTP {exc.response.status_code}): {detail}",
                )
            ]

        except json.JSONDecodeError:
            return [
                types.TextContent(
                    type="text",
                    text="Error: El servidor devolvió una respuesta no válida (no es JSON).",
                )
            ]

        except Exception as exc:
            return [
                types.TextContent(
                    type="text",
                    text=f"Error inesperado: {type(exc).__name__}: {exc}",
                )
            ]


# ═══════════════════════════════════════════════════════════════════════
#  Entry point — stdio transport
# ═══════════════════════════════════════════════════════════════════════
async def main() -> None:
    """Launch the MCP server over stdio transport."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="KinnyCode-Memory-RAG",
                server_version="0.4.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())
