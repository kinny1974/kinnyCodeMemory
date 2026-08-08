"""
KinnyCode Memory System — Windows Service Wrapper
===================================================
Manages the memory server as a Windows service via Task Scheduler.

Provides:
  - create_service()  — Register a scheduled task that starts at logon
  - delete_service()  — Remove the scheduled task
  - start_service()   — Start the task immediately
  - stop_service()    — Stop the running server
  - restart_service() — Stop + Start
  - service_status()  — Check if the service is running
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

def find_venv_python(venv_path: Path) -> Path:
    """Find python.exe in venv (handles MSYS2 'bin/' vs standard 'Scripts/')."""
    for subdir in ("Scripts", "bin"):
        candidate = venv_path / subdir / "python.exe"
        if candidate.exists():
            return candidate
    return venv_path / "Scripts" / "python.exe"

# ── Constants ──────────────────────────────────────────────────────────────
SERVICE_TASK_NAME = "KinnyCodeMemoryServer"
DEFAULT_PORT = 8006
DEFAULT_INSTALL_DIR = Path(os.environ.get("PROGRAMDATA", "C:\\ProgramData")) / "KinnyCode" / "memory"

# ═══════════════════════════════════════════════════════════════════════════
#  PowerShell helpers
# ═══════════════════════════════════════════════════════════════════════════

def _run_ps(command: str, timeout: int = 30) -> tuple[int, str, str]:
    """Execute a PowerShell command and return (exit_code, stdout, stderr)."""
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True, text=True, timeout=timeout
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", "Timeout"
    except Exception as e:
        return -1, "", str(e)


# ═══════════════════════════════════════════════════════════════════════════
#  Service operations
# ═══════════════════════════════════════════════════════════════════════════

def create_service(
    install_dir: str | Path | None = None,
    port: int = DEFAULT_PORT,
    python_exe: str | Path | None = None,
) -> dict:
    """
    Register the memory server as a Windows scheduled task (logon trigger).

    Returns dict with: ok, task_name, message
    """
    if install_dir is None:
        install_dir = DEFAULT_INSTALL_DIR
    install_dir = Path(install_dir)

    if python_exe is None:
        python_exe = find_venv_python(install_dir / ".venv")
    python_exe = Path(python_exe)

    cli_script = install_dir / "cli.py"

    if not python_exe.exists():
        return {"ok": False, "error": f"Python no encontrado: {python_exe}"}
    if not cli_script.exists():
        return {"ok": False, "error": f"cli.py no encontrado: {cli_script}"}

    result: dict[str, Any] = {"ok": True, "task_name": SERVICE_TASK_NAME}

    # Remove existing task first
    _run_ps(
        f"$task = Get-ScheduledTask -TaskName '{SERVICE_TASK_NAME}' -ErrorAction SilentlyContinue; "
        f"if ($task) {{ Unregister-ScheduledTask -TaskName '{SERVICE_TASK_NAME}' -Confirm:$false }}"
    )

    # Create new task
    user = os.environ.get("USERNAME", os.environ.get("USER", ""))
    ps_cmd = (
        "$action = New-ScheduledTaskAction -Execute '" + str(python_exe) + "' "
        "-Argument '\"" + str(cli_script) + "\" server start --port " + str(port) + "'; "
        "$trigger = New-ScheduledTaskTrigger -AtLogOn -User '" + user + "'; "
        "$settings = New-ScheduledTaskSettingsSet "
        "-AllowStartIfOnBatteries -DontStopIfGoingOnBatteries "
        "-StartWhenAvailable -RestartCount 3 "
        "-RestartInterval (New-TimeSpan -Minutes 1) "
        "-ExecutionTimeLimit (New-TimeSpan -Days 365); "
        "Register-ScheduledTask -TaskName '" + SERVICE_TASK_NAME + "' "
        "-Action $action -Trigger $trigger -Settings $settings "
        "-Description 'KinnyCode Memory Server — auto-starts at user logon' "
        "-Force | Out-Null; "
        "if ($?) { Write-Output 'OK' } else { Write-Error 'FAIL' }"
    )

    exit_code, stdout, stderr = _run_ps(ps_cmd)
    if exit_code != 0 or "FAIL" in stderr:
        result["ok"] = False
        result["error"] = stderr or "Error desconocido"

    return result


def delete_service() -> dict:
    """Remove the scheduled task."""
    exit_code, stdout, stderr = _run_ps(
        f"$task = Get-ScheduledTask -TaskName '{SERVICE_TASK_NAME}' -ErrorAction SilentlyContinue; "
        f"if ($task) {{ Unregister-ScheduledTask -TaskName '{SERVICE_TASK_NAME}' -Confirm:$false; "
        f"Write-Output 'OK' }} else {{ Write-Output 'NOT_FOUND' }}"
    )
    return {
        "ok": exit_code == 0,
        "deleted": stdout == "OK",
        "task_name": SERVICE_TASK_NAME,
    }


def start_service() -> dict:
    """Start the scheduled task immediately."""
    exit_code, stdout, stderr = _run_ps(
        f"$task = Get-ScheduledTask -TaskName '{SERVICE_TASK_NAME}' -ErrorAction SilentlyContinue; "
        f"if ($task) {{ Start-ScheduledTask -TaskName '{SERVICE_TASK_NAME}'; Write-Output 'OK' }} "
        f"else {{ Write-Output 'NOT_FOUND' }}"
    )
    return {"ok": exit_code == 0, "started": stdout == "OK", "task_name": SERVICE_TASK_NAME}


def stop_service(port: int = DEFAULT_PORT) -> dict:
    """Stop the memory server by killing the process on the port."""
    exit_code, stdout, stderr = _run_ps(
        f"$conns = Get-NetTCPConnection -LocalPort {port} -ErrorAction SilentlyContinue; "
        f"if ($conns) {{ "
        f"  foreach ($c in $conns) {{ Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue }}; "
        f"  Write-Output 'STOPPED' "
        f"}} else {{ Write-Output 'NOT_RUNNING' }}"
    )
    return {"ok": exit_code == 0, "status": stdout or "unknown"}


def restart_service(install_dir: Path | None = None, port: int = DEFAULT_PORT) -> dict:
    """Stop and restart the server."""
    stop_result = stop_service(port)
    time.sleep(2)
    start_result = start_service()
    return {"ok": start_result["ok"], "stop": stop_result, "start": start_result}


def service_status(port: int = DEFAULT_PORT) -> dict:
    """Check if the server is running and if the task is registered."""
    # Check task existence
    _, task_out, _ = _run_ps(
        f"$task = Get-ScheduledTask -TaskName '{SERVICE_TASK_NAME}' -ErrorAction SilentlyContinue; "
        f"if ($task) {{ Write-Output 'REGISTERED' }} else {{ Write-Output 'NOT_REGISTERED' }}"
    )
    task_registered = "REGISTERED" in task_out

    # Check port
    import socket
    running = False
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1)
        running = s.connect_ex(("127.0.0.1", port)) == 0
        s.close()
    except Exception:
        pass

    return {
        "task_registered": task_registered,
        "server_running": running,
        "port": port,
        "task_name": SERVICE_TASK_NAME,
    }


# ═══════════════════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════════════════

def main():
    import argparse
    parser = argparse.ArgumentParser(description="KinnyCode Windows Service Manager")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("create", help="Create service (scheduled task)")
    sub.add_parser("delete", help="Delete service")
    sub.add_parser("start", help="Start server via task")
    sub.add_parser("stop", help="Stop server")
    sub.add_parser("restart", help="Restart server")
    sub.add_parser("status", help="Service status")

    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Server port")
    parser.add_argument("--install-dir", type=str, help="Install directory")
    parser.add_argument("--python-exe", type=str, help="Python executable")

    args = parser.parse_args()

    install_dir = Path(args.install_dir) if args.install_dir else DEFAULT_INSTALL_DIR
    port = args.port

    if args.command == "create":
        result = create_service(install_dir, port, args.python_exe)
    elif args.command == "delete":
        result = delete_service()
    elif args.command == "start":
        result = start_service()
    elif args.command == "stop":
        result = stop_service(port)
    elif args.command == "restart":
        result = restart_service(install_dir, port)
    elif args.command == "status":
        result = service_status(port)
    else:
        parser.print_help()
        return

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
