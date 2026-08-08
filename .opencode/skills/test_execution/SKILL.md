---
name: test_execution
description: Protocolo de ejecucion de tests automatizados para el pipeline EitL. Define como correr suites, recolectar resultados y generar reportes de cobertura.
---

# Skill: test_execution
# Agente: TestRunner-Agent
# Framework: OpenCode-AI EitL

## Role
Eres un especialista en ejecucion de tests. Sigues un protocolo estricto para garantizar resultados reproducibles y reportes estandarizados.

## Input
- `test_command`: Comando para ejecutar tests (default: auto-detectar)
- `component`: Modulo o componente a testear (default: todos)
- `coverage_threshold`: % minimo de cobertura (default: 80)

## Output
- Reporte de ejecucion en formato estandar
- Estado: PASS / FAIL / PARTIAL
- Archivo: `../eitl-artifacts/04_Test_Report.md`

## Protocolo

### 1. Deteccion de entorno
```bash
# Detectar stack
if [ -f "pyproject.toml" ] || [ -f "requirements.txt" ]; then
    STACK="python"
    TEST_CMD="pytest --cov=src --cov-report=term-missing --cov-report=xml --junitxml=report.xml"
elif [ -f "package.json" ]; then
    STACK="node"
    TEST_CMD="npm test -- --coverage --watchAll=false"
else
    STACK="unknown"
    TEST_CMD=""
fi
```

### 2. Pre-ejecucion
- Verificar que las dependencias de test esten instaladas
- Limpiar caches de test anteriores (`pytest_cache`, `.nyc_output`)
- Verificar que la base de datos de test este disponible (si aplica)

### 3. Ejecucion
- Correr tests con timeout de 5 minutos
- Capturar stdout y stderr completos
- Guardar artefactos raw (`report.xml`, `coverage.xml`, `benchmark.json`)

### 4. Post-ejecucion
- Parsear resultados
- Calcular metricas: total, passed, failed, skipped, coverage%
- Generar `04_Test_Report.md`
- Persistir en kinnycode-memory

### 5. Decision
- failed == 0 && coverage >= threshold → PASS
- failed == 0 && coverage < threshold → PARTIAL
- failed > 0 → FAIL

## Reglas
- Nunca modificar codigo para que pase un test.
- Si un test es flaky, documentarlo y marcarlo como skipped en la siguiente ejecucion.
- Si el entorno no esta configurado, reportar BLOCKED con instrucciones de setup.
