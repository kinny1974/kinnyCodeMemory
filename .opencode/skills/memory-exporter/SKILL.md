---
name: memory-exporter
description: Exporta toda la memoria agentiva (código, tareas, decisiones, documentos) a archivos estructurados
---

# Skill: memory-exporter
# Framework: OpenCode-AI EitL — Memoria Multicapa

## Role
Eres un especialista en persistencia de memoria. Tu trabajo es **extraer toda la información almacenada en las 4 capas de memoria agentiva** (C1: conversaciones, C2: decisiones, C3: código indexado, C4: documentos) y escribirla a archivos estructurados en el disco para backup, migración o revisión.

## Script de Exportación (Implementación Real)
Este skill describe el método basado en MCP tools del servidor de memoria. Como **alternativa**, existe el script `memory-portability/export_memory.ps1` (skill `portability-export`) que hace una exportación más completa escaneando el sistema de archivos directamente, generando índices SHA-256 para todos los archivos del proyecto, y produciendo el formato portable SIGMA-Team con `data/` + `metadata/`.

## Input
- `output_dir`: Directorio donde se escribirán los archivos de exportación (por defecto `.opencode/memory-export/`)
- `include_layers`: Lista de capas a exportar (por defecto: `["c1", "c2", "c3", "c4"]`)
- `timestamp`: Timestamp ISO para etiquetar la exportación

## Output
En `output_dir` se genera una carpeta con timestamp que contiene:

```
memory-export_2026-07-02_150000/
├── _manifest.json              # Metadatos de la exportación
├── capa1_conversaciones/
│   └── conversaciones.json     # Historial de conversaciones guardadas
├── capa2_decisiones/
│   └── decisiones.json         # Decisiones de arquitectura
├── capa3_codigo/
│   ├── chunks_indexados.json   # Fragmentos de código indexados
│   └── archivos_referencia.txt # Lista de archivos fuente
├── capa4_documentos/
│   └── documentos.json         # Documentos indexados
├── tareas/
│   └── tareas.json             # Tareas agentivas (pendientes/en_progreso/completadas)
└── contexto_proyecto.md        # Resumen ejecutivo del estado del proyecto
```

## MCP Tools Utilizadas

### Lectura de memoria (EXPORTAR)

```python
# 1. Estadísticas del proyecto
info = mcp.kinnycode-memory_info_proyecto()

# 2. Listar todas las tareas (por estado)
tareas_pendientes = mcp.kinnycode-memory_listar_tareas(status="pending")
tareas_progreso  = mcp.kinnycode-memory_listar_tareas(status="in_progress")
tareas_completadas = mcp.kinnycode-memory_listar_tareas(status="completed")

# 3. Listar todos los documentos indexados
documentos = mcp.kinnycode-memory_listar_documentos()

# 4. Recuperar decisiones guardadas
#    (Se buscan semánticamente con queries amplias)
decisiones_1 = mcp.kinnycode-memory_buscar_codigo(query="decisión arquitectura", n_results=50)
decisiones_2 = mcp.kinnycode-memory_buscar_codigo(query="decisión diseño", n_results=50)

# 5. Buscar fragmentos de código indexados (queries semánticas amplias)
chunks_codigo = []
for query in ["clase principal", "función API", "modelo datos", "ruta endpoint",
              "configuración", "servicio", "base de datos", "consulta SQL",
              "componente React", "hook", "test", "migración"]:
    chunks = mcp.kinnycode-memory_buscar_codigo(query=query, n_results=30)
    chunks_codigo.extend(chunks)

# 6. Buscar documentos indexados
docs = mcp.kinnycode-memory_buscar_documentos(query="documentación proyecto", n_results=50)

# 7. Contexto de sesión
contexto = mcp.kinnycode-memory_contexto_sesion(
    include_tasks=True,
    include_decisions=True,
    include_code=True,
    include_documents=True
)
```

### Escritura de archivos

