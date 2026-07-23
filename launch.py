#!/usr/bin/env python3
"""Start optional lightweight local services for nesus_ai.

The orchestrator itself is an on-demand CLI and does not need a daemon. This
launcher only manages the optional llama.cpp fallback server. It has no third-
party Python dependencies and never downloads a model implicitly.
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

APP = "nesus-ai"
CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / APP
STATE_DIR = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / APP
LOCAL_ENV = CONFIG_DIR / "local.env"
SERVICE_FILE = STATE_DIR / "services.json"
LOG_FILE = STATE_DIR / "local-llm.log"


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            raise ValueError(f"Invalid line {number} in {path}")
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    return values


def merged_settings() -> dict[str, str]:
    settings = parse_env_file(LOCAL_ENV)
    for key, value in os.environ.items():
        if key.startswith("NESUS_LOCAL_"):
            settings[key] = value
    return settings


def as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on", "oui"}


def as_int(settings: Mapping[str, str], key: str, default: int, minimum: int, maximum: int) -> int:
    raw = settings.get(key, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{key} must be an integer, got {raw!r}") from exc
    if not minimum <= value <= maximum:
        raise ValueError(f"{key} must be between {minimum} and {maximum}")
    return value


def process_alive(pid: int) -> bool:
    if pid <= 1:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def read_state() -> dict[str, object]:
    if not SERVICE_FILE.exists():
        return {}
    try:
        data = json.loads(SERVICE_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_state(data: dict[str, object]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = SERVICE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, SERVICE_FILE)


def available_memory_mib() -> int | None:
    meminfo = Path("/proc/meminfo")
    if not meminfo.exists():
        return None
    for line in meminfo.read_text(encoding="utf-8", errors="ignore").splitlines():
        if line.startswith("MemAvailable:"):
            parts = line.split()
            if len(parts) >= 2 and parts[1].isdigit():
                return int(parts[1]) // 1024
    return None


def endpoint_ready(host: str, port: int, timeout: float = 1.5) -> bool:
    for path in ("/health", "/v1/models"):
        try:
            with urllib.request.urlopen(f"http://{host}:{port}{path}", timeout=timeout) as response:
                if 200 <= response.status < 500:
                    return True
        except (urllib.error.URLError, TimeoutError, OSError):
            continue
    return False


def resolve_binary(raw: str) -> str:
    expanded = os.path.expandvars(os.path.expanduser(raw))
    if os.path.sep in expanded:
        path = Path(expanded)
        if not path.is_file() or not os.access(path, os.X_OK):
            raise FileNotFoundError(f"llama.cpp server is not executable: {path}")
        return str(path.resolve())
    found = shutil.which(expanded)
    if not found:
        raise FileNotFoundError(
            f"{expanded!r} was not found in PATH. Install llama.cpp or set NESUS_LOCAL_LLM_BIN."
        )
    return found


def build_command(settings: Mapping[str, str]) -> tuple[list[str], str, int]:
    binary = resolve_binary(settings.get("NESUS_LOCAL_LLM_BIN", "llama-server"))
    host = settings.get("NESUS_LOCAL_LLM_HOST", "127.0.0.1").strip()
    port = as_int(settings, "NESUS_LOCAL_LLM_PORT", 8080, 1024, 65535)
    context = as_int(settings, "NESUS_LOCAL_LLM_CONTEXT", 1024, 256, 8192)
    threads = as_int(settings, "NESUS_LOCAL_LLM_THREADS", 1, 1, max(1, os.cpu_count() or 1))

    model_file = settings.get("NESUS_LOCAL_MODEL_FILE", "").strip()
    model_hf = settings.get("NESUS_LOCAL_MODEL_HF", "").strip()
    if bool(model_file) == bool(model_hf):
        raise ValueError(
            "Configure exactly one of NESUS_LOCAL_MODEL_FILE or NESUS_LOCAL_MODEL_HF in local.env."
        )

    command = [binary]
    if model_file:
        path = Path(os.path.expandvars(os.path.expanduser(model_file))).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Local GGUF model not found: {path}")
        command += ["-m", str(path)]
    else:
        command += ["-hf", model_hf]

    command += [
        "--host", host,
        "--port", str(port),
        "-c", str(context),
        "-t", str(threads),
        "-np", "1",
    ]
    extra = settings.get("NESUS_LOCAL_LLM_EXTRA_ARGS", "").strip()
    if extra:
        command.extend(shlex.split(extra))
    return command, host, port


def start_local_llm(settings: Mapping[str, str], wait_seconds: int) -> int:
    state = read_state()
    service = state.get("local_llm")
    if isinstance(service, dict):
        pid = int(service.get("pid", 0) or 0)
        host = str(service.get("host", "127.0.0.1"))
        port = int(service.get("port", 8080) or 8080)
        if process_alive(pid):
            status = "ready" if endpoint_ready(host, port) else "starting/unhealthy"
            print(f"Local LLM already running: pid={pid}, http://{host}:{port}, status={status}")
            return 0
        state.pop("local_llm", None)
        save_state(state)

    command, host, port = build_command(settings)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    memory = available_memory_mib()
    if memory is not None and memory < 750:
        print(
            f"Warning: only about {memory} MiB RAM is currently available. "
            "Use a sub-1B Q4 model, 1K context, one thread, and swap.",
            file=sys.stderr,
        )

    log_handle = LOG_FILE.open("ab", buffering=0)
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            close_fds=True,
        )
    except Exception:
        log_handle.close()
        raise
    log_handle.close()

    state["local_llm"] = {
        "pid": process.pid,
        "host": host,
        "port": port,
        "command": command,
        "log": str(LOG_FILE),
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    save_state(state)

    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            state.pop("local_llm", None)
            save_state(state)
            print(f"Local LLM exited with code {process.returncode}. See {LOG_FILE}", file=sys.stderr)
            return 1
        if endpoint_ready(host, port):
            print(f"Local LLM ready: pid={process.pid}, http://{host}:{port}")
            print(f"Log: {LOG_FILE}")
            return 0
        time.sleep(0.5)

    print(f"Local LLM started: pid={process.pid}; health check still pending. Log: {LOG_FILE}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Start optional lightweight local services for nesus_ai.")
    parser.add_argument("--wait", type=int, default=30, help="Seconds to wait for local LLM readiness.")
    parser.add_argument("--force-local", action="store_true", help="Start local LLM even when disabled in local.env.")
    parser.add_argument("--status", action="store_true", help="Only display current service status.")
    args = parser.parse_args()

    settings = merged_settings()
    state = read_state()
    service = state.get("local_llm")
    if args.status:
        if isinstance(service, dict):
            pid = int(service.get("pid", 0) or 0)
            host = str(service.get("host", "127.0.0.1"))
            port = int(service.get("port", 8080) or 8080)
            print(json.dumps({
                "pid": pid,
                "process_alive": process_alive(pid),
                "endpoint_ready": endpoint_ready(host, port),
                "endpoint": f"http://{host}:{port}",
                "log": service.get("log"),
            }, indent=2))
            return 0
        print("No nesus_ai background service is registered.")
        return 0

    enabled = as_bool(settings.get("NESUS_LOCAL_LLM_ENABLED"), False) or args.force_local
    print("nesus_ai is an on-demand CLI; no orchestrator daemon is required.")
    if not enabled:
        print(f"Local LLM is disabled. Enable it in {LOCAL_ENV} or use --force-local.")
        return 0
    return start_local_llm(settings, max(1, args.wait))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        raise SystemExit(130)
    except (OSError, ValueError) as exc:
        print(f"launch.py: {exc}", file=sys.stderr)
        raise SystemExit(2)
