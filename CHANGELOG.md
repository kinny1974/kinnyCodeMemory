# Changelog

Todos los cambios notables en KinnyCode Memory System.

El formato está basado en [Keep a Changelog](https://keepachangelog.com/),
y este proyecto adherce a [Semantic Versioning](https://semver.org/).

## [1.0.0] - 2026-08-08

### Added
- **Memory Server**: Servidor FastAPI con API REST completa
- **MCP Wrapper**: Soporte para Model Context Protocol
- **CLI**: Interfaz de línea de comandos
- **Web UI**: Interfaz web para gestión y consultas
- **Installer**: Instalador GUI cross-platform
- **System Tray**: Bandeja del sistema para Windows/Linux
- **Multi-formato**: Soporte para PDF, EPUB, DOCX, ODF, XLS, CSV, Markdown, TXT
- **Multi-proyecto**: Aislamiento completo entre proyectos
- **Embeddings**: Modelo all-MiniLM-L6-v2 local
- **M_score**: Algoritmo de relevancia avanzado
- **Indexation Service**: Servicio consolidado de indexación
- **Embedding Cache**: Cache TTL para embeddings
- **Monitoring**: Endpoints /health, /metrics, /ready
- **Validation**: Validación estricta de project_id

### Changed
- Refactorización de código duplicado
- Mejora en rendimiento de indexación
- Optimización de uso de memoria

### Fixed
- Corrección en manejo de caracteres especiales
- Fix en indexación de archivos grandes
- Corrección en búsqueda semántica

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
