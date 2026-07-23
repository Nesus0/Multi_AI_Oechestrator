#!/usr/bin/env python3
"""Stop nesus_ai background services safely."""
from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
from pathlib import Path

APP = "nesus-ai"
STATE_DIR = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / APP
SERVICE_FILE = STATE_DIR / "services.json"


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


def command_line(pid: int) -> str:
    try:
        return Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")
    except OSError:
        return ""


def read_state() -> dict[str, object]:
    try:
        value = json.loads(SERVICE_FILE.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_state(value: dict[str, object]) -> None:
    if not value:
        SERVICE_FILE.unlink(missing_ok=True)
        return
    tmp = SERVICE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(value, indent=2), encoding="utf-8")
    os.replace(tmp, SERVICE_FILE)


def stop_one(name: str, service: dict[str, object], timeout: float, force: bool) -> bool:
    pid = int(service.get("pid", 0) or 0)
    if not alive(pid):
        print(f"{name}: already stopped")
        return True
    expected = " ".join(str(x) for x in service.get("command", []))
    observed = command_line(pid)
    if observed and expected:
        binary = Path(expected.split()[0]).name
        if binary not in observed and not force:
            raise RuntimeError(f"PID {pid} does not match {name}; use --force")
    try:
        os.killpg(pid, signal.SIGTERM)
    except OSError:
        os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not alive(pid):
            print(f"{name}: stopped (pid={pid})")
            return True
        time.sleep(0.25)
    try:
        os.killpg(pid, signal.SIGKILL)
    except OSError:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    stopped = not alive(pid)
    print(f"{name}: {'stopped' if stopped else 'unable to confirm stop'} (pid={pid})")
    return stopped


def main() -> int:
    parser = argparse.ArgumentParser(description="Stop nesus_ai manager and local fallback")
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--manager-only", action="store_true")
    parser.add_argument("--local-only", action="store_true")
    args = parser.parse_args()
    state = read_state()
    if not state:
        print("No nesus_ai background service is registered.")
        return 0
    names = ["manager", "local_llm"]
    if args.manager_only:
        names = ["manager"]
    elif args.local_only:
        names = ["local_llm"]
    failed = False
    for name in names:
        service = state.get(name)
        if isinstance(service, dict):
            if stop_one(name, service, max(0.5, args.timeout), args.force):
                state.pop(name, None)
            else:
                failed = True
    save_state(state)
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"stop.py: {exc}", file=sys.stderr)
        raise SystemExit(2)
