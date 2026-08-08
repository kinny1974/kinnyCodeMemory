"""
KinnyCode CLI — Multi-Layer Memory System command-line tool.

Communicates with the KinnyCode memory server at the configured URL.
Manages server lifecycle, project initialization, code indexing,
semantic search, and project status display.

Usage:
    kinnycode server start       # Start the memory server
    kinnycode server stop        # Stop the memory server
    kinnycode server status      # Check if server is running
    kinnycode init [path]        # Initialize a project for memory
    kinnycode index [path]       # Index current project's codebase
    kinnycode search <query>     # Semantic search (code + docs)
    kinnycode status [path]      # Show project memory stats
    kinnycode uninstall          # Remove KinnyCode

Environment Variables:
    MEMORY_SERVER_URL: Base URL of the memory server (default http://127.0.0.1:8006)
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── Optional third-party imports ──────────────────────────────────────────
try:
    import httpx
except ImportError:
    httpx = None  # type: ignore[assignment]

# ═══════════════════════════════════════════════════════════════════════════
#  Constants
# ═══════════════════════════════════════════════════════════════════════════
SERVER_URL: str = os.environ.get("MEMORY_SERVER_URL", "http://127.0.0.1:8006")
"""Base URL of the KinnyCode memory server."""

CLI_DIR: Path = Path(__file__).resolve().parent
"""Directory where cli.py (and memory_server.py, mcp_wrapper.py) lives."""

PID_DIR: Path = Path.home() / ".kinnycode"
"""Directory for runtime files (PID file)."""

PID_FILE: Path = PID_DIR / "server.pid"
"""File storing the PID of the running memory server."""

# Common binary/text extensions for filtering
_TEXT_EXTENSIONS: set[str] = {
    ".py", ".pyi", ".pyx", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
    ".html", ".htm", ".css", ".scss", ".sass", ".less",
    ".json", ".jsonc", ".yaml", ".yml", ".toml", ".xml", ".ini", ".cfg",
    ".md", ".mdx", ".rst", ".txt", ".log", ".csv",
    ".rs", ".go", ".java", ".kt", ".kts", ".scala", ".swift",
    ".c", ".cpp", ".cc", ".cxx", ".h", ".hpp", ".hxx",
    ".rb", ".php", ".pl", ".pm", ".lua", ".r", ".R",
    ".sh", ".bash", ".zsh", ".fish", ".ps1", ".psm1", ".psd1",
    ".bat", ".cmd", ".make", ".cmake", ".dockerfile", ".dockerignore",
    ".sql", ".graphql", ".proto", ".thrift",
    ".tf", ".tfvars", ".hcl",
    ".env", ".env.example", ".gitignore", ".gitattributes",
    ".editorconfig", ".prettierrc", ".eslintrc",
    ".vue", ".svelte", ".astro",
    ".conf", ".service", ".socket", ".timer",
    ".tex", ".bib",
}
"""File extensions considered text (and thus indexable)."""

_LANGUAGE_MAP: dict[str, str] = {
    ".py": "python", ".pyi": "python", ".pyx": "python",
    ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".ts": "typescript", ".tsx": "typescript",
    ".rs": "rust",
    ".go": "go",
    ".java": "java", ".kt": "kotlin", ".kts": "kotlin",
    ".c": "c", ".cpp": "cpp", ".cc": "cpp", ".cxx": "cpp",
    ".h": "c", ".hpp": "cpp", ".hxx": "cpp",
    ".rb": "ruby", ".php": "php",
    ".swift": "swift", ".scala": "scala",
    ".sh": "bash", ".bash": "bash", ".zsh": "bash",
    ".ps1": "powershell", ".psm1": "powershell",
    ".sql": "sql",
    ".html": "html", ".htm": "html",
    ".css": "css", ".scss": "scss", ".sass": "sass", ".less": "less",
    ".md": "markdown", ".mdx": "markdown", ".rst": "rst",
    ".yaml": "yaml", ".yml": "yaml", ".toml": "toml",
    ".json": "json", ".jsonc": "json",
    ".xml": "xml",
    ".vue": "vue", ".svelte": "svelte",
    ".tf": "hcl", ".hcl": "hcl",
    ".tex": "latex",
    ".dockerfile": "dockerfile",
    ".lua": "lua",
    ".r": "r", ".R": "r",
    ".graphql": "graphql",
    ".proto": "protobuf",
}
"""Mapping from file extension to language identifier for the embedding chunker."""

# Maximum file size to index (1 MB) — skip larger files
_MAX_FILE_SIZE: int = 1_048_576

# Batch size for index-project endpoint
_BATCH_SIZE: int = 50

# ═══════════════════════════════════════════════════════════════════════════
#  Utility Functions
# ═══════════════════════════════════════════════════════════════════════════


def get_project_id(project_path: str | None = None) -> str:
    """Generate a deterministic unique project_id from the project path.

    Uses the first 16 hex characters of the SHA-256 hash of the
    resolved absolute path.

    Args:
        project_path: Filesystem path to the project. Defaults to CWD.

    Returns:
        A 16-character hexadecimal string uniquely identifying the project.
    """
    if project_path is None:
        project_path = str(Path.cwd())

    abs_path = str(Path(project_path).resolve())
    return hashlib.sha256(abs_path.encode()).hexdigest()[:16]


def _get_http_client() -> httpx.Client:
    """Return an httpx Client, raising a helpful error if httpx is not installed.

    Returns:
        A configured httpx.Client instance.

    Raises:
        SystemExit: If httpx is not installed.
    """
    if httpx is None:
        print("Error: 'httpx' is required but not installed.", file=sys.stderr)
        print("Install it with: pip install httpx", file=sys.stderr)
        sys.exit(1)
    return httpx.Client(timeout=120.0)


def check_server_running(url: str | None = None) -> bool:
    """Check whether the memory server is reachable.

    Sends a GET request to the server's OpenAPI docs endpoint.

    Args:
        url: Server base URL. Defaults to SERVER_URL.

    Returns:
        True if the server responds, False otherwise.
    """
    if url is None:
        url = SERVER_URL

    try:
        client = _get_http_client()
        resp = client.get(f"{url}/docs")
        return resp.status_code in (200, 307, 308)
    except Exception:
        return False


def detect_language(file_path: Path) -> str:
    """Detect the programming language from a file's extension.

    Args:
        file_path: Path to the source file.

    Returns:
        Language identifier string (e.g., 'python', 'javascript').
        Returns 'text' for unknown extensions or files without extensions.
    """
    suffix = file_path.suffix.lower()
    # Handle compound extensions like .test.ts → .ts
    if suffix == ".ts" and file_path.suffixes:
        # .ts wins over compound
        pass
    elif len(file_path.suffixes) > 1:
        # Check compound suffix first (e.g., .d.ts)
        compound = "".join(file_path.suffixes[-2:]).lower()
        if compound in _LANGUAGE_MAP:
            return _LANGUAGE_MAP[compound]

    return _LANGUAGE_MAP.get(suffix, "text")


def is_binary_file(file_path: Path) -> bool:
    """Determine whether a file is binary by checking for null bytes.

    Reads the first 8 KB of the file. If a null byte is found within
    the first block, the file is considered binary.

    Args:
        file_path: Path to the file to check.

    Returns:
        True if the file appears to be binary, False otherwise.
    """
    try:
        with file_path.open("rb") as fh:
            chunk = fh.read(8192)
            return b"\x00" in chunk
    except (OSError, PermissionError):
        return True


def load_ignore_patterns(project_path: Path) -> list[str]:
    """Load ignore patterns from the project's .kinnycode/ignore file.

    Also merges in a set of built-in default patterns.

    Args:
        project_path: Root directory of the project.

    Returns:
        A list of gitignore-style pattern strings.
    """
    # Built-in defaults that always apply
    defaults = [
        ".git/",
        ".kinnycode/",
        ".opencode/",
        "__pycache__/",
        "*.pyc",
        "*.pyo",
        "node_modules/",
        ".venv/",
        "venv/",
        ".virtualenvs/",
        ".idea/",
        ".vscode/",
        "dist/",
        "build/",
        ".next/",
        ".nuxt/",
        "target/",
        "*.egg-info/",
        "*.so",
        "*.dll",
        "*.exe",
        "*.bin",
        "lancedb_memory_db/",
        "*.db",
        "*.sqlite",
        "*.sqlite3",
    ]

    ignore_file = project_path / ".kinnycode" / "ignore"
    patterns: list[str] = list(defaults)

    if ignore_file.is_file():
        try:
            with ignore_file.open("r", encoding="utf-8") as fh:
                for line in fh:
                    stripped = line.strip()
                    if stripped and not stripped.startswith("#"):
                        patterns.append(stripped)
        except OSError:
            pass

    return patterns


def _gitignore_to_regex(pattern: str) -> str:
    """Convert a single gitignore glob pattern to a regular expression.

    Implements standard gitignore glob semantics:
    - ``*`` matches anything except ``/``
    - ``**`` matches zero or more directories (when followed by ``/``)
    - ``?`` matches any single character except ``/``
    - ``[abc]`` matches one character from the set
    - Trailing ``/`` makes the pattern match only directories (and their contents)

    The returned regex is designed for use with :func:`re.match` against
    a POSIX-style relative path.

    Args:
        pattern: Raw gitignore pattern (negation already stripped).

    Returns:
        A full-match regex string.
    """
    is_dir = pattern.endswith("/")
    if is_dir:
        pattern = pattern[:-1]

    anchored: bool
    if pattern.startswith("/"):
        anchored = True
        pattern = pattern[1:]
    elif "/" in pattern:
        anchored = True
    else:
        anchored = False

    # ── Convert glob tokens to regex ─────────────────────────────────
    parts: list[str] = []
    i = 0
    n = len(pattern)

    while i < n:
        c = pattern[i]
        if c == "*":
            if i + 1 < n and pattern[i + 1] == "*":
                # ** — match zero or more directories
                if i + 2 < n and pattern[i + 2] == "/":
                    parts.append(r"(?:.*/)?")
                    i += 3
                    continue
                else:
                    # ** at end or not followed by / → match anything
                    parts.append(r".*")
                    i += 2
                    continue
            else:
                # * — match anything within a single path component
                parts.append(r"[^/]*")
                i += 1
                continue
        elif c == "?":
            # ? — match any single char except /
            parts.append(r"[^/]")
            i += 1
            continue
        elif c == "[":
            # Character class — pass through (fnmatch-compatible)
            j = i + 1
            while j < n and pattern[j] != "]":
                j += 1
            if j < n:
                parts.append(pattern[i : j + 1])
                i = j + 1
                continue
            else:
                parts.append(re.escape(c))
                i += 1
                continue
        else:
            parts.append(re.escape(c))
            i += 1

    glob_re = "".join(parts)

    # ── Build anchored/unanchored regex ──────────────────────────────
    if is_dir:
        # Directory pattern: match the dir itself OR anything inside
        if anchored:
            regex = f"^{glob_re}(/.*)?$"
        else:
            regex = f"(?:^|.*/){glob_re}(/.*)?$"
    else:
        if anchored:
            regex = f"^{glob_re}$"
        else:
            regex = f"(?:^|.*/){glob_re}$"

    return regex


def _parse_ignore_patterns(patterns: list[str]) -> list[tuple[bool, str]]:
    """Parse gitignore-style patterns into (negated, pattern_regex) tuples.

    Implements standard gitignore semantics:
    - Patterns without ``/`` match at any level (e.g., ``*.pyc``)
    - Patterns with ``/`` are anchored relative to root
    - Trailing ``/`` matches directories and everything inside them
    - Leading ``!`` negates (re-includes) a previously ignored path

    Args:
        patterns: Raw pattern strings from ignore file.

    Returns:
        List of (is_negated, pattern_regex) tuples where pattern_regex
        is a compiled regex string (usable with :func:`re.match`).
    """
    parsed: list[tuple[bool, str]] = []
    for pat in patterns:
        if not pat:
            continue
        negated = False
        p = pat.strip()
        # Handle negation
        if p.startswith("!"):
            negated = True
            p = p[1:]
        try:
            regex = _gitignore_to_regex(p)
            parsed.append((negated, regex))
        except Exception:
            # Skip malformed patterns
            pass
    return parsed


def should_ignore(rel_path: str, patterns: list[tuple[bool, str]]) -> bool:
    """Determine if a relative path should be ignored based on patterns.

    Implements gitignore-style semantics: patterns are evaluated in order,
    with later matching patterns overriding earlier ones. Negated patterns
    (prefixed with !) re-include previously excluded files.

    Args:
        rel_path: File path relative to the project root (POSIX-style).
        patterns: Parsed pattern list from _parse_ignore_patterns.

    Returns:
        True if the file should be excluded from indexing.
    """
    ignored = False
    for negated, regex in patterns:
        if re.match(regex, rel_path):
            ignored = not negated
    return ignored


def _find_mcp_wrapper() -> Path:
    """Locate the mcp_wrapper.py script relative to this CLI.

    Returns:
        Absolute path to mcp_wrapper.py.

    Raises:
        FileNotFoundError: If mcp_wrapper.py cannot be found.
    """
    candidate = CLI_DIR / "mcp_wrapper.py"
    if candidate.is_file():
        return candidate
    raise FileNotFoundError(
        f"mcp_wrapper.py not found. Expected at: {candidate}"
    )


# ═══════════════════════════════════════════════════════════════════════════
#  Command: server start
# ═══════════════════════════════════════════════════════════════════════════


def cmd_server_start() -> None:
    """Start the KinnyCode memory server as a background subprocess.

    Launches ``uvicorn memory_server:app`` on 127.0.0.1:8006.
    Writes the PID to a file for later use by the stop command.
    """
    if check_server_running():
        print(f"[i] Memory server is already running at {SERVER_URL}")
        pid = _read_pid_file()
        if pid is not None:
            print(f"    PID: {pid}")
        return

    # Ensure PID directory exists
    PID_DIR.mkdir(parents=True, exist_ok=True)

    # Launch uvicorn in the CLI_DIR so it can find memory_server.py
    memory_server_path = CLI_DIR / "memory_server.py"
    if not memory_server_path.is_file():
        print(
            f"Error: memory_server.py not found at {memory_server_path}",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        # Use sys.executable to ensure we use the same Python interpreter
        # DETACHED_PROCESS prevents the ugly WinError 6 on garbage collection
        flags = subprocess.DETACHED_PROCESS if platform.system() == "Windows" else 0  # type: ignore[attr-defined]
        proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "memory_server:app",
                "--host",
                "127.0.0.1",
                "--port",
                "8006",
            ],
            cwd=str(CLI_DIR),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
            close_fds=True,
        )

        # Write PID to file and release handle (DETACHED_PROCESS prevents WinError 6)
        pid = proc.pid
        _write_pid_file(pid)
        # Release the Popen handle to avoid WinError 6 on GC
        proc.stdin = None
        proc.stdout = None
        proc.stderr = None
        proc = None  # Drop reference

        # ── Spinner animation while waiting ────────────────────────────
        spinner = ["\u25d0", "\u25d3", "\u25d1", "\u25d2"]  # \u25d0\u25d3\u25d1\u25d2
        start_time = time.time()
        timeout = 90  # seconds (model download on first run)
        i = 0
        sys.stdout.write(f"\r  {spinner[i % 4]} Starting server (PID: {pid})...")
        sys.stdout.flush()

        while (time.time() - start_time) < timeout:
            time.sleep(0.3)
            i += 1
            elapsed = int(time.time() - start_time)
            sys.stdout.write(f"\r  {spinner[i % 4]} Starting server (PID: {pid})... {elapsed}s")
            sys.stdout.flush()
            
            if check_server_running():
                sys.stdout.write("\r" + " " * 60 + "\r")  # Clear spinner line
                sys.stdout.flush()
                print(f"[+] Memory server started successfully")
                print(f"    URL: {SERVER_URL}")
                print(f"    PID: {pid}")
                return

        # Timeout
        sys.stdout.write("\r" + " " * 60 + "\r")
        sys.stdout.flush()
        print(f"[!] Server did not respond within {timeout}s.")
        print(f"    PID {pid} may still be loading the embedding model.")
        print(f"    Run 'kinnycode server status' to check.")

    except FileNotFoundError:
        print("Error: 'uvicorn' not found. Is it installed?", file=sys.stderr)
        print("Install with: pip install uvicorn", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"Error starting server: {exc}", file=sys.stderr)
        sys.exit(1)


# ═══════════════════════════════════════════════════════════════════════════
#  Command: server stop
# ═══════════════════════════════════════════════════════════════════════════


def cmd_server_stop() -> None:
    """Stop the KinnyCode memory server process.

    Attempts to read the PID from the PID file and terminate it.
    Falls back to platform-specific port-based termination if needed.
    """
    pid = _read_pid_file()

    if pid is not None:
        try:
            _kill_process(pid)
            _delete_pid_file()
            print(f"[+] Memory server stopped (PID: {pid})")
            return
        except Exception as exc:
            print(f"[!] Could not kill PID {pid}: {exc}", file=sys.stderr)

    # Fallback: try to find by port
    print("[i] PID file not found or process already dead. Trying port-based detection...")
    killed = _kill_process_on_port(8006)
    if killed:
        print(f"[+] Killed process on port 8006")
    else:
        if not check_server_running():
            print("[i] No memory server appears to be running.")
        else:
            print("[!] Server is running but could not be stopped automatically.")
            print("    Try manually: taskkill /F /IM python.exe  (Windows)")
            print("    Or:           pkill -f uvicorn              (Linux/Mac)")


# ═══════════════════════════════════════════════════════════════════════════
#  Command: server status
# ═══════════════════════════════════════════════════════════════════════════


def cmd_server_status() -> None:
    """Check and display the status of the memory server.

    Shows whether the server is running, its URL, and any available
    project stats from the /project-info endpoint.
    """
    running = check_server_running()

    if running:
        print(f"Server:  RUNNING")
        print(f"URL:     {SERVER_URL}")

        pid = _read_pid_file()
        if pid is not None:
            print(f"PID:     {pid}")

        # Try to get project stats
        _print_project_stats()
    else:
        print(f"Server:  STOPPED")
        print(f"URL:     {SERVER_URL}")
        print(f"\nStart it with: kinnycode server start")


def _print_project_stats() -> None:
    """Fetch and display project statistics from the server.

    Attempts to gather counts from all known layers. Gracefully handles
    unavailable endpoints.
    """
    try:
        client = _get_http_client()

        # Gather stats from available endpoints
        stats: dict[str, int] = {}

        # Try /list-documents (Layer 4)
        try:
            resp = client.get(f"{SERVER_URL}/list-documents", params={"project_id": project_id})
            if resp.status_code == 200:
                docs = resp.json().get("documents", [])
                stats["documents"] = len(docs)
        except Exception:
            pass

        print(f"\nProjects: (check individual projects with 'kinnycode status [path]')")
        if stats:
            print(f"Stats:    ", end="")
            parts = []
            if "documents" in stats:
                parts.append(f"{stats['documents']} docs indexed")
            print(", ".join(parts))
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════════════
#  Command: init  (KEY COMMAND — Project Initialization)
# ═══════════════════════════════════════════════════════════════════════════


def cmd_init(project_path: str | None = None) -> None:
    """Initialize a project directory for use with KinnyCode memory.

    Creates the .kinnycode/ directory with configuration files and
    the .opencode/opencode.jsonc file for MCP server integration.

    Directory structure created::

        <project>/
        ├── .kinnycode/
        │   ├── memory.json   — Project metadata (project_id, name, path)
        │   ├── rules.md      — Template for project conventions
        │   └── ignore        — Patterns for files to skip during indexing
        └── .opencode/
            └── opencode.jsonc — MCP server configuration for Opencode

    Args:
        project_path: Path to the project root. Defaults to current directory.
    """
    # Resolve the project root
    if project_path is None:
        project_path = str(Path.cwd())

    root = Path(project_path).resolve()

    if not root.exists():
        print(f"Error: Directory does not exist: {root}", file=sys.stderr)
        sys.exit(1)

    if not root.is_dir():
        print(f"Error: Path is not a directory: {root}", file=sys.stderr)
        sys.exit(1)

    project_id = get_project_id(str(root))
    project_name = root.name

    print(f"Initializing KinnyCode Memory for: {project_name}")
    print(f"  Project root: {root}")
    print(f"  Project ID:   {project_id}")
    print()

    # ── Create .kinnycode directory ────────────────────────────────────
    kinnycode_dir = root / ".kinnycode"
    kinnycode_dir.mkdir(exist_ok=True)
    print(f"  Created .kinnycode/")

    # ── Create .kinnycode/memory.json (project metadata) ───────────────
    memory_config = {
        "project_id": project_id,
        "project_name": project_name,
        "project_path": str(root),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "server_url": SERVER_URL,
    }

    memory_file = kinnycode_dir / "memory.json"
    memory_file.write_text(
        json.dumps(memory_config, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"  Created .kinnycode/memory.json")

    # ── Create .kinnycode/rules.md if not exists ───────────────────────
    rules_file = kinnycode_dir / "rules.md"
    if not rules_file.exists():
        rules_content = f"""# {project_name} — Project Rules

