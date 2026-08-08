---
name: batch-workflow
description: Reglas obligatorias de trabajo por lotes para refactorizaciones grandes. Usa cuando se refactorean componentes, migras a TanStack Query, reescribes hooks, o cualquier tarea que involucre modificar más de 3 archivos. Palabras clave: refactor, migración, TSQ, TanStack Query, batch, lote, lotes, chunk, chunking, context window, ventana de contexto.
---

# Batch Workflow — Reglas de Trabajo por Lotes

## Propósito

Este skill define las reglas **obligatorias** para evitar desbordar la ventana de contexto durante refactorizaciones grandes. Se aplica automáticamente a cualquier tarea de refactorización, migración de librerías, o reestructuración de código que involucre más de 3 archivos.

## Reglas Inquebrantables

### 1. Límite de Líneas por Lote
- **Máximo 300 líneas de código nuevo** por lote
- Si un archivo existente tiene más de 500 líneas, **nunca lo leas completo** — usa `grep` para encontrar las líneas relevantes y lee solo los rangos necesarios con `read --offset --limit`

### 2. Lectura Selectiva de Archivos
- **Nunca leas archivos >500 líneas completos**
- Usa `grep` para localizar patrones, luego `read` con `--offset` y `--limit` para leer solo el rango necesario
- Ejemplo: `grep -n "cargarCaracterizacion" ReportesContext.jsx` → `read ReportesContext.jsx --offset 228 --limit 60`

### 3. Auto-Verificación por Lote
Cada lote debe producir:
1. **Código compilable**: El build (`pnpm build` o equivalente) debe pasar
2. **Smoke test mínimo**: Al menos un check de import/export o verificación de tipos
3. **Commit atómico**: Un commit con mensaje descriptivo (`feat: add queryKeys factory`, `refactor: migrate useCharacterization to TSQ`)

### 4. Archivos Old → Deprecación, No Borrado
- Archivos legacy se marcan con `@deprecated` JSDoc/TS comment
- Se renombran con sufijo `.deprecated.js` o `.deprecated.ts`
- Se mueven a `_deprecated/` solo en la Fase final de limpieza

### 5. Estructura de Lotes Obligatoria
Cada lote sigue este formato:

```
LOTE X.Y — [Nombre Descriptivo]
├── Objetivo: [1-2 líneas]
├── Archivos nuevos: [lista]
├── Archivos modificados: [lista]
├── Archivos leídos: [solo rangos específicos]
├── Entregable: [líneas estimadas]
└── Criterio de aceptación: [cómo verificar]
```

## Flujo de Trabajo por Lote

### Fase 0: Planificación
1. Analiza el scope total de la tarea
2. Divide en lotes ≤300 líneas cada uno
3. Presenta el plan al usuario para aprobación
4. **No comiences a escribir código hasta que el usuario apruebe**

### Fase 1: Ejecución del Lote
Para cada lote, sigue este orden:
1. **Leer** solo los archivos/rangos necesarios (usa `grep` + `read --offset`)
2. **Escribir** los nuevos archivos o modificaciones
3. **Verificar** que el build compila
4. **Commit** atómico con mensaje descriptivo
5. **Reportar** al usuario: qué se hizo, qué sigue, y si hay bloqueos

### Fase 2: Siguiente Lote
1. Confirma con el usuario que el lote anterior está OK
2. Carga el contexto del siguiente lote
3. Repite Fase 1

## Reglas de Arquitectura del Proyecto CNM

### Stack Tecnológico
- **Backend**: FastAPI (Python 3.12+)
- **Frontend**: React + TypeScript + Vite
- **Base de Datos**: PostgreSQL (schema `sgcnmdb`)
- **Estado**: Zustand + TanStack Query v5
- **UI**: MUI + Tailwind CSS
- **Caché**: Dexie/IndexedDB (en proceso de migración a TSQ)
- **Paquetes**: PNPM (frontend), Poetry/pip (backend)

