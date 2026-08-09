# OpenCode Plugin - KinnyCode Memory

Plugin nativo de TypeScript para OpenCode que se conecta directamente al servidor KinnyCode Memory sin necesidad del wrapper MCP en Python.

## Ventajas sobre el MCP Wrapper

| Característica | MCP Wrapper (Python) | Plugin (TypeScript) |
|----------------|---------------------|---------------------|
| **Dependencias** | Python + httpx + mcp | Solo Node.js |
| **Instalación** | Manual | Automática via npm |
| **Rendimiento** | Proceso separado | Integrado en OpenCode |
| **Mantenimiento** | Dos codebases | Un solo codebase |
| **Distribución** | Archivo .py | Paquete npm |

## Instalación

### Opción 1: Instalación local (recomendado)

```bash
# Navegar al directorio del plugin
cd F:\kinnyCodeMemory\plugin-kinnycode

# Instalar dependencias
npm install

# Compilar
npm run build
```

### Opción 2: Instalación global

```bash
# Instalar globalmente
npm install -g opencode-kinnycode-memory

# O usar npm link
cd F:\kinnyCodeMemory\plugin-kinnycode
npm link
```

## Configuración

### 1. Editar opencode.jsonc

Abre `C:\Users\anonymous\.config\opencode\opencode.jsonc`:

```jsonc
{
  "plugin": [
    ["opencode-kinnycode-memory", {
      "serverUrl": "http://192.168.2.111:8007",
      "projectId": "6b6a8b869aea48ad"
    }]
  ]
}
```

### 2. Variables de entorno (alternativa)

```powershell
# Establecer variables de entorno
$env:KINNYCODE_SERVER_URL = "http://192.168.2.111:8007"
$env:KINNYCODE_PROJECT_ID = "6b6a8b869aea48ad"
```

Luego en opencode.jsonc:

```jsonc
{
  "plugin": ["opencode-kinnycode-memory"]
}
```

## Herramientas Disponibles

El plugin expone las siguientes **18 herramientas**:

### Indexación (4)
| Herramienta | Descripción |
|-------------|-------------|
| `indexar_archivo` | Indexa un archivo de código |
| `indexar_proyecto` | Indexa múltiples archivos |
| `indexar_documento` | Indexa PDF/MD/TXT |
| `reindexar_archivo` | Re-indexa si el hash cambió |

### Búsqueda (3)
| Herramienta | Descripción |
|-------------|-------------|
| `buscar_codigo` | Búsqueda semántica en código |
| `buscar_documentos` | Búsqueda en documentos |
| `recuperar_contexto` | RAG completo (todas las capas) |

### Gestión de Documentos (2)
| Herramienta | Descripción |
|-------------|-------------|
| `listar_documentos` | Lista documentos indexados |
| `eliminar_documento` | Elimina un documento |

### Conversaciones y Decisiones (3)
| Herramienta | Descripción |
|-------------|-------------|
| `guardar_conversacion` | Guarda historial |
| `cargar_conversacion` | Recupera historial |
| `guardar_decision` | Guarda decisión técnica |

### Tareas (2)
| Herramienta | Descripción |
|-------------|-------------|
| `guardar_tarea` | Crea/actualiza una tarea (L5) |
| `buscar_tareas` | Búsqueda semántica en tareas |

### Gestión de Memoria (3)
| Herramienta | Descripción |
|-------------|-------------|
| `consolidar_memoria` | Consolida memoria (elimina obsoletos) |
| `contexto_sesion` | Contexto proactivo de sesión |
| `limpiar_proyecto` | Elimina todos los datos del proyecto |

### Proyecto (1)
| Herramienta | Descripción |
|-------------|-------------|
| `info_proyecto` | Estadísticas del proyecto |

## Ejemplo de Uso

Una vez configurado, puedes usar las herramientas directamente en OpenCode:

```
# Buscar en el codebase
indexar_archivo con file_path="src/main.py", content="...", language="python"

# Buscar código relevante
buscar_codigo con prompt="¿Cómo funciona el sistema de embeddings?"

# Recuperar contexto completo
recuperar_contexto con prompt="¿Qué decisiones de arquitectura tomamos?"
```

## Project IDs Disponibles

| Project ID | Descripción |
|------------|-------------|
| `6b6a8b869aea48ad` | Proyecto principal (KinnyCode) |
| `ccf515ff0c3fe492` | Documentos |
| `1b09b364b8400c7c` | Proyecto secundario |

## Desarrollo

### Estructura del proyecto

```
plugin-kinnycode/
├── src/
│   └── index.ts        # Código fuente del plugin
├── dist/               # Archivos compilados
├── package.json
├── tsconfig.json
└── README.md
```

### Compilar en modo desarrollo

```bash
npm run dev
```

Esto compilará automáticamente cada vez que hagas cambios en `src/index.ts`.

### Testing

```bash
# Abrir OpenCode con el plugin
opencode

# Verificar que el plugin esté cargado
/mcp
```

## Solución de Problemas

### Error: "Cannot find module"

```bash
# Reinstalar dependencias
rm -rf node_modules
npm install

# Recompilar
npm run build
```

### Error: "Server connection failed"

1. Verifica que el servidor esté corriendo:
   ```bash
   ssh hell-house "systemctl status kinnycodememory"
   ```

2. Verifica la URL del servidor en la configuración

### Error: "Project ID not found"

```bash
# Verificar proyectos disponibles
curl -X POST http://192.168.2.111:8007/project-info \
  -H "Content-Type: application/json" \
  -d '{"project_id": "6b6a8b869aea48ad"}'
```

## Licencia

MIT
