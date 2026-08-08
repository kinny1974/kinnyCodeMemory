# Changelog

Todos los cambios notables en KinnyCode Memory System.

El formato está basado en [Keep a Changelog](https://keepachangelog.com/),
y este proyecto adherce a [Semantic Versioning](https://semver.org/).

## [1.0.0] - 2026-08-08

### Added
- **Memory Server**: Servidor FastAPI con API REST completa (38 endpoints)
- **MCP Wrapper**: Soporte para Model Context Protocol (15 herramientas)
- **CLI**: Interfaz de línea de comandos completa
- **Web UI**: Interfaz web para gestión y consultas
- **Installer**: Instalador GUI + CLI cross-platform
- **System Tray**: Bandeja del sistema para Windows/Linux
- **Multi-formato**: Soporte para PDF, EPUB, DOCX, ODF, XLS, CSV, Markdown, TXT
- **Multi-proyecto**: Aislamiento completo entre proyectos
- **Embeddings**: Modelo all-MiniLM-L6-v2 local (sin dependencias externas)
- **M_score**: Algoritmo de relevancia con decaimiento Ebbinghaus
- **Indexation Service**: Servicio consolidado de indexación
- **Embedding Cache**: Cache TTL para embeddings
- **Monitoring**: Endpoints /health, /metrics, /ready
- **Validation**: Validación estricta de project_id
- **Tests**: 89 tests (unit, integración, benchmarks)
- **Systemd Services**: Servicios para Memory Server y Web UI

### Changed
- Refactorización de código duplicado
- Mejora en rendimiento de indexación
- Optimización de uso de memoria
- Instalador incluye opción de Web UI como servicio

### Fixed
- Corrección en manejo de caracteres especiales
- Fix en indexación de archivos grandes
- Corrección en búsqueda semántica
- Fix en KINNYCODE_HOST (ahora se lee del .env)
- Fix en installer para headless Linux

### Known Limitations (v1.0.1)
- **Sin autenticación**: API accesible sin credenciales (aceptable para uso privado)
- **CORS abierto**: `allow_origins=["*"]` (restringir en producción)
- **Sin rate limiting**: Vulnerable a abuso (no crítico para uso interno)
- **Cobertura ~25%**: Tests en módulos core, pendiente expandir

### Security Notes
- Para uso **interno/privado**: v1.0.0 es seguro
- Para exposición **pública**: Requiere autenticación y CORS restrictivo

## [0.9.0] - 2026-08-01

### Added
- Soporte inicial para documentos
- Búsqueda semántica básica
- Sistema de tareas (L5)

## [0.8.0] - 2026-07-15

### Added
- Sistema de conversaciones (L2)
- Storage de decisiones
- Gestión de proyectos

## [0.7.0] - 2026-07-01

### Added
- Indexación de código fuente
- Detección de cambios
- File watcher

## [0.6.0] - 2026-06-15

### Added
- LanceDB como base de datos vectorial
- Sistema de embeddings
- Chunking de texto

## [0.5.0] - 2026-06-01

### Added
- Arquitectura inicial
- Prototipo del servidor
- Primera versión del memory manager

## [0.1.0] - 2026-05-01

### Added
- Inicio del proyecto
- Configuración inicial
- Primera estructura de directorios
