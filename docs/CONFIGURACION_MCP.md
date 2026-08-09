# Guia de Configuracion MCP - KinnyCode Memory Server

## Visión General

Esta guia explica cómo configurar OpenCode para conectarse al servidor de memoria KinnyCode Memory en tu servidor Linux remoto (192.168.2.111:8007).

**Tienes dos opciones de configuración:**

| Opción | Descripción | Ventajas |
|--------|-------------|----------|
| **Plugin TypeScript** (recomendado) | Plugin nativo para OpenCode | Sin dependencias Python, mejor rendimiento |
| **MCP Wrapper** (legacy) | Wrapper en Python | Compatible con cualquier cliente MCP |

## Requisitos Previos

1. **OpenCode** instalado y funcionando
2. **Servidor KinnyCode Memory** corriendo en `192.168.2.111:8007`
3. **Acceso SSH** configurado al servidor (sin contraseña)

## Arquitectura

```
┌─────────────────┐      HTTP/REST       ┌─────────────────────┐
│   OpenCode      │ ───────────────────▶ │  KinnyCode Memory   │
│   (Cliente MCP) │                      │  Server (FastAPI)   │
└────────┬────────┘                      └──────────┬──────────┘
         │                                          │
         │ MCP Protocol (stdio)                     │
         │                                          │
┌────────▼────────┐                      ┌──────────▼──────────┐
│   MCP Wrapper   │ ───────────────────▶ │     LanceDB         │
│   (mcp_wrapper) │      HTTP            │   (Base de datos)   │
└─────────────────┘                      └─────────────────────┘
```

## Paso 1: Verificar que el servidor este corriendo

```bash
# Conectarse al servidor
ssh hell-house

# Verificar estado del servicio
systemctl status kinnycodememory

# Verificar que responda
curl http://127.0.0.1:8007/health
```

Salida esperada:
```json
{
  "status": "healthy",
  "version": "0.5.0",
  "uptime_seconds": 258.38,
  "uptime_human": "4m 18s"
}
```

---

## OPCIÓN A: Plugin TypeScript (Recomendado)

### Paso 2A: Instalar el plugin

```bash
# Navegar al directorio del plugin
cd F:\kinnyCodeMemory\plugin-kinnycode

# Instalar dependencias
npm install

# Compilar
npm run build
```

### Paso 3A: Configurar opencode.jsonc

Edita `C:\Users\anonymous\.config\opencode\opencode.jsonc`:

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "disabled_providers": [],
  "plugin": [
    ["opencode-kinnycode-memory", {
      "serverUrl": "http://192.168.2.111:8007",
      "projectId": "a67d4e5165ff6b92"
    }]
  ]
}
```

### Parámetros del plugin

| Parámetro | Descripción | Ejemplo |
|-----------|-------------|---------|
| `serverUrl` | URL del servidor remoto | `http://192.168.2.111:8007` |
| `projectId` | ID del proyecto por defecto | `a67d4e5165ff6b92` |

---

## OPCIÓN B: MCP Wrapper (Legacy)

### Paso 2B: Configurar opencode.jsonc

Edita `C:\Users\anonymous\.config\opencode\opencode.jsonc`:

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "disabled_providers": [],
  "mcpServers": {
    "kinnycode-memory": {
      "command": "python",
      "args": ["C:\\ProgramData\\KinnyCode\\memory\\mcp_wrapper.py"],
      "env": {
        "KINNYCODE_SERVER_URL": "http://192.168.2.111:8007",
        "KINNYCODE_PROJECT_ID": "a67d4e5165ff6b92"
      }
    }
  }
}
```

### Parámetros del MCP Wrapper

| Parámetro | Descripción | Ejemplo |
|-----------|-------------|---------|
| `command` | Ejecutable Python | `python` o ruta completa |
| `args` | Argumentos del comando | Ruta al mcp_wrapper.py |
| `env.KINNYCODE_SERVER_URL` | URL del servidor remoto | `http://192.168.2.111:8007` |
| `env.KINNYCODE_PROJECT_ID` | ID del proyecto por defecto | `a67d4e5165ff6b92` |

## Paso 3: Configurar variables de entorno (Opcional)

Si prefieres no hardcodear la URL en el archivo de configuración, puedes usar variables de entorno:

```powershell
# Establecer variables de entorno
$env:KINNYCODE_SERVER_URL = "http://192.168.2.111:8007"
$env:KINNYCODE_PROJECT_ID = "a67d4e5165ff6b92"
```

O agregarlas a tu perfil de PowerShell:

```powershell
# Editar PowerShell profile
notepad $PROFILE

# Agregar las siguientes lineas:
$env:KINNYCODE_SERVER_URL = "http://192.168.2.111:8007"
$env:KINNYCODE_PROJECT_ID = "a67d4e5165ff6b92"
```

## Paso 4: Herramientas MCP Disponibles

Una vez configurado, tendrás acceso a las siguientes herramientas:

### Indexación de Código

