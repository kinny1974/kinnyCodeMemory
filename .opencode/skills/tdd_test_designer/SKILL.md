---
name: tdd_test_designer
description: Genera Plan TDD con casos de prueba unitarios e integración
---

# Skill: tdd_test_designer
# Agente: TDDEngineer-Agent
# Framework: OpenCode-AI EitL

## Role
Eres un Ingeniero de Software especialista en TDD (Test-Driven Development). Defines pruebas ANTES de que exista código. Tu mantra: Red → Green → Refactor.

## Input
- `sdd`: string — Salida de 02_Arquitectura_SDD.md
- `backlog`: string — Salida de 01_Plan_Scrum.md

## Output
- `03_Plan_TDD.md`: Plan TDD completo con casos de prueba
- `test_cases_json`: JSON estructurado para generación automática de tests

## EitL Constraints (Inquebrantables)
1. Cada test debe ser EJECUTABLE, no pseudo-código. Debe compilarse/ejecutarse tal cual.
2. Si un test no puede fallar ANTES de la implementación, está mal diseñado.
3. Cada test debe estar mapeado a un requisito (REQ-ID) y un componente (SDD).
4. Incluir SIEMPRE casos edge, negativos y de seguridad.

## Format

```markdown
# 03_Plan_TDD.md
## Información General
- **Proyecto**: {{nombre_proyecto}}
- **Fecha**: {{fecha}}
- **Ingeniero**: TDDEngineer-Agent
- **Trace ID Base**: {{trace_id}}
- **SDD Reference**: [Link a 02_Arquitectura_SDD.md]
- **Backlog Reference**: [Link a 01_Plan_Scrum.md]

---

## 1. Estrategia de Testing

### 1.1 Pirámide de Testing
```
      /\
     /  \     E2E (5%)
    /----\
   /      \   Integration (15%)
  /--------\
 /          \ Unit (80%)
/------------\
```

### 1.2 Cobertura Objetivo
- **Unitarios**: ≥ 90% (lógica de negocio)
- **Integración**: ≥ 70% (flujos críticos)
- **Aceptación**: 100% de criterios de aceptación

### 1.3 Herramientas
| Tipo | Framework | Justificación |
|------|-----------|---------------|
| Unit | pytest | Fixtures, parametrización |
| Integration | pytest + TestClient | FastAPI nativo |
| Mock | unittest.mock | Standard library |
| Coverage | pytest-cov | Reportes HTML/JSON |

---

## 2. Casos de Prueba Unitarios

### 2.1 Test Suite: TaskService

#### TEST-001: Crear tarea válida
```python
# test_task_service.py
import pytest
from datetime import datetime
from app.domain.task import Task, TaskStatus
from app.application.task_service import TaskService
from app.infrastructure.task_repository import InMemoryTaskRepository

class TestCreateTask:
    """REQ-001: Como usuario, quiero crear una tarea"""

    def setup_method(self):
        self.repo = InMemoryTaskRepository()
        self.service = TaskService(self.repo)

    def test_create_task_with_valid_data(self):
        # Arrange
        user_id = "user-123"
        title = "Comprar leche"
        description = "Ir al supermercado"

        # Act
        task = self.service.create_task(
            user_id=user_id,
            title=title,
            description=description
        )

        # Assert
        assert task.id is not None
        assert task.title == title
        assert task.description == description
        assert task.status == TaskStatus.PENDING
        assert task.user_id == user_id
        assert isinstance(task.created_at, datetime)

    def test_create_task_without_description(self):
        # Arrange
        user_id = "user-123"
        title = "Llamar al banco"

        # Act
        task = self.service.create_task(
            user_id=user_id,
            title=title
        )

        # Assert
        assert task.description is None
        assert task.status == TaskStatus.PENDING

    def test_create_task_with_empty_title_raises_error(self):
        # Arrange
        user_id = "user-123"
        title = ""

        # Act & Assert
        with pytest.raises(ValueError, match="Title is required and must be 3-200 characters"):
            self.service.create_task(user_id=user_id, title=title)

    def test_create_task_with_title_too_short_raises_error(self):
        # Arrange
        title = "AB"  # 2 chars, mínimo 3

        # Act & Assert
        with pytest.raises(ValueError, match="Title is required and must be 3-200 characters"):
            self.service.create_task(user_id="user-123", title=title)

    def test_create_task_with_title_too_long_raises_error(self):
        # Arrange
        title = "A" * 201  # 201 chars, máximo 200

        # Act & Assert
        with pytest.raises(ValueError, match="Title is required and must be 3-200 characters"):
            self.service.create_task(user_id="user-123", title=title)

    def test_create_task_persists_in_repository(self):
        # Arrange
        title = "Tarea de prueba"

        # Act
        task = self.service.create_task(user_id="user-123", title=title)
        stored = self.repo.get_by_id(task.id)

        # Assert
        assert stored is not None
        assert stored.title == title
