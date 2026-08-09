# Guia Rapida - Configuracion MCP

## Configuracion Minima (3 pasos)

### 1. Editar opencode.jsonc

Abre `C:\Users\anonymous\.config\opencode\opencode.jsonc` y agrega:

```json
{
  "plugin": [
    ["opencode-kinnycode-memory", {
      "serverUrl": "http://192.168.2.111:8007",
      "projectId": "a67d4e5165ff6b92"
    }]
  ]
}
```

### 2. Reiniciar OpenCode

Cierra y vuelve a abrir OpenCode.

### 3. Verificar

Escribe `/mcp` en OpenCode. Deberías ver `kinnycode-memory` en la lista.

---

## Project IDs para usar

| Proyecto | ID |
|----------|-----|
| KinnyCode Memory | `a67d4e5165ff6b92` |

---

## Ejemplo de uso

```
/buscar_codigo "¿Cómo funciona el sistema de embeddings?"
```

---

## Mas informacion

Ver `docs/CONFIGURACION_MCP.md` para configuracion avanzada.