| Herramienta | Descripción |
|-------------|-------------|
| `indexar_archivo` | Indexa un archivo de código fuente |
| `indexar_proyecto` | Indexa múltiples archivos en lote |
| `indexar_archivos_por_ruta` | Indexa archivos por rutas de disco |

### Búsqueda

| Herramienta | Descripción |
|-------------|-------------|
| `buscar_codigo` | Búsqueda semántica en código |
| `recuperar_contexto` | RAG completo (todas las capas) |

### Documentos

| Herramienta | Descripción |
|-------------|-------------|
| `indexar_documento` | Indexa PDF/MD/TXT |
| `buscar_documentos` | Busca en documentos |
| `listar_documentos` | Lista documentos indexados |

### Conversaciones y Decisiones

| Herramienta | Descripción |
|-------------|-------------|
| `guardar_conversacion` | Guarda historial de conversación |
| `cargar_conversacion` | Recupera historial |
| `guardar_decision` | Guarda una decisión técnica |

### Proyecto

| Herramienta | Descripción |
|-------------|-------------|
| `info_proyecto` | Muestra estadísticas del proyecto |

## Paso 5: Ejemplos de Uso

### Buscar en el codebase

```python
# El agente puede usar la herramienta buscar_codigo
buscar_codigo(
    prompt="¿Cómo funciona el sistema de embeddings?",
    n_results=5
)
```

### Indexar un archivo nuevo

```python
indexar_archivo(
    file_path="src/nuevo_modulo.py",
    content="def mi_funcion(): ...",
    language="python"
)
```

### Recuperar contexto completo

```python
recuperar_contexto(
    prompt="¿Qué decisiones de arquitectura tomamos para el sistema de memoria?",
    layers=["code", "documents", "conversations", "decisions"]
)
```

## Paso 6: Verificar la Conexión

### Desde OpenCode

1. Abre OpenCode
2. Escribe: `/mcp` para ver los servidores MCP disponibles
3. Deberías ver `kinnycode-memory` en la lista

### Usando la CLI de KinnyCode

```bash
# Verificar info del proyecto
python cli.py info --project-id a67d4e5165ff6b92

# Buscar en el codebase
python cli.py search "memory system" --project-id a67d4e5165ff6b92
```

## Project IDs Disponibles

| Project ID | Descripción | Registros |
|------------|-------------|-----------|
| `a67d4e5165ff6b92` | Proyecto principal (KinnyCode Memory) | 205,139 registros |

## Solución de Problemas

### Error: "Cannot connect to server"

```bash
# Verificar que el servidor este corriendo
ssh hell-house "systemctl status kinnycodememory"

# Verificar conectividad de red
ping 192.168.2.111

# Verificar que el puerto este abierto
Test-NetConnection -ComputerName 192.168.2.111 -Port 8007
```

### Error: "Project ID not found"

```bash
# Listar proyectos disponibles
curl -X POST http://192.168.2.111:8007/project-info \
  -H "Content-Type: application/json" \
  -d '{"project_id": "6b6a8b869aea48ad"}'
```

### Error: "MCP server not responding"

1. Verifica que Python este instalado
2. Verifica que las dependencias estén instaladas:
   ```bash
   pip install httpx mcp
   ```
3. Verifica la ruta al mcp_wrapper.py

### Logs del servidor

```bash
# Ver logs en tiempo real
ssh hell-house "journalctl -u kinnycodememory -f"

# Ver logs recientes
ssh hell-house "journalctl -u kinnycodememory --no-pager -n 50"
```

## Configuración Avanzada

### Múltiples proyectos

Puedes configurar múltiples instancias del MCP server para diferentes proyectos:

```jsonc
{
  "mcpServers": {
    "kinnycode-main": {
      "command": "python",
      "args": ["C:\\ProgramData\\KinnyCode\\memory\\mcp_wrapper.py"],
      "env": {
        "KINNYCODE_SERVER_URL": "http://192.168.2.111:8007",
        "KINNYCODE_PROJECT_ID": "6b6a8b869aea48ad"
      }
    },
    "kinnycode-docs": {
      "command": "python",
      "args": ["C:\\ProgramData\\KinnyCode\\memory\\mcp_wrapper.py"],
      "env": {
        "KINNYCODE_SERVER_URL": "http://192.168.2.111:8007",
        "KINNYCODE_PROJECT_ID": "ccf515ff0c3fe492"
      }
    }
  }
}
```

### Proxy inverso con Nginx (Opcional)

Si quieres usar un dominio o HTTPS:

```nginx
server {
    listen 80;
    server_name memory.tudominio.com;

    location / {
        proxy_pass http://192.168.2.111:8007;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## Comandos Útiles

```bash
# Reiniciar servicio
ssh hell-house "sudo systemctl restart kinnycodememory"

# Verificar espacio en disco
ssh hell-house "df -h /home/anonymous"

# Verificar tamaño de la base de datos
ssh hell-house "du -sh /opt/KinnyCodeMemory/lancedb_memory_db/"

# Backup de la base de datos
ssh hell-house "sudo cp -r /opt/KinnyCodeMemory/lancedb_memory_db /opt/KinnyCodeMemory/backup_$(date +%Y%m%d)"
```

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
