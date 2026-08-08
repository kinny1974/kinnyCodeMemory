---
name: portability-export
description: Exporta toda la memoria del proyecto (código, decisiones, tareas, configuraciones) a formato portable SIGMA-Team usando export_memory.ps1
---

# Skill: portability-export
# Framework: OpenCode-AI EitL — Portabilidad de Memoria

## Role
Eres un especialista en exportación de memoria. Tu trabajo es **ejecutar el script `export_memory.ps1`** para generar un paquete portable con todo el estado del proyecto: índice de código fuente con SHA-256, decisiones de arquitectura, artefactos del pipeline EitL, migraciones SQL, y configuraciones de sesión.

## Script de Exportación
**Ruta**: `memory-portability/export_memory.ps1`
**Lenguaje**: PowerShell 5.1+
**Ubicación**: Raíz del proyecto (`C:\cnm-dev`)

## Parámetros del Script

| Parámetro | Tipo | Obligatorio | Default | Descripción |
|-----------|------|-------------|---------|-------------|
| `-TeamName` | string | No | `"SIGMA-Team"` | Nombre del equipo que genera el export |
| `-OutputPath` | string | No | `""` (raíz del proyecto) | Ruta personalizada donde crear el directorio de exportación |

## Comportamiento del Script
1. Escanea `migrations/*.sql` → genera `data/tasks/tasks_manifest.json` (51+ migraciones)
2. Busca artefactos: `01_Plan_Scrum.md`, `02_Arquitectura_SDD.md` → genera `data/tasks/tasks_manifest.json`
3. Copia documentos de decisión → `data/decisions/` (archivos .md completos)
4. Escanea `*.py, *.js, *.jsx, *.ts, *.tsx, *.sql` (excluyendo node_modules, .git, etc.) → genera `data/code_index/code_index.json` con 27,000+ referencias (path, sha256, size, modified)
5. Copia `.opencode/` → `data/conversations/` (agentes, skills, artefactos, validaciones)
6. Genera `metadata/MANIFEST.txt` con checksums SHA-256
7. Genera `metadata/checksums.json` con todos los hashes
8. Genera `README.md` portable

## Output
```
memory-export-<YYYYMMDD_HHMMSS>/
├── README.md
├── data/
│   ├── tasks/tasks_manifest.json
│   ├── decisions/
│   │   ├── 01_Plan_Scrum.md
│   │   ├── 02_Arquitectura_SDD.md
│   │   └── validation_report_responsive.md
│   ├── code_index/code_index.json
│   └── conversations/ (agentes, skills, artefactos, etc.)
└── metadata/
    ├── MANIFEST.txt
    └── checksums.json
```

## Cómo ejecutar (vía bash tool)

### Export básico (raíz del proyecto)
```powershell
& ".\memory-portability\export_memory.ps1"
```

### Export con nombre de equipo personalizado
```powershell
& ".\memory-portability\export_memory.ps1" -TeamName "MiEquipo"
```

### Export a ruta específica
```powershell
& ".\memory-portability\export_memory.ps1" -OutputPath "D:\backups\" -TeamName "SIGMA-Backup"
```

## Flujo de Exportación (para el agente)

1. **Verificar pre-requisitos**: Confirmar que `memory-portability/export_memory.ps1` existe
2. **Ejecutar script**: Llamar al script con los parámetros deseados usando la bash tool
3. **Verificar salida**: Confirmar que el directorio `memory-export-<timestamp>/` se generó
4. **Validar contenido**: Revisar que `data/code_index/code_index.json` contiene las referencias esperadas
5. **Reportar resultado**: Indicar ruta del export, cantidad de archivos indexados y checksums

## Reglas
1. **Ejecutar siempre desde la raíz del proyecto** (`C:\cnm-dev`). Usar `workdir` si es necesario.
2. **No modificar el script**: El skill solo ejecuta el script, no lo edita.
3. **Verificar salida**: Después de ejecutar, confirmar que el directorio de exportación se creó correctamente.
4. **Reportar estadísticas**: Indicar cuántos archivos de código, decisiones y tareas se exportaron.
5. **Encoding UTF-8**: Todos los archivos generados por el script usan UTF-8.

## Integración con otros skills
- El skill `portability-import` consume el formato generado por este skill.
- Compatible con el script `import_memory.ps1` para restauración en otro equipo/instancia.
- Complementario al skill `memory-exporter` (que usa MCP tools del servidor de memoria).