```python
import json
from pathlib import Path
from datetime import datetime

ts = datetime.now().strftime("%Y%m%d_%H%M%S")
export_dir = Path(output_dir) / f"memory-export_{ts}"
export_dir.mkdir(parents=True, exist_ok=True)

# Escribir cada capa
(export_dir / "capa1_conversaciones").mkdir(exist_ok=True)
(export_dir / "capa1_conversaciones" / "conversaciones.json").write_text(
    json.dumps(conversaciones_data, indent=2, ensure_ascii=False)
)

(export_dir / "capa2_decisiones").mkdir(exist_ok=True)
(export_dir / "capa2_decisiones" / "decisiones.json").write_text(
    json.dumps(decisiones_data, indent=2, ensure_ascii=False)
)

(export_dir / "capa3_codigo").mkdir(exist_ok=True)
(export_dir / "capa3_codigo" / "chunks_indexados.json").write_text(
    json.dumps(chunks_data, indent=2, ensure_ascii=False)
)

(export_dir / "capa4_documentos").mkdir(exist_ok=True)
(export_dir / "capa4_documentos" / "documentos.json").write_text(
    json.dumps(documentos_data, indent=2, ensure_ascii=False)
)

(export_dir / "tareas").mkdir(exist_ok=True)
(export_dir / "tareas" / "tareas.json").write_text(
    json.dumps(tareas_data, indent=2, ensure_ascii=False)
)

# Manifest
manifest = {
    "export_timestamp": ts,
    "project_name": "<nombre_proyecto>",
    "layers_exported": include_layers,
    "stats": {
        "tareas": len(tareas_data),
        "decisiones": len(decisiones_data),
        "chunks_codigo": len(chunks_data),
        "documentos": len(documentos_data),
        "conversaciones": len(conversaciones_data),
    }
}
(export_dir / "_manifest.json").write_text(
    json.dumps(manifest, indent=2, ensure_ascii=False)
)

# Resumen Markdown
resumen = f"""# Exportación de Memoria Agentiva

**Fecha:** {ts}
**Proyecto:** {manifest['project_name']}

## Estadísticas
| Capa | Elementos |
|------|-----------|
| Tareas | {len(tareas_data)} |
| Decisiones | {len(decisiones_data)} |
| Chunks de código | {len(chunks_data)} |
| Documentos | {len(documentos_data)} |
| Conversaciones | {len(conversaciones_data)} |
"""
(export_dir / "contexto_proyecto.md").write_text(resumen)
```

## Flujo de Exportación

1. **Recolectar metadatos**: Llamar `info_proyecto()` para obtener estadísticas generales.
2. **Exportar tareas**: Llamar `listar_tareas()` con cada estado y consolidar.
3. **Exportar documentos**: Llamar `listar_documentos()`.
4. **Exportar decisiones**: Usar `buscar_codigo()` con queries semánticas amplias para capturar decisiones guardadas.
5. **Exportar chunks de código**: Iterar queries de búsqueda semántica para cubrir la mayor superficie posible del código indexado.
6. **Exportar conversaciones**: Usar `cargar_conversacion()` para cada session_id disponible.
7. **Generar manifiesto**: Escribir `_manifest.json` con metadatos.
8. **Generar resumen**: Escribir `contexto_proyecto.md`.

## Reglas
1. **No modificar la memoria**: El exportador es solo lectura. Nunca escribir, modificar ni eliminar datos de la memoria.
2. **Deduplicar resultados**: Las búsquedas semánticas pueden devolver solapamientos. Deduplicar por `id` o `file_path` antes de escribir.
3. **UTF-8 siempre**: Todos los archivos de exportación deben codificarse en UTF-8 con `ensure_ascii=False`.
4. **Estructura de carpetas**: Mantener la jerarquía `capaN_nombre/` para facilitar la importación posterior.
5. **Manifiesto obligatorio**: Siempre incluir `_manifest.json` con timestamp, proyecto y estadísticas para validación.
6. **No exponer secretos**: Si algún chunk contiene tokens, passwords o URLs con credenciales, omitirlo de la exportación.

## Formato de salida (JSON)

### Tareas
```json
{
  "task_id": "uuid",
  "title": "string",
  "description": "string",
  "status": "pending|in_progress|completed|cancelled",
  "priority": "high|medium|low",
  "dependencies": ["task_id_1"],
  "created_at": "ISO datetime"
}
```

### Decisiones
```json
{
  "decision": "string",
  "context": "string",
  "created_at": "ISO datetime"
}
```

## Recovery / Re-import
Los archivos generados por este skill están diseñados para ser consumidos por el skill `memory-importer`. La estructura de carpetas y nombres de archivo son el contrato entre ambos skills.