## Stack Tecnológico
<!-- Describe el stack de tu proyecto aquí -->

## Convenciones de Código
<!-- Describe las convenciones de tu proyecto aquí -->

## Arquitectura
<!-- Describe la arquitectura de tu proyecto aquí -->

## Testing
<!-- Describe los requerimientos de testing aquí -->
"""
        rules_file.write_text(rules_content, encoding="utf-8")
        print(f"  Created .kinnycode/rules.md (template)")
    else:
        print(f"  .kinnycode/rules.md already exists — skipping")

    # ── Create .kinnycode/ignore if not exists ─────────────────────────
    ignore_file = kinnycode_dir / "ignore"
    if not ignore_file.exists():
        ignore_content = """# Project-specific ignore patterns (gitignore-style)
# Add files/directories to exclude from indexing

# Dependencies
node_modules/
__pycache__/
.venv/
venv/
.virtualenvs/

# Build artifacts
dist/
build/
.next/
.nuxt/
target/

# IDE
.idea/
.vscode/

# Secrets
.env
*.key
*.pem
"""
        ignore_file.write_text(ignore_content, encoding="utf-8")
        print(f"  Created .kinnycode/ignore (template)")
    else:
        print(f"  .kinnycode/ignore already exists — skipping")

    # ── Create .opencode directory and opencode.jsonc ──────────────────
    opencode_dir = root / ".opencode"
    opencode_dir.mkdir(exist_ok=True)
    print(f"  Created .opencode/")

    config_file = opencode_dir / "opencode.jsonc"

    try:
        mcp_wrapper_path = _find_mcp_wrapper()
    except FileNotFoundError as exc:
        print(f"  [!] Warning: {exc}", file=sys.stderr)
        print(f"  [!] opencode.jsonc will be created but mcp_wrapper.py path may be incorrect.", file=sys.stderr)
        mcp_wrapper_path = CLI_DIR / "mcp_wrapper.py"

    new_mcp_config = {
        "$schema": "https://opencode.ai/config.json",
        "mcp": {
            "kinnycode-memory": {
                "type": "local",
                "command": ["python", str(mcp_wrapper_path)],
                "description": (
                    "KinnyCode Multi-Layer Memory — RAG semántico, "
                    "persistencia de conversaciones, indexación de documentos."
                ),
                "environment": {
                    "MEMORY_SERVER_URL": SERVER_URL,
                    "KINNYCODE_PROJECT_ID": project_id,
                },
                "enabled": True,
            }
        }
    }

    if config_file.exists():
        # Update existing opencode.jsonc — merge the kinnycode-memory entry
        try:
            _update_mcp_jsonc(config_file, new_mcp_config)
            print(f"  Updated .opencode/opencode.jsonc")
        except Exception:
            # If parsing fails, back up and overwrite
            backup = opencode_dir / "opencode.jsonc.bak"
            config_file.rename(backup)
            config_file.write_text(
                _format_jsonc(new_mcp_config),
                encoding="utf-8",
            )
            print(f"  Created .opencode/opencode.jsonc (existing file backed up to opencode.jsonc.bak)")
    else:
        config_file.write_text(
            _format_jsonc(new_mcp_config),
            encoding="utf-8",
        )
        print(f"  Created .opencode/opencode.jsonc")

    # ── Summary ────────────────────────────────────────────────────────
    print(f"\n[+] Project '{project_name}' initialized for KinnyCode Memory")
    print(f"    Project ID: {project_id}")
    print(f"    Server URL: {SERVER_URL}")
    print(f"\n    Next steps:")
    print(f"    1. Edit .kinnycode/rules.md with your project conventions")
    print(f"    2. Run: kinnycode index     (to index your codebase)")
    print(f"    3. Restart Opencode to load the MCP server")


def _format_jsonc(data: dict[str, Any], indent: int = 2) -> str:
    """Format a dictionary as JSONC (JSON with comments).

    Adds a header comment block and formats the JSON with indentation.

    Args:
        data: The configuration dictionary.
        indent: Number of spaces for indentation.

    Returns:
        JSONC-formatted string.
    """
    header = (
        "{\n"
        "  // ═══════════════════════════════════════════════════════════════════\n"
        "  //  KinnyCode — Multi-Layer Memory MCP Server Configuration\n"
        "  //  \n"
        "  //  Provides 10 MCP tools for code indexing, semantic search,\n"
        "  //  conversation persistence, architecture decisions, and\n"
        "  //  document indexing.\n"
        "  // ═══════════════════════════════════════════════════════════════════\n"
    )

    # Build the rest of the JSON manually to interleave the comment
    body_lines = json.dumps(data, indent=indent, ensure_ascii=False).split("\n")
    # Remove the opening brace (first line of json.dumps) since we have our own
    body_content = "\n".join(body_lines[1:])

    return header + body_content


def _update_mcp_jsonc(mcp_file: Path, new_config: dict[str, Any]) -> None:
    """Update an existing opencode.jsonc file with a new MCP server entry.

    Preserves existing servers and adds/updates the kinnycode-memory entry.

    Args:
        mcp_file: Path to the existing opencode.jsonc file.
        new_config: The new configuration dict (full) to merge.
    """
    raw = mcp_file.read_text(encoding="utf-8").strip()
    if not raw:
        # Empty file, just write new config
        mcp_file.write_text(_format_jsonc(new_config), encoding="utf-8")
        return

    # Strip // comments and parse JSON
    cleaned = _strip_json_comments(raw)
    try:
        existing = json.loads(cleaned)
    except json.JSONDecodeError:
        # Can't parse, fall back to overwrite
        raise

    # Merge: preserve existing mcp servers, add/update kinnycode-memory
    if "mcp" not in existing:
        existing["mcp"] = {}
    existing["mcp"]["kinnycode-memory"] = new_config["mcp"][
        "kinnycode-memory"
    ]

    mcp_file.write_text(_format_jsonc(existing), encoding="utf-8")


def _strip_json_comments(text: str) -> str:
    """Remove // line comments from a JSONC string.

    Handles comments both at the start of lines and after content.
    Does not handle /* block comments */.

    Args:
        text: JSONC source text.

    Returns:
        Valid JSON string with line comments removed.
    """
    lines = text.split("\n")
    result: list[str] = []
    for line in lines:
        # Find the first // outside of a string
        in_string = False
        string_char: str | None = None
        for i, ch in enumerate(line):
            if in_string:
                if ch == "\\" and i + 1 < len(line):
                    # Escaped character, skip next
                    continue  # handled by loop increment
                elif ch == string_char:
                    in_string = False
                    string_char = None
            else:
                if ch in ('"', "'"):
                    in_string = True
                    string_char = ch
                elif ch == "/" and i + 1 < len(line) and line[i + 1] == "/":
                    line = line[:i].rstrip()
                    break
        result.append(line)
    return "\n".join(result)


# ═══════════════════════════════════════════════════════════════════════════
#  Command: index
# ═══════════════════════════════════════════════════════════════════════════


def cmd_index(project_path: str | None = None) -> None:
    """Index a project's codebase into the memory server.

    Walks the project directory, collects text source files, and sends
    them to the memory server for chunking and embedding.

    Respects .kinnycode/ignore patterns and skips binary files,
    hidden directories, and files over 1 MB.

    Args:
        project_path: Path to the project root. Defaults to current directory.
    """
    # ── Resolve project path ────────────────────────────────────────────
    if project_path is None:
        project_path = str(Path.cwd())

    root = Path(project_path).resolve()

    if not root.is_dir():
        print(f"Error: Directory does not exist: {root}", file=sys.stderr)
        sys.exit(1)

    project_id = get_project_id(str(root))

    # Check if project has been initialized
    kinnycode_dir = root / ".kinnycode"
    if not kinnycode_dir.is_dir():
        print("[!] Project has not been initialized for KinnyCode.", file=sys.stderr)
        print(f"    Run 'kinnycode init {root}' first.", file=sys.stderr)
        sys.exit(1)

    print(f"Indexing project: {root.name}")
    print(f"  Project ID: {project_id}")
    print()

    # ── Load ignore patterns ────────────────────────────────────────────
    raw_patterns = load_ignore_patterns(root)
    parsed_patterns = _parse_ignore_patterns(raw_patterns)

    # ── Collect files ───────────────────────────────────────────────────
    files: list[tuple[str, str, str]] = []  # (relative_path, content, language)
    skipped_binary = 0
    skipped_size = 0
    skipped_ignored = 0
    total_files = 0

    print("Scanning files...")

    for entry in root.rglob("*"):
        if not entry.is_file():
            continue

        total_files += 1

        # Compute relative path in POSIX style
        try:
            rel_path = entry.relative_to(root).as_posix()
        except ValueError:
            continue

        # Check ignore patterns
        if should_ignore(rel_path, parsed_patterns):
            skipped_ignored += 1
            continue

        # Skip files without recognized extensions
        if entry.suffix.lower() not in _TEXT_EXTENSIONS:
            continue

        # Skip large files
        try:
            fsize = entry.stat().st_size
        except OSError:
            continue

        if fsize > _MAX_FILE_SIZE:
            skipped_size += 1
            continue

        # Skip binary files
        if is_binary_file(entry):
            skipped_binary += 1
            continue

        # Read file content
        try:
            content = entry.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        if not content.strip():
            continue

        language = detect_language(entry)
        files.append((rel_path, content, language))

    print(f"  Found {len(files)} indexable files")
    if skipped_ignored:
        print(f"  Skipped {skipped_ignored} files (ignore patterns)")
    if skipped_binary:
        print(f"  Skipped {skipped_binary} binary files")
    if skipped_size:
        print(f"  Skipped {skipped_size} files over 1 MB")
    print()

    if not files:
        print("[i] No files to index.")
        return

    # ── Send to server in batches ───────────────────────────────────────
    print(f"Sending to server at {SERVER_URL} ...")
    client = _get_http_client()

    total_indexed = 0
    total_chunks = 0
    batch_count = (len(files) + _BATCH_SIZE - 1) // _BATCH_SIZE

    for batch_idx in range(batch_count):
        start = batch_idx * _BATCH_SIZE
        end = min(start + _BATCH_SIZE, len(files))
        batch = files[start:end]

        payload_files = [
            {
                "file_path": f[0],
                "content": f[1],
                "language": f[2],
            }
            for f in batch
        ]

        payload = {
            "files": payload_files,
            "clear_first": (batch_idx == 0),
            "project_id": project_id,
        }

        try:
            resp = client.post(
                f"{SERVER_URL}/index-project",
                json=payload,
            )
            if resp.status_code == 200:
                data = resp.json()
                fi = data.get("files_indexed", 0)
                ci = data.get("chunks_indexed", 0)
                total_indexed += fi
                total_chunks += ci
                # Progress indicator
                progress = min(batch_idx + 1, batch_count)
                bar_len = 30
                filled = int(bar_len * progress / batch_count)
                bar = "█" * filled + "░" * (bar_len - filled)
                print(f"  [{bar}] Batch {progress}/{batch_count} — {fi} files, {ci} chunks")
            else:
                print(f"  [!] Batch {batch_idx + 1} failed: HTTP {resp.status_code}", file=sys.stderr)
        except Exception as exc:
            print(f"  [!] Batch {batch_idx + 1} error: {exc}", file=sys.stderr)

    print(f"\n[+] Indexing complete: {total_indexed} files, {total_chunks} chunks")


# ═══════════════════════════════════════════════════════════════════════════
#  Command: search
# ═══════════════════════════════════════════════════════════════════════════


def cmd_search(
    query: str,
    project_path: str | None = None,
    n_results: int = 5,
) -> None:
    """Perform semantic search across code and documents.

    Sends the query to the /retrieve-context endpoint, which searches
    across all memory layers: conversation history, architecture decisions,
    codebase, and indexed documents.

    Args:
        query: Natural language search query.
        project_path: Optional project path for context.
        n_results: Number of code results to include (default 5).
    """
    if not query.strip():
        print("Error: Search query cannot be empty.", file=sys.stderr)
        sys.exit(1)

    project_id: str | None = None
    if project_path:
        project_id = get_project_id(project_path)
    else:
        project_id = get_project_id()

    print(f"Search: \"{query}\"")
    if project_id:
        print(f"Project: {project_id}")
    print()

    client = _get_http_client()

    # ── Code search (structured results with scores) ────────────────────
    print("-" * 60)
    print("  CODE RESULTS")
    print("-" * 60)
    try:
        resp = client.post(
            f"{SERVER_URL}/semantic-search",
            json={"prompt": query, "n_results": n_results, "project_id": project_id},
        )
        if resp.status_code == 200:
            data = resp.json()
            results = data.get("results", [])
            if results:
                for i, r in enumerate(results, 1):
                    score = r.get("score", 1.0)
                    file_path = r.get("file_path", "unknown")
                    lang = r.get("language", "text")
                    snippet = r.get("snippet", "")
                    print(f"\n  [{i}] {file_path}  ({lang})  score={score:.3f}")
                    print(f"  {'-' * 54}")
                    # Truncate snippet for display
                    display = snippet[:400]
                    if len(snippet) > 400:
                        display += "..."
                    # Indent each line of the snippet
                    for line in display.split("\n"):
                        print(f"  | {line}")
            else:
                print("  (no code results found)")
        else:
            print(f"  [!] Code search failed: HTTP {resp.status_code}", file=sys.stderr)
    except Exception as exc:
        print(f"  [!] Code search error: {exc}", file=sys.stderr)

    # ── Document search ─────────────────────────────────────────────────
    print(f"\n{'-' * 60}")
    print("  DOCUMENT RESULTS")
    print("-" * 60)
    try:
        resp = client.post(
            f"{SERVER_URL}/search-documents",
            json={"query": query, "n_results": 3},
        )
        if resp.status_code == 200:
            data = resp.json()
            results = data.get("results", [])
            if results:
                for i, r in enumerate(results, 1):
                    score = r.get("score", 1.0)
                    source = r.get("source_file", "unknown")
                    doc_type = r.get("doc_type", "txt")
                    page = r.get("page_number")
                    snippet = r.get("snippet", "")
                    page_str = f", page {page}" if page is not None else ""
                    print(f"\n  [{i}] {source}  ({doc_type}{page_str})  score={score:.3f}")
                    print(f"  {'-' * 54}")
                    display = snippet[:400]
                    if len(snippet) > 400:
                        display += "..."
                    for line in display.split("\n"):
                        print(f"  | {line}")
            else:
                print("  (no document results found)")
        else:
            print(f"  [!] Document search failed: HTTP {resp.status_code}", file=sys.stderr)
    except Exception as exc:
        print(f"  [!] Document search error: {exc}", file=sys.stderr)

    print()


# ═══════════════════════════════════════════════════════════════════════════
#  Command: status
# ═══════════════════════════════════════════════════════════════════════════


def cmd_status(project_path: str | None = None) -> None:
    """Display memory statistics for a project.

    Shows code chunks indexed, document chunks, conversations stored,
    and architecture decisions recorded.

    Args:
        project_path: Path to the project root. Defaults to current directory.
    """
    if project_path is None:
        project_path = str(Path.cwd())

    root = Path(project_path).resolve()
    project_id = get_project_id(str(root))
    project_name = root.name

    print(f"Project: {project_name}")
    print(f"Path:    {root}")
    print(f"ID:      {project_id}")
    print()

    if not check_server_running():
        print("[!] Memory server is not running.", file=sys.stderr)
        print(f"    Start it with: kinnycode server start", file=sys.stderr)
        return

    client = _get_http_client()

    # ── Check initialization ────────────────────────────────────────────
    memory_json = root / ".kinnycode" / "memory.json"
    if memory_json.is_file():
        try:
            cfg = json.loads(memory_json.read_text(encoding="utf-8"))
            created = cfg.get("created_at", "unknown")
            print(f"Initialized: {created}")
        except Exception:
            print(f"Initialized: (config file found but could not be parsed)")
    else:
        print("[!] Project not initialized. Run 'kinnycode init' first.")
        print()

    print("-" * 60)
    print("  MEMORY LAYER STATS")
    print("-" * 60)

    # Use /project-info for all layers at once
    try:
        resp = client.post(f"{SERVER_URL}/project-info", json={"project_id": project_id})
        if resp.status_code == 200:
            data = resp.json()
            stats = data.get("stats", {})
            code_chunks = stats.get("code_chunks", 0)
            doc_chunks = stats.get("document_chunks", 0)
            conversations = stats.get("conversations", 0)
            decisions = stats.get("decisions", 0)
            tasks = stats.get("tasks", 0)

            print(f"\n  Layer 4 — Documents:")
            print(f"    Document chunks:   {doc_chunks:,}")
            print(f"\n  Layer 3 — Codebase:")
            print(f"    Code chunks:       {code_chunks:,}")
            print(f"\n  Layer 2 — Architecture Decisions:")
            print(f"    Decisions stored:  {decisions}")
            print(f"\n  Layer 1 — Conversations:")
            print(f"    Conversations:     {conversations}")
            print(f"\n  Layer 5 — Agent Tasks:")
            print(f"    Tasks registered:  {tasks}")
        else:
            print(f"\n  [!] Could not fetch project stats: HTTP {resp.status_code}")
    except Exception as exc:
        print(f"\n  [!] Could not fetch project stats: {exc}")

    # ── File counts in project ──────────────────────────────────────────
    kinnycode_dir = root / ".kinnycode"
    rules_file = kinnycode_dir / "rules.md"
    ignore_file = kinnycode_dir / "ignore"
    opencode_mcp = root / ".opencode" / "opencode.jsonc"

    print(f"\n{'-' * 60}")
    print("  CONFIGURATION")
    print("-" * 60)
    print(f"  .kinnycode/memory.json:  {'[+] exists' if memory_json.is_file() else '[ ] missing'}")
    print(f"  .kinnycode/rules.md:     {'[+] exists' if rules_file.is_file() else '[ ] missing'}")
    print(f"  .kinnycode/ignore:       {'[+] exists' if ignore_file.is_file() else '[ ] missing'}")
    print(f"  .opencode/opencode.jsonc: {'[+] exists' if opencode_mcp.is_file() else '[ ] missing'}")
    print()


# ═══════════════════════════════════════════════════════════════════════════
#  Command: uninstall
# ═══════════════════════════════════════════════════════════════════════════


def cmd_uninstall() -> None:
    """Uninstall KinnyCode: stop the server and remove runtime files.

    Does NOT remove project-level .kinnycode/ directories — those are
    per-project configuration files. Removes only the global PID file
    and asks for confirmation before proceeding.
    """
    print("KinnyCode Uninstall")
    print("=" * 60)
    print()
    print("This will:")
    print("  1. Stop the memory server if running")
    print("  2. Remove the global ~/.kinnycode/ directory (PID file, runtime state)")
    print()
    print("NOTE: Project-level .kinnycode/ directories are NOT removed.")
    print("      Delete them manually from each project if desired.")
    print()

    response = input("Continue? [y/N] ").strip().lower()
    if response not in ("y", "yes"):
        print("Uninstall cancelled.")
        return

    # ── Stop server ─────────────────────────────────────────────────────
    print("\n[1/2] Stopping memory server...")
    cmd_server_stop()

    # ── Remove global .kinnycode directory ──────────────────────────────
    print("\n[2/2] Removing global runtime files...")
    if PID_DIR.exists():
        try:
            import shutil

            shutil.rmtree(PID_DIR)
            print(f"  Removed {PID_DIR}")
        except Exception as exc:
            print(f"  [!] Could not remove {PID_DIR}: {exc}", file=sys.stderr)
    else:
        print(f"  {PID_DIR} does not exist — nothing to remove")

    print()
    print("[+] KinnyCode uninstalled successfully.")
    print()
    print("    To completely remove KinnyCode from this system:")
    print(f"    1. Delete project .kinnycode/ directories (in each project)")
    print(f"    2. Remove the kinnycode command from your PATH or scripts")
    print(f"    3. Uninstall Python packages: pip uninstall fastapi uvicorn lancedb httpx")
    if CLI_DIR.exists():
        print(f"    4. Delete the installation directory: {CLI_DIR}")


# ═══════════════════════════════════════════════════════════════════════════
#  Platform-specific process helpers
# ═══════════════════════════════════════════════════════════════════════════


def _read_pid_file() -> int | None:
    """Read the server PID from the PID file.

    Returns:
        The PID as an integer, or None if the file doesn't exist or is invalid.
    """
    if not PID_FILE.is_file():
        return None
    try:
        content = PID_FILE.read_text(encoding="utf-8").strip()
        return int(content)
    except (ValueError, OSError):
        return None


def _write_pid_file(pid: int) -> None:
    """Write the server PID to the PID file.

    Args:
        pid: The process ID to store.
    """
    PID_DIR.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(pid), encoding="utf-8")


def _delete_pid_file() -> None:
    """Delete the PID file if it exists."""
    try:
        PID_FILE.unlink(missing_ok=True)
    except OSError:
        pass


def _kill_process(pid: int) -> None:
    """Kill a process by PID, handling platform differences.

    On Windows, uses ``taskkill /F``. On Unix, sends SIGTERM first,
    then SIGKILL if the process doesn't exit.

    Args:
        pid: The process ID to terminate.

    Raises:
        OSError: If the process cannot be killed.
        ProcessLookupError: If no process exists with the given PID.
    """
    system = platform.system()

    if system == "Windows":
        # Use taskkill for reliable termination on Windows
        result = subprocess.run(
            ["taskkill", "/F", "/PID", str(pid)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            if "not found" in result.stderr.lower() or "no existe" in result.stderr.lower():
                raise ProcessLookupError(f"No process with PID {pid}")
            raise OSError(f"taskkill failed: {result.stderr.strip()}")
    else:
        # Unix: send SIGTERM
        try:
            os.kill(pid, 0)  # Check if process exists
        except OSError:
            raise ProcessLookupError(f"No process with PID {pid}")

        # Try graceful shutdown first
        try:
            os.kill(pid, __import__("signal").SIGTERM)
            time.sleep(1)
            # Check if still alive
            try:
                os.kill(pid, 0)
                # Still alive — force kill
                os.kill(pid, __import__("signal").SIGKILL)
            except OSError:
                pass  # Already dead
        except OSError:
            pass


def _kill_process_on_port(port: int) -> bool:
    """Kill the process listening on a specific port.

    Args:
        port: The TCP port number.

    Returns:
        True if a process was found and killed, False otherwise.
    """
    system = platform.system()

    if system == "Windows":
        try:
            result = subprocess.run(
                ["netstat", "-ano"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            for line in result.stdout.split("\n"):
                if f":{port}" in line and "LISTENING" in line:
                    parts = line.strip().split()
                    pid_str = parts[-1]
                    try:
                        pid = int(pid_str)
                        subprocess.run(
                            ["taskkill", "/F", "/PID", str(pid)],
                            capture_output=True,
                        )
                        return True
                    except (ValueError, OSError):
                        continue
        except Exception:
            pass
    else:
        # Try fuser first
        try:
            result = subprocess.run(
                ["fuser", "-k", f"{port}/tcp"],
                capture_output=True,
                timeout=10,
            )
            if result.returncode == 0:
                return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        # Try lsof as fallback
        try:
            result = subprocess.run(
                ["lsof", "-ti", f":{port}"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            pids = result.stdout.strip().split("\n")
            pids = [p for p in pids if p]
            if pids:
                for pid_str in pids:
                    try:
                        os.kill(int(pid_str), __import__("signal").SIGKILL)
                    except (ValueError, OSError):
                        pass
                return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

    return False


# ═══════════════════════════════════════════════════════════════════════════
#  Main entry point
# ═══════════════════════════════════════════════════════════════════════════


def main() -> None:
    """Parse command-line arguments and dispatch to the appropriate handler.

    Entry point for the ``kinnycode`` CLI tool.
    """
    parser = argparse.ArgumentParser(
        prog="kinnycode",
        description="KinnyCode — Multi-Layer Memory System CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Environment:\n"
            "  MEMORY_SERVER_URL   Server URL (default: http://127.0.0.1:8006)\n"
        ),
    )

    subparsers = parser.add_subparsers(
        dest="command",
        help="Available commands",
    )

    # ── server ──────────────────────────────────────────────────────────
    server_parser = subparsers.add_parser(
        "server",
        help="Manage the KinnyCode memory server",
        description="Start, stop, or check the status of the memory server.",
    )
    server_parser.add_argument(
        "action",
        choices=["start", "stop", "status"],
        help="Action to perform on the server",
    )

    # ── init ─────────────────────────────────────────────────────────────
    init_parser = subparsers.add_parser(
        "init",
        help="Initialize a project for KinnyCode memory",
        description=(
            "Initialize a project directory with .kinnycode/ configuration "
            "and .opencode/opencode.jsonc for MCP server integration."
        ),
    )
    init_parser.add_argument(
        "path",
        nargs="?",
        default=None,
        help="Project path (default: current directory)",
    )

    # ── index ────────────────────────────────────────────────────────────
    index_parser = subparsers.add_parser(
        "index",
        help="Index project codebase into memory",
        description=(
            "Scan and index the project's source code files into the "
            "KinnyCode memory server for semantic search."
        ),
    )
    index_parser.add_argument(
        "path",
        nargs="?",
        default=None,
        help="Project path (default: current directory)",
    )

    # ── search ───────────────────────────────────────────────────────────
    search_parser = subparsers.add_parser(
        "search",
        help="Semantic search across code and documents",
        description=(
            "Search indexed code and documents using natural language "
            "queries. Results include code snippets and document matches."
        ),
    )
    search_parser.add_argument(
        "query",
        help="Search query (natural language or code fragment)",
    )
    search_parser.add_argument(
        "--project",
        "-p",
        default=None,
        help="Project path for context (default: current directory)",
    )
    search_parser.add_argument(
        "--results",
        "-n",
        type=int,
        default=5,
        help="Number of results to return (default: 5)",
    )

    # ── status ───────────────────────────────────────────────────────────
    status_parser = subparsers.add_parser(
        "status",
        help="Show project memory statistics",
        description="Display memory layer stats and configuration status for a project.",
    )
    status_parser.add_argument(
        "path",
        nargs="?",
        default=None,
        help="Project path (default: current directory)",
    )

    # ── uninstall ────────────────────────────────────────────────────────
    subparsers.add_parser(
        "uninstall",
        help="Remove KinnyCode runtime files",
        description="Stop the server and remove global KinnyCode runtime files.",
    )

    # ── Parse and dispatch ──────────────────────────────────────────────
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    if args.command == "server":
        if args.action == "start":
            cmd_server_start()
        elif args.action == "stop":
            cmd_server_stop()
        elif args.action == "status":
            cmd_server_status()
    elif args.command == "init":
        cmd_init(args.path)
    elif args.command == "index":
        cmd_index(args.path)
    elif args.command == "search":
        cmd_search(args.query, args.project, args.results)
    elif args.command == "status":
        cmd_status(args.path)
    elif args.command == "uninstall":
        cmd_uninstall()
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
