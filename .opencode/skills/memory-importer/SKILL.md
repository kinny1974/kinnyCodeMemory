---
name: memory-importer
description: Importa datos de memoria agentive desde archivos estructurados y reconstruye el estado en las 4 capas
---

# Skill: memory-importer
# Framework: OpenCode-AI EitL — Memoria Multicapa

## Role
Eres un especialista en restauración de memoria. Tu trabajo es **leer archivos de exportación** generados por el skill `memory-exporter` y **reconstruir el estado completo** en las 4 capas de memoria agentiva usando las MCP tools de escritura.

## Script de Importación (Implementación Real)
Este skill describe el método basado en MCP tools del servidor de memoria. Como **alternativa**, existe el script `memory-portability/import_memory.ps1` (skill `portability-import`) que restaura el formato portable SIGMA-Team verificando checksums SHA-256 y copiando decisiones, configuraciones de agentes y artefactos directamente al proyecto.

## Input
- `import_dir`: Ruta al directorio de exportación (ej: `.opencode/memory-export/memory-export_2026-07-02_150000/`)
- `layers`: Lista de capas a importar (por defecto: `["all"]`)
- `mode`: `"restore"` (restaura completa, limpia primero) o `"merge"` (agrega sin borrar existente)
- `confirm`: Debe ser `true` para proceder (seguridad contra imports accidentales)

## Output
- Reporte de importación: cuántos elementos se restauraron en cada capa
- Log de errores: elementos que no pudieron importarse (duplicados, fallos de validación)

## Pre-requisitos
El directorio de importación debe tener la estructura generada por `memory-exporter`:

```
memory-export_YYYY-MM-DD_HHMMSS/
├── _manifest.json
├── capa1_conversaciones/conversaciones.json
├── capa2_decisiones/decisiones.json
├── capa3_codigo/chunks_indexados.json
├── capa4_documentos/documentos.json
└── tareas/tareas.json
```

## MCP Tools Utilizadas

### Escritura de memoria (IMPORTAR)

```python
# 1. Validar manifiesto
manifest = json.loads((import_dir / "_manifest.json").read_text())
if not manifest.get("export_timestamp"):
    raise ValueError("Manifiesto inválido o ausente")

# 2. IMPORTAR TAREAS
tareas = json.loads((import_dir / "tareas" / "tareas.json").read_text())
for tarea in tareas:
    mcp.kinnycode-memory_registrar_tarea(
        task_id=tarea.get("task_id"),        # None si es nueva
        title=tarea["title"],
        description=tarea.get("description", ""),
        context=tarea.get("context", ""),
        status=tarea["status"],
        priority=tarea.get("priority", "medium"),
        dependencies=tarea.get("dependencies", [])
    )

# 3. IMPORTAR DECISIONES
decisiones = json.loads((import_dir / "capa2_decisiones" / "decisiones.json").read_text())
for decision in decisiones:
    mcp.kinnycode-memory_guardar_decision(
        decision=decision["decision"],
        context=decision.get("context", "")
    )

# 4. IMPORTAR CHUNKS DE CÓDIGO (Capa 3)
#    Los chunks exportados contienen file_path, content y language.
#    Se re-indexan archivo por archivo para regenerar los embeddings.
chunks = json.loads((import_dir / "capa3_codigo" / "chunks_indexados.json").read_text())
# Agrupar por archivo para indexar una sola vez por archivo
archivos = {}
for chunk in chunks:
    fp = chunk.get("file_path")
    if fp:
        archivos[fp] = {
            "file_path": fp,
            "content": chunk.get("content", ""),
            "language": chunk.get("language", "unknown")
        }

for file_path, info in archivos.items():
    mcp.kinnycode-memory_indexar_archivo(
        file_path=info["file_path"],
        content=info["content"],
        language=info["language"]
    )

# 5. IMPORTAR DOCUMENTOS (Capa 4)
documentos = json.loads((import_dir / "capa4_documentos" / "documentos.json").read_text())
for doc in documentos:
    mcp.kinnycode-memory_indexar_documento(
        file_path=doc["file_path"],
        doc_type=doc.get("doc_type")  # se infiere de extensión si es None
    )

# 6. IMPORTAR CONVERSACIONES (Capa 1)
conversaciones = json.loads(
    (import_dir / "capa1_conversaciones" / "conversaciones.json").read_text()
)
for conv in conversaciones:
    mcp.kinnycode-memory_guardar_conversacion(
        session_id=conv["session_id"],
        messages=conv["messages"],
        summarise=conv.get("summarise", False)
    )
```

