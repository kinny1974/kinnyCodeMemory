# Plugin TypeScript para OpenCode - KinnyCode Memory

## Descripción

Plugin nativo de TypeScript para OpenCode que conecta al servidor de memoria KinnyCode Memory. Proporciona 18 herramientas MCP para indexación, búsqueda y gestión de memoria.

**Ventajas sobre el MCP Wrapper (Python):**
- Sin dependencias Python
- Mejor rendimiento (compilado a JavaScript)
- Integración nativa con OpenCode
- Soporte completo de TypeScript

## Requisitos Previos

1. **Node.js** 18+ instalado
2. **OpenCode** instalado y funcionando
3. **Servidor KinnyCode Memory** corriendo (local o remoto)

## Instalación

### Opción 1: Desde el repositorio (recomendado)

```bash
# 1. Clonar el repositorio
git clone https://github.com/kinny1974/kinnyCodeMemory.git
cd kinnyCodeMemory/plugin-kinnycode

# 2. Instalar dependencias
npm install

# 3. Compilar
npm run build
```

### Opción 2: Copiar solo el plugin

Si solo necesitas el plugin sin el resto del repositorio:

```bash
# 1. Crear directorio del plugin
mkdir -p ~/.opencode/plugin/kinnycode-memory
cd ~/.opencode/plugin/kinnycode-memory

# 2. Copiar archivos necesarios
# (src/index.ts, package.json, tsconfig.json)

# 3. Instalar y compilar
npm install
npm run build
```

## Configuración

### Paso 1: Editar opencode.jsonc

Abre tu archivo de configuración de OpenCode:

- **Windows:** `C:\Users\<usuario>\.config\opencode\opencode.jsonc`
- **Linux/macOS:** `~/.config/opencode/opencode.jsonc`

Agrega la siguiente configuración:

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "plugin": [
    ["opencode-kinnycode-memory", {
      "serverUrl": "http://192.168.2.111:8007",
      "projectId": "a67d4e5165ff6b92"
    }]
  ]
}
```

### Paso 2: Configurar parámetros

| Parámetro | Tipo | Descripción | Ejemplo |
|-----------|------|-------------|---------|
| `serverUrl` | string | URL del servidor KinnyCode Memory | `http://192.168.2.111:8007` |
| `projectId` | string | ID del proyecto por defecto | `a67d4e5165ff6b92` |

### Paso 3: Reiniciar OpenCode

Cierra y vuelve a abrir OpenCode para que los cambios surtan efecto.

### Paso 4: Verificar

Escribe `/mcp` en OpenCode. Deberías ver `kinnycode-memory` en la lista de servidores MCP.

## Herramientas Disponibles

El plugin expone las siguientes 18 herramientas:

### Indexación de Código (L3)

| Herramienta | Descripción | Parámetros |
|-------------|-------------|------------|
| `indexar_archivo` | Indexa un archivo de código fuente | `file_path`, `content`, `language` |
| `reindexar_archivo` | Re-indexa un archivo si cambió | `file_path`, `content`, `language` |
| `indexar_proyecto` | Indexa múltiples archivos en lote | `file_paths[]`, `clean_first` |

### Búsqueda

| Herramienta | Descripción | Parámetros |
|-------------|-------------|------------|
| `buscar_codigo` | Búsqueda semántica en código | `prompt`, `n_results` |
| `recuperar_contexto` | RAG completo (todas las capas) | `prompt`, `layers[]` |

### Documentos (L4)

| Herramienta | Descripción | Parámetros |
|-------------|-------------|------------|
| `indexar_documento` | Indexa PDF/MD/TXT | `file_path`, `doc_type` |
| `buscar_documentos` | Busca en documentos | `query`, `n_results` |
| `listar_documentos` | Lista documentos indexados | - |
| `eliminar_documento` | Elimina un documento | `source_file` |

### Conversaciones (L2)

| Herramienta | Descripción | Parámetros |
|-------------|-------------|------------|
| `guardar_conversacion` | Guarda historial de conversación | `session_id`, `messages[]` |
| `cargar_conversacion` | Recupera historial | `session_id` |

### Decisiones (L2)

| Herramienta | Descripción | Parámetros |
|-------------|-------------|------------|
| `guardar_decision` | Guarda una decisión técnica | `key_decision`, `context` |

### Tareas (L5)

