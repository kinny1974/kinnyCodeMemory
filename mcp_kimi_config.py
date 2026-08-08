"""
Generador de configuración MCP para Kimi Code.

Kimi Code carga servidores MCP desde:
  - Configuración de usuario: ~/.kimi/mcp.json
  - Configuración de proyecto: .kimi-code/mcp.json

Formato esperado (root key `mcpServers`):

    {
      "mcpServers": {
        "kinnycode-memory": {
          "command": "python",
          "args": ["/ruta/a/mcp_wrapper.py"],
          "env": {
            "MEMORY_SERVER_URL": "http://127.0.0.1:8006",
            "KINNYCODE_PROJECT_ID": "..."
          }
        }
      }
    }

Uso:
    from mcp_kimi_config import generate_config, write_config
    config = generate_config("/ruta/al/proyecto")
    write_config("/ruta/al/proyecto")
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any


def _get_default_server_url() -> str:
    """Lee MEMORY_SERVER_URL del entorno en tiempo de ejecución."""
    return os.environ.get("MEMORY_SERVER_URL", "http://127.0.0.1:8006")


def _get_project_id(project_path: Path) -> str:
    """Genera un project_id estable a partir de la ruta absoluta."""
    abs_path = str(project_path.resolve())
    return hashlib.sha256(abs_path.encode()).hexdigest()[:16]


def _find_mcp_wrapper() -> Path:
    """Localiza mcp_wrapper.py relativo a este script."""
    candidate = Path(__file__).resolve().parent / "mcp_wrapper.py"
    if candidate.is_file():
        return candidate
    raise FileNotFoundError(f"mcp_wrapper.py no encontrado. Buscado en: {candidate}")


def generate_config(project_path: str | Path) -> dict[str, Any]:
    """Genera la configuración MCP para Kimi Code.

    Args:
        project_path: Ruta raíz del proyecto a vincular.

    Returns:
        Diccionario con el formato `mcpServers` de Kimi Code.

    Raises:
        ValueError: Si la ruta no existe o no es un directorio.
        FileNotFoundError: Si no se encuentra mcp_wrapper.py.
    """
    project = Path(project_path).resolve()

    if not project.exists():
        raise ValueError(f"La ruta no existe: {project}")
    if not project.is_dir():
        raise ValueError(f"La ruta no es un directorio: {project}")

    wrapper_path = _find_mcp_wrapper()

    # En Windows, el shebang no funciona; usamos sys.executable explícito.
    python_exe = sys.executable

    config = {
        "mcpServers": {
            "kinnycode-memory": {
                "command": python_exe,
                "args": [str(wrapper_path)],
                "env": {
                    "MEMORY_SERVER_URL": _get_default_server_url(),
                    "KINNYCODE_PROJECT_ID": _get_project_id(project),
                },
            }
        }
    }

    return config


def write_config(
    project_path: str | Path,
    config_dir: str | Path | None = None,
) -> Path:
    """Escribe la configuración MCP en `.kimi-code/mcp.json`.

    Args:
        project_path: Ruta raíz del proyecto.
        config_dir: Directorio donde escribir el archivo. Por defecto
            `.kimi-code` dentro del proyecto.

    Returns:
        Ruta al archivo escrito.
    """
    project = Path(project_path).resolve()
    target_dir = Path(config_dir).resolve() if config_dir else project / ".kimi-code"
    target_dir.mkdir(parents=True, exist_ok=True)

    config = generate_config(project)
    config_path = target_dir / "mcp.json"
    config_path.write_text(
        json.dumps(config, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    return config_path


def main() -> None:
    """CLI para generar configuración MCP de Kimi Code."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Genera configuración MCP de Kimi Code para KinnyCode Memory"
    )
    parser.add_argument(
        "project_path",
        nargs="?",
        default=".",
        help="Ruta del proyecto (default: directorio actual)",
    )
    parser.add_argument(
        "--output",
        "-o",
        default=None,
        help="Directorio de salida (default: .kimi-code dentro del proyecto)",
    )
    parser.add_argument(
        "--print",
        "-p",
        action="store_true",
        help="Imprime la configuración en stdout sin escribir archivo",
    )

    args = parser.parse_args()

    if args.print:
        print(json.dumps(generate_config(args.project_path), indent=2, ensure_ascii=False))
    else:
        path = write_config(args.project_path, args.output)
        print(f"[+] Configuración MCP escrita en: {path}")


if __name__ == "__main__":
    main()
