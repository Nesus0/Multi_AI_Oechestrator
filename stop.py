#!/usr/bin/env python3
"""Stop optional background services started by launch.py."""
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


def command_line(pid: int) -> str:
    path = Path(f"/proc/{pid}/cmdline")
    if not path.exists():
        return ""
    try:
        return path.read_bytes().replace(b"\0", b" ").decode("utf-8", errors="replace").strip()
    except OSError:
        return ""


def read_state() -> dict[str, object]:
    if not SERVICE_FILE.exists():
        return {}
    try:
        value = json.loads(SERVICE_FILE.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_state(data: dict[str, object]) -> None:
    if not data:
        SERVICE_FILE.unlink(missing_ok=True)
        return
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = SERVICE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, SERVICE_FILE)


def stop_process(pid: int, expected_command: str, timeout: float, force: bool) -> bool:
    if not process_alive(pid):
        return True
    observed = command_line(pid)
    if observed and expected_command:
        expected_binary = Path(expected_command.split()[0]).name
        if expected_binary not in observed and not force:
            raise RuntimeError(
                f"PID {pid} does not look like the registered service ({observed!r}). Use --force to override."
            )
    try:
        os.killpg(pid, signal.SIGTERM)
    except ProcessLookupError:
        return True
    except PermissionError as exc:
        raise RuntimeError(f"Permission denied while stopping PID {pid}") from exc
    except OSError:
        os.kill(pid, signal.SIGTERM)

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not process_alive(pid):
            return True
        time.sleep(0.25)

    try:
        os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        return True
    except OSError:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            return True
    return not process_alive(pid)


def main() -> int:
    parser = argparse.ArgumentParser(description="Stop optional nesus_ai background services.")
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--force", action="store_true", help="Ignore process identity mismatch.")
    args = parser.parse_args()

    state = read_state()
    service = state.get("local_llm")
    if not isinstance(service, dict):
        print("No local LLM service is registered.")
        return 0

    pid = int(service.get("pid", 0) or 0)
    command = service.get("command", [])
    expected = " ".join(str(part) for part in command) if isinstance(command, list) else str(command)
    stopped = stop_process(pid, expected, max(0.5, args.timeout), args.force)
    if not stopped:
        print(f"Unable to confirm shutdown of PID {pid}.", file=sys.stderr)
        return 1

    state.pop("local_llm", None)
    save_state(state)
    print(f"Local LLM stopped (pid={pid}).")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"stop.py: {exc}", file=sys.stderr)
        raise SystemExit(2)