### Estructura de Directorios
```
cnm-dev/
├── backend/          # API FastAPI
├── frontend/         # React SPA
│   ├── src/
│   │   ├── query/    # TSQ: queryKeys, queryOptions, client
│   │   ├── hooks/    # Custom hooks
│   │   ├── pages/    # Componentes de página
│   │   ├── services/ # Servicios de API
│   │   └── context/  # React contexts
│   └── docs/         # Documentación técnica
├── docs/             # Docs en LaTeX
└── scripts/          # Utilidades de despliegue
```

### Reglas de Nomenclatura
- **Query Keys**: `queryKeys.{dominio}.{recurso}` (ej: `queryKeys.monthly.list`, `queryKeys.weekly.byId(id)`)
- **Query Options**: `get{Recurso}QueryOptions()` (ej: `getMonthlyReportQueryOptions`)
- **Hooks**: `use{Recurso}()` (ej: `useMonthlyReport`, `useCharacterization`)
- **Componentes**: PascalCase (ej: `FilterPanel`, `ReportGrid`)
- **Archivos**: camelCase para JS/TS, PascalCase para componentes React

### Reglas de TanStack Query
1. **Siempre usa `queryOptions()`** helper de TSQ v5 — nunca construir objects manualmente
2. **Query keys tipadas** desde `queryKeys` factory — nunca strings literals
3. **StaleTime mínimo**: 5 minutos para datos de reporte, 1 hora para configuración estática
4. **GC Time**: 30 minutos para reportes, 1 hora para configuración
5. **Persistencia**: Usa `persistQueryClient` con `removeStaleEntries: true`

### Reglas de Backend
1. **Endpoints**: Prefijo `/api/v1/` para todas las rutas
2. **Validación**: Pydantic v2 models para request/response
3. **Dependencias**: Inyección de dependencias FastAPI (`Depends()`)
4. **Migraciones**: Alembic para cambios de schema
5. **Logging**: Structured logging con `structlog`

## Patrones Comunes

### Patrón: Migrar Hook a TanStack Query
```typescript
// ANTES (custom caching)
function useOldHook() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  // ... 50 líneas de lógica manual
}

// DESPUÉS (TSQ)
function useNewHook(params) {
  const options = getRecursoQueryOptions(params);
  return useQuery(options);
}
```

### Patrón: Query Keys Factory
```typescript
export const queryKeys = {
  all: ['query'] as const,
  monthly: {
    all: [...queryKeys.all, 'monthly'] as const,
    list: (...params) => [...queryKeys.monthly.all, ...params] as const,
    byId: (id) => [...queryKeys.monthly.all, 'detail', id] as const,
  },
  // ... más dominios
};
```

### Patrón: Query Options Factory
```typescript
export function getMonthlyReportQueryOptions(params: MonthlyParams) {
  return queryOptions({
    queryKey: queryKeys.monthly.byId(params.id),
    queryFn: () => fetchMonthlyReport(params),
    staleTime: 5 * 60 * 1000,
    gcTime: 30 * 60 * 1000,
  });
}
```

## Checkpoint de Calidad

Antes de marcar un lote como completado, verifica:
- [ ] El build compila sin errores
- [ ] No hay imports circulares nuevos
- [ ] Los tipos TypeScript son estrictos (no `any`)
- [ ] Los query keys están tipados correctamente
- [ ] Los archivos old están marcados `@deprecated`
- [ ] El commit message es descriptivo y sigue conventional commits
- [ ] No se leyeron archivos >500 líneas completos

## Comunicación con el Usuario

### Al Iniciar un Lote
```
📦 LOTE X.Y — [Nombre]
🎯 Objetivo: [qué se va a hacer]
📁 Archivos: [lista de archivos nuevos/modificados]
📏 Estimado: [líneas de código]
```

### Al Completar un Lote
```
✅ LOTE X.Y — COMPLETADO
📝 Cambios: [resumen de lo hecho]
🧪 Verificación: [qué se verificó]
📦 Commit: [hash y mensaje]
➡️ Siguiente: [qué lote sigue]
```

### Si hay un Bloqueo
```
🚫 BLOQUEO en LOTE X.Y
❓ Problema: [descripción]
💡 Opciones: [alternativas]
⏳ Esperando: [decisión del usuario]
```