## Flujo de Importación

### Modo `restore` (por defecto)
1. **Validar** el manifiesto y la estructura del directorio.
2. **Limpiar** la memoria existente (opcional, vía `indexar_proyecto(clear_first=true)` para código, el resto se sobreescribe).
3. **Importar** cada capa en orden: Tareas → Decisiones → Código → Documentos → Conversaciones.
4. **Consolidar** la memoria con `consolidar_memoria()` para recalcular scores de Ebbinghaus.
5. **Verificar** con `info_proyecto()` que los conteos coincidan con el manifiesto.

### Modo `merge`
1. **Validar** el manifiesto.
2. **Importar** cada capa sin limpiar primero. Los elementos duplicados (mismo `task_id`, `file_path` o `session_id`) se saltan.
3. **Consolidar** y **verificar**.

## Reglas
1. **Seguridad ante todo**: Requerir `confirm=true` explícito. Si no está presente, abortar con mensaje de advertencia.
2. **Validación de manifiesto**: Siempre verificar que `_manifest.json` existe y tiene `export_timestamp` antes de proceder.
3. **Integridad por capa**: Si una capa falla (archivo faltante o corrupto), registrar el error pero continuar con las demás capas.
4. **Deduplicación en merge mode**: Antes de importar una tarea, verificar si ya existe con el mismo `task_id`. Antes de indexar un archivo, verificar si ya está indexado.
5. **UTF-8**: Todos los archivos de entrada deben leerse como UTF-8.
6. **Reporte final**: Generar un resumen con:
   - Tareas importadas: ✅ / ❌
   - Decisiones importadas: ✅ / ❌
   - Archivos re-indexados: ✅ / ❌
   - Documentos re-indexados: ✅ / ❌
   - Conversaciones restauradas: ✅ / ❌
   - Consolidación: ✅ / ❌

## Validación Pre-import

```python
def validate_import(import_dir, manifest):
    errors = []
    required_files = [
        "_manifest.json",
        "tareas/tareas.json",
        "capa2_decisiones/decisiones.json",
        "capa3_codigo/chunks_indexados.json",
        "capa4_documentos/documentos.json",
        "capa1_conversaciones/conversaciones.json",
    ]
    for rel_path in required_files:
        full_path = import_dir / rel_path
        if not full_path.exists():
            errors.append(f"Archivo requerido ausente: {rel_path}")

    # Validar estructura del JSON
    for rel_path in required_files[1:]:
        try:
            data = json.loads((import_dir / rel_path).read_text())
            if not isinstance(data, list):
                errors.append(f"Formato inválido: {rel_path} debe ser un array JSON")
        except json.JSONDecodeError:
            errors.append(f"JSON inválido: {rel_path}")

    return errors
```

## Reporte de Salida

```markdown
## Reporte de Importación de Memoria

**Origen:** memory-export_2026-07-02_150000
**Modo:** restore | merge
**Fecha:** 2026-07-02 16:00:00

### Resultados por Capa
| Capa | Esperados | Importados | Errores | Estado |
|------|-----------|------------|---------|--------|
| Tareas | 12 | 12 | 0 | ✅ |
| Decisiones | 5 | 5 | 0 | ✅ |
| Código (archivos) | 48 | 48 | 0 | ✅ |
| Documentos | 3 | 3 | 0 | ✅ |
| Conversaciones | 2 | 2 | 0 | ✅ |

### Estado Final de Memoria
- Chunks de código: 156
- Chunks de documentos: 12
- Conversaciones: 2
- Decisiones: 5
- Tareas: 12

### Próximos Pasos Recomendados
1. Verificar que las búsquedas semánticas devuelvan resultados esperados.
2. Ejecutar `consolidar_memoria()` si no se ejecutó automáticamente.
```
