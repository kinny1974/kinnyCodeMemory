# Contribuir a KinnyCode Memory

¡Gracias por tu interés en contribuir! Aquí tienes las guías para empezar.

## 🚀 Guía Rápida

1. **Fork** el repositorio
2. **Clone** tu fork
3. **Crear** una rama para tu feature
4. **Hacer** tus cambios
5. **Push** a tu fork
6. **Crear** un Pull Request

## 📋 Pre-requisitos

- Python 3.10+
- pip
- git

## 🔧 Setup de Desarrollo

```bash
# Clonar tu fork
git clone https://github.com/kinny1974/kinnycodememory.git
cd kinnycodememory

# Crear entorno virtual
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows

# Instalar dependencias
pip install -r requirements.txt

# Instalar dependencias de desarrollo
pip install pytest pytest-cov black flake8 mypy
```

## 📝 Convenciones de Código

### Python
- **Formatter**: Black
- **Linter**: Flake8
- **Type Hints**: MyPy
- **Line Length**: 88 caracteres (Black default)

```bash
# Formatear código
black .

# Verificar estilo
flake8 .

# Verificar tipos
mypy memory/
```

### Commits
- Usar **Conventional Commits**
- Ejemplos:
  - `feat:添加 EPUB 支持`
  - `fix:修复索引问题`
  - `docs:更新 README`
  - `test:添加单元测试`

### Ramas
- `main` - Código estable
- `develop` - Desarrollo activo
- `feature/*` - Nuevas features
- `fix/*` - Correcciones
- `docs/*` - Documentación

## 🧪 Testing

```bash
# Ejecutar todos los tests
pytest tests/

# Con cobertura
pytest tests/ --cov=memory --cov-report=html

# Test específico
pytest tests/test_memory_manager.py -v
```

## 📚 Estructura de Directorios

```
kinnycodememory/
├── memory/              # Código principal
├── web/                 # Web UI
├── tests/               # Tests
├── docs/                # Documentación
└── assets/              # Recursos estáticos
```

## 🐛 Reportar Bugs

1. **Buscar** si ya existe un issue
2. **Crear** un nuevo issue con:
   - Título descriptivo
   - Pasos para reproducir
   - Comportamiento esperado vs actual
   - Versión de Python y SO
   - Logs si es posible

## 💡 Sugerir Features

1. **Crear** un issue con label "enhancement"
2. **Describir**:
   - Problema que resuelve
   - Solución propuesta
   - Alternativas consideradas

## 📖 Documentación

- **README**: Uso general
- **API Docs**: Generadas automáticamente por FastAPI
- **Docstrings**: Google style

```python
def mi_funcion(param1: str, param2: int) -> bool:
    """Breve descripción.

    Args:
        param1: Descripción del parámetro 1
        param2: Descripción del parámetro 2

    Returns:
        Descripción del valor de retorno

    Raises:
        ValueError: Si param1 está vacío
    """
    pass
```

## 🎯 Labels de Issues

- `good first issue` - Bueno para principiantes
- `help wanted` - Necesita ayuda
- `bug` - Error reportado
- `enhancement` - Nueva feature
- `documentation` - Documentación
- `question` - Pregunta

## ✅ Checklist del Pull Request

- [ ] Código sigue las convenciones
- [ ] Tests agregados/actualizados
- [ ] Documentación actualizada
- [ ] No rompe la API existente
- [ ] Commit messages claros
- [ ] Rama limpia y actualizada

## 📞 Contacto

- **Issues**: Para preguntas y bugs
- **Discussions**: Para discusiones generales
- **Email**: Para asuntos privados

¡Gracias por contribuir! 🎉