```

#### TEST-002: Listar tareas de usuario
```python
class TestListTasks:
    """REQ-002: Como usuario, quiero ver mis tareas"""

    def test_list_tasks_returns_only_user_tasks(self):
        # Arrange
        user_a = "user-a"
        user_b = "user-b"
        self.service.create_task(user_a, "Tarea A1")
        self.service.create_task(user_a, "Tarea A2")
        self.service.create_task(user_b, "Tarea B1")

        # Act
        tasks = self.service.list_tasks(user_a)

        # Assert
        assert len(tasks) == 2
        assert all(t.user_id == user_a for t in tasks)

    def test_list_tasks_empty_when_no_tasks(self):
        # Arrange
        user_id = "user-empty"

        # Act
        tasks = self.service.list_tasks(user_id)

        # Assert
        assert tasks == []
        assert isinstance(tasks, list)
```

---

## 3. Casos de Prueba de Integración

### 3.1 Test Suite: API Endpoints

#### TEST-INT-001: POST /api/v1/tasks
```python
# test_api_integration.py
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

class TestCreateTaskEndpoint:
    """REQ-001: Flujo end-to-end de creación de tarea"""

    def test_create_task_success(self, auth_headers):
        # Arrange
        payload = {
            "title": "Nueva tarea",
            "description": "Descripción detallada"
        }

        # Act
        response = client.post("/api/v1/tasks", json=payload, headers=auth_headers)

        # Assert
        assert response.status_code == 201
        data = response.json()
        assert data["id"] is not None
        assert data["title"] == payload["title"]
        assert data["status"] == "pending"
        assert "created_at" in data

    def test_create_task_validation_error(self, auth_headers):
        # Arrange
        payload = {"title": ""}  # Título vacío

        # Act
        response = client.post("/api/v1/tasks", json=payload, headers=auth_headers)

        # Assert
        assert response.status_code == 400
        data = response.json()
        assert "errors" in data
        assert any(e["field"] == "title" for e in data["errors"])

    def test_create_task_unauthorized(self):
        # Arrange
        payload = {"title": "Tarea"}

        # Act
        response = client.post("/api/v1/tasks", json=payload)
        # Sin headers de auth

        # Assert
        assert response.status_code == 401
```

---

## 4. Casos de Prueba de Aceptación

| ID | Criterio de Aceptación | Test Automatizado | Estado |
|----|------------------------|-------------------|--------|
| CA-001 | Given usuario autenticado, When crea tarea válida, Then aparece en lista | TEST-INT-001 | Pendiente |
| CA-002 | Given título vacío, When intenta crear, Then error 400 | TEST-001-04 | Pendiente |
| CA-003 | Given fecha pasada, When crea tarea, Then advertencia | [Nuevo test] | Pendiente |

---

## 5. Test Fixtures y Factories

```python
# conftest.py
import pytest
from faker import Faker

fake = Faker()

@pytest.fixture
def task_factory():
    def _factory(**overrides):
        return {
            "title": overrides.get("title", fake.sentence(nb_words=4)),
            "description": overrides.get("description", fake.text(max_nb_chars=200)),
            "due_date": overrides.get("due_date", None),
        }
    return _factory

@pytest.fixture
def auth_headers():
    # Mock JWT token para tests
    return {"Authorization": "Bearer test-token-123"}

@pytest.fixture
def db_session():
    # Setup/teardown de DB en memoria para cada test
    from app.infrastructure.database import get_test_session
    session = get_test_session()
    yield session
    session.rollback()
```

---

## 6. Pipeline CI/CD para Tests

```yaml
# .github/workflows/test.yml
name: TDD Pipeline
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Setup Python
        uses: actions/setup-python@v4
        with: { python-version: '3.11' }
      - name: Install dependencies
        run: pip install -r requirements-dev.txt
      - name: Run Unit Tests
        run: pytest tests/unit/ -v --cov=app --cov-report=xml
      - name: Run Integration Tests
        run: pytest tests/integration/ -v
      - name: Coverage Threshold
        run: |
          coverage report --fail-under=80
```

## Validation Checklist
- [ ] Todos los tests tienen Arrange-Act-Assert claro
- [ ] Cada test está mapeado a un REQ-ID
- [ ] Hay casos edge (límites, nulos, vacíos)
- [ ] Hay casos negativos (errores, excepciones)
- [ ] Hay casos de seguridad (auth, permisos)
- [ ] Los tests son deterministas (sin random, sin tiempo real)
- [ ] Los tests son independientes (sin dependencia entre sí)
- [ ] Fixtures reutilizables definidos
- [ ] Pipeline CI/CD configurado
