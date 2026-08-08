---
name: portability-import
description: Importa un paquete de memoria portable SIGMA-Team al proyecto usando import_memory.ps1
---

# Skill: portability-import
# Framework: OpenCode-AI EitL — Portabilidad de Memoria

## Role
Eres un especialista en importación de memoria. Tu trabajo es **ejecutar el script `import_memory.ps1`** para restaurar un paquete de memoria portable (generado por `export_memory.ps1`) en el proyecto actual, incluyendo decisiones de arquitectura, migraciones referenciadas, y configuraciones de sesión.

## Script de Importación
**Ruta**: `memory-portability/import_memory.ps1`
**Lenguaje**: PowerShell 5.1+
**Ubicación**: Raíz del proyecto (`C:\cnm-dev`)

## Parámetros del Script

| Parámetro | Tipo | Obligatorio | Default | Descripción |
|-----------|------|-------------|---------|-------------|
| `-ImportPath` | string | **Sí** | — | Ruta al directorio de exportación (ej: `.\memory-export-20260701_211840\`) o a un archivo ZIP |
| `-ExtractFirst` | switch | No | `$false` | Si se proporciona un ZIP, lo extrae automáticamente antes de importar |
| `-DryRun` | switch | No | `$false` | Modo simulación: verifica integridad pero no copia archivos |

## Validación Pre-import (ejecutada por el script)
1. Busca `metadata/MANIFEST.txt` en el directorio de importación
2. Si existe `metadata/checksums.json`, verifica **todos los SHA-256** contra los archivos
3. Si algún checksum falla → **ERROR** y aborta la importación
4. Modo `-DryRun`: verifica todo pero no escribe nada

## Lo que importa el script

| Dato | Origen | Destino | Descripción |
|------|--------|---------|-------------|
| Decisiones | `data/decisions/*.md` | Raíz del proyecto | Copia literal de los documentos (01_Plan_Scrum.md, etc.) |
| Tareas (migraciones) | `data/tasks/tasks_manifest.json` | `migrations/` (referencia) | Solo referencia; las migraciones ya existen en el repo |
| Conversaciones | `data/conversations/` | `.opencode/` | Restaura agentes, skills, artefactos, validaciones |
| Código | `data/code_index/code_index.json` | Solo referencia | El índice se usa como referencia, no se sobreescribe código |

## Cómo ejecutar (vía bash tool)

### Importar desde directorio
```powershell
& ".\memory-portability\import_memory.ps1" -ImportPath ".\memory-export-20260701_211840\"
```

### Importar desde ZIP (extracción automática)
```powershell
& ".\memory-portability\import_memory.ps1" -ImportPath ".\memoria.zip" -ExtractFirst
```

### Modo simulación (solo verificar)
```powershell
& ".\memory-portability\import_memory.ps1" -ImportPath ".\memory-export-20260701_211840\" -DryRun
```

## Flujo de Importación (para el agente)

1. **Solicitar confirmación**: El agente DEBE preguntar al usuario antes de importar (puede sobrescribir archivos existentes)
2. **Verificar integridad**: El script verifica checksums automáticamente. Si hay errores, reportarlos.
3. **Ejecutar import**: Llamar al script con los parámetros adecuados usando la bash tool
4. **Verificar resultado**: Confirmar que los archivos se copiaron correctamente
5. **Reportar**: Indicar cuántas decisiones, migraciones y configuraciones se importaron

## Reglas
1. **Siempre pedir confirmación al usuario** antes de ejecutar el import (puede sobrescribir `01_Plan_Scrum.md`, `02_Arquitectura_SDD.md`, etc.)
2. **Verificar checksums**: Si el script reporta errores de checksum, detener el proceso y notificar al usuario
3. **Ejecutar desde la raíz del proyecto** (`C:\cnm-dev`). Usar `workdir` si es necesario.
4. **No modificar el script**: El skill solo ejecuta el script, no lo edita.
5. **Modo DryRun recomendado**: Para verificar antes de importar, ejecutar primero con `-DryRun`

## Integración con otros skills
- Consume el formato generado por el skill `portability-export` (y por `export_memory.ps1`)
- Complementario al skill `memory-importer` (que usa MCP tools del servidor de memoria en lugar de scripts locales)
- El skill `artifact_validator` puede usarse para validar los artefactos importados (01_Plan_Scrum.md, etc.)