| Herramienta | Descripción | Parámetros |
|-------------|-------------|------------|
| `guardar_tarea` | Crea/actualiza una tarea | `title`, `description`, `status`, `priority` |
| `buscar_tareas` | Búsqueda semántica de tareas | `query`, `n_results`, `status` |

### Utilidades

| Herramienta | Descripción | Parámetros |
|-------------|-------------|------------|
| `info_proyecto` | Muestra estadísticas del proyecto | - |
| `consolidar_memoria` | Consolida memoria de largo plazo | - |
| `contexto_sesion` | Contexto proactivo de sesión | `recent_messages[]` |
| `limpiar_proyecto` | Limpia datos del proyecto | `confirm` |

## Ejemplos de Uso

### Buscar en el codebase

```
buscar_codigo(
    prompt="¿Cómo funciona el sistema de embeddings?",
    n_results=5
)
```

### Indexar un archivo nuevo

```
indexar_archivo(
    file_path="src/nuevo_modulo.py",
    content="def mi_funcion(): ...",
    language="python"
)
```

### Recuperar contexto completo

```
recuperar_contexto(
    prompt="¿Qué decisiones de arquitectura tomamos para el sistema de memoria?",
    layers=["code", "documents", "conversations", "decisions"]
)
```

### Guardar una decisión

```
guardar_decision(
    key_decision="Usar TypeScript para el plugin",
    context="Decidimos usar TypeScript en lugar de Python para mejor rendimiento y integración nativa con OpenCode."
)
```

### Crear una tarea

```
guardar_tarea(
    title="Implementar autenticación API",
    description="Agregar autenticación con tokens JWT al servidor",
    status="pending",
    priority="high"
)
```

## Arquitectura

```
┌─────────────────┐      HTTP/REST       ┌─────────────────────┐
│   OpenCode      │ ───────────────────▶ │  KinnyCode Memory   │
│   (Plugin TS)   │                      │  Server (FastAPI)   │
└─────────────────┘                      └──────────┬──────────┘
                                                    │
                                           ┌────────▼────────┐
                                           │     LanceDB     │
                                           │   (Base datos)  │
                                           └─────────────────┘
```

El plugin se comunica directamente con el servidor FastAPI mediante HTTP/REST. No hay protocolo MCP intermedio.

## Solución de Problemas

### Error: "Cannot connect to server"

1. Verifica que el servidor esté corriendo:
   ```bash
   curl http://192.168.2.111:8007/health
   ```

2. Verifica la URL en `opencode.jsonc`

3. Verifica la conectividad de red:
   ```bash
   ping 192.168.2.111
   ```

### Error: "Plugin not found"

1. Verifica que el plugin esté compilado:
   ```bash
   ls ~/.opencode/plugin/kinnycode-memory/dist/
   ```

2. Reinstala dependencias:
   ```bash
   cd ~/.opencode/plugin/kinnycode-memory
   npm install
   npm run build
   ```

### Error: "Project ID not found"

1. Verifica el project_id en `opencode.jsonc`

2. Lista proyectos disponibles:
   ```bash
   curl -X POST http://192.168.2.111:8007/project-info \
     -H "Content-Type: application/json" \
     -d '{"project_id": "a67d4e5165ff6b92"}'
   ```

### Logs del servidor

```bash
# Ver logs en tiempo real
ssh hell-house "journalctl -u kinnycodememory -f"

# Ver logs recientes
ssh hell-house "journalctl -u kinnycodememory --no-pager -n 50"
```

## Project IDs

| Project ID | Descripción |
|------------|-------------|
| `a67d4e5165ff6b92` | Proyecto principal (KinnyCode Memory) |

## Notas Importantes

1. **Seguridad**: El servidor no tiene autenticación API configurada. Solo úsalo en red local o configura un proxy con autenticación.

2. **Rendimiento**: La primera consulta puede tardar ~10s mientras se carga el modelo de embeddings.

3. **Espacio en disco**: La base de datos ocupa ~6.8 GB. Monitorea el espacio disponible.

4. **Backups**: Realiza backups regulares de la base de datos:
   ```bash
   ssh hell-house "sudo tar -czf /tmp/backup_$(date +%Y%m%d).tar.gz -C /opt/KinnyCodeMemory lancedb_memory_db"
   ```

---

*Última actualización: 2026-08-09*
