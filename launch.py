#!/usr/bin/env python3
"""Launch nesus_ai's ultra-light manager and optional llama.cpp fallback."""
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

APP = "nesus-ai"
CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / APP
STATE_DIR = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / APP
LOCAL_ENV = CONFIG_DIR / "local.env"
SERVICE_FILE = STATE_DIR / "services.json"
MANAGER_LOG = STATE_DIR / "manager-stdout.log"
LLM_LOG = STATE_DIR / "local-llm.log"


def parse_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        out[key.strip()] = value
    return out


def settings() -> dict[str, str]:
    out = parse_env(LOCAL_ENV)
    out.update({k: v for k, v in os.environ.items() if k.startswith("NESUS_")})
    return out


def as_bool(value: str | None, default: bool = False) -> bool:
    return default if value is None else value.lower() in {"1", "true", "yes", "on", "oui"}


def as_int(cfg: dict[str, str], key: str, default: int, low: int, high: int) -> int:
    try:
        value = int(cfg.get(key, str(default)))
    except ValueError as exc:
        raise ValueError(f"{key} must be an integer") from exc
    return max(low, min(high, value))


def alive(pid: int) -> bool:
    if pid <= 1:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def read_state() -> dict[str, object]:
    try:
        value = json.loads(SERVICE_FILE.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_state(value: dict[str, object]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = SERVICE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(value, indent=2), encoding="utf-8")
    os.replace(tmp, SERVICE_FILE)


def endpoint_ready(host: str, port: int) -> bool:
    for path in ("/health", "/v1/models"):
        try:
            with urllib.request.urlopen(f"http://{host}:{port}{path}", timeout=1.0) as response:
                if response.status < 500:
                    return True
        except (urllib.error.URLError, TimeoutError, OSError):
            pass
    return False


def start_detached(command: list[str], log_path: Path, env: dict[str, str] | None = None) -> subprocess.Popen[bytes]:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    log = log_path.open("ab", buffering=0)
    try:
        proc = subprocess.Popen(
            command, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
            start_new_session=True, close_fds=True, env=env,
        )
    finally:
        log.close()
    return proc


def start_manager(cfg: dict[str, str], state: dict[str, object]) -> None:
    if not as_bool(cfg.get("NESUS_MANAGER_ENABLED"), True):
        print("Manager disabled.")
        return
    current = state.get("manager")
    if isinstance(current, dict) and alive(int(current.get("pid", 0) or 0)):
        print(f"Manager already running: pid={current['pid']}")
        return
    manager = shutil.which("nesus-ai-manager") or str(Path(__file__).with_name("manager.py"))
    command = [sys.executable, manager] if manager.endswith(".py") else [manager]
    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    proc = start_detached(command, MANAGER_LOG, env)
    state["manager"] = {
        "pid": proc.pid, "command": command, "log": str(MANAGER_LOG),
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    save_state(state)
    print(f"Manager started: pid={proc.pid}; log={MANAGER_LOG}")


def resolve_binary(raw: str) -> str:
    expanded = os.path.expanduser(os.path.expandvars(raw))
    found = expanded if os.path.sep in expanded else shutil.which(expanded)
    if not found or not Path(found).is_file():
        raise FileNotFoundError(f"llama-server not found: {raw}")
    return str(Path(found).resolve())


def start_local_llm(cfg: dict[str, str], state: dict[str, object], wait: int, force: bool) -> None:
    if not (as_bool(cfg.get("NESUS_LOCAL_LLM_ENABLED"), False) or force):
        print("Local LLM disabled (recommended while trading services use most resources).")
        return
    current = state.get("local_llm")
    if isinstance(current, dict) and alive(int(current.get("pid", 0) or 0)):
        print(f"Local LLM already running: pid={current['pid']}")
        return
    binary = resolve_binary(cfg.get("NESUS_LOCAL_LLM_BIN", "llama-server"))
    host = cfg.get("NESUS_LOCAL_LLM_HOST", "127.0.0.1")
    port = as_int(cfg, "NESUS_LOCAL_LLM_PORT", 8080, 1024, 65535)
    context = as_int(cfg, "NESUS_LOCAL_LLM_CONTEXT", 512, 256, 2048)
    threads = as_int(cfg, "NESUS_LOCAL_LLM_THREADS", 1, 1, 2)
    model_file = cfg.get("NESUS_LOCAL_MODEL_FILE", "").strip()
    model_hf = cfg.get("NESUS_LOCAL_MODEL_HF", "").strip()
    if bool(model_file) == bool(model_hf):
        raise ValueError("Configure exactly one local model source.")
    command = [binary]
    command += ["-m", os.path.expanduser(model_file)] if model_file else ["-hf", model_hf]
    command += ["--host", host, "--port", str(port), "-c", str(context), "-t", str(threads), "-np", "1"]
    if cfg.get("NESUS_LOCAL_LLM_EXTRA_ARGS"):
        command += shlex.split(cfg["NESUS_LOCAL_LLM_EXTRA_ARGS"])
    proc = start_detached(command, LLM_LOG)
    state["local_llm"] = {
        "pid": proc.pid, "host": host, "port": port, "command": command,
        "log": str(LLM_LOG), "started_at": datetime.now(timezone.utc).isoformat(),
    }
    save_state(state)
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline and proc.poll() is None:
        if endpoint_ready(host, port):
            print(f"Local LLM ready: pid={proc.pid}, http://{host}:{port}")
            return
        time.sleep(0.5)
    print(f"Local LLM started: pid={proc.pid}; log={LLM_LOG}")


def show_status(state: dict[str, object]) -> None:
    result: dict[str, object] = {}
    for name in ("manager", "local_llm"):
        service = state.get(name)
        if isinstance(service, dict):
            item = dict(service)
            item["process_alive"] = alive(int(service.get("pid", 0) or 0))
            if name == "local_llm":
                item["endpoint_ready"] = endpoint_ready(str(service.get("host", "127.0.0.1")), int(service.get("port", 8080)))
            result[name] = item
    print(json.dumps(result or {"status": "stopped"}, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description="Launch lightweight nesus_ai services")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--force-local", action="store_true")
    parser.add_argument("--wait", type=int, default=15)
    args = parser.parse_args()
    cfg, state = settings(), read_state()
    if args.status:
        show_status(state)
        return 0
    start_manager(cfg, state)
    start_local_llm(cfg, state, max(1, args.wait), args.force_local)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
    except (OSError, ValueError) as exc:
        print(f"launch.py: {exc}", file=sys.stderr)
        raise SystemExit(2)
