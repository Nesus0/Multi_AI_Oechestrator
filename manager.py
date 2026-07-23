#!/usr/bin/env python3
"""Ultra-light 24/7 health manager for nesus_ai (stdlib only)."""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

APP = "nesus-ai"
CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / APP
STATE_DIR = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / APP
LOCAL_ENV = CONFIG_DIR / "local.env"
INSTRUCTIONS = CONFIG_DIR / "instructions.md"
LOCK_FILE = STATE_DIR / "manager.lock"
LOG_FILE = STATE_DIR / "manager.jsonl"
MAX_LOG_BYTES = 1_000_000


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


def as_bool(value: str | None, default: bool = False) -> bool:
    return default if value is None else value.lower() in {"1", "true", "yes", "on", "oui"}


def as_int(cfg: dict[str, str], key: str, default: int, low: int, high: int) -> int:
    try:
        return max(low, min(high, int(cfg.get(key, str(default)))))
    except ValueError as exc:
        raise ValueError(f"{key} must be an integer") from exc


def log(event: str, **fields: object) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    if LOG_FILE.exists() and LOG_FILE.stat().st_size > MAX_LOG_BYTES:
        LOG_FILE.replace(LOG_FILE.with_suffix(".jsonl.1"))
    with LOG_FILE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"time": datetime.now(timezone.utc).isoformat(), "event": event, **fields}, ensure_ascii=False) + "\n")


def run(command: str, timeout: int) -> tuple[bool, str]:
    if not command.strip():
        return False, "command not configured"
    proc = subprocess.run(shlex.split(command), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, text=True, timeout=timeout, check=False)
    return proc.returncode == 0, proc.stdout[-1200:].strip()


def memory_mib() -> int:
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) // 1024
    except OSError:
        pass
    return 0


def load_1m() -> float:
    try:
        return float(Path("/proc/loadavg").read_text().split()[0])
    except (OSError, ValueError, IndexError):
        return 999.0


def resources_allow_ai(cfg: dict[str, str]) -> bool:
    return (memory_mib() >= as_int(cfg, "NESUS_MANAGER_MIN_AI_MEMORY_MIB", 350, 128, 8192)
            and load_1m() <= float(cfg.get("NESUS_MANAGER_MAX_AI_LOAD_1M", "0.80")))


def service_cfg(cfg: dict[str, str], prefix: str) -> dict[str, str]:
    return {"name": cfg.get(f"NESUS_{prefix}_NAME", prefix),
            "health": cfg.get(f"NESUS_{prefix}_HEALTH_CMD", ""),
            "recover": cfg.get(f"NESUS_{prefix}_RECOVERY_CMD", ""),
            "project": cfg.get(f"NESUS_{prefix}_PROJECT_DIR", "")}


def orchestrator_busy() -> bool:
    """Return True only for a currently held flock; stale lock files are harmless."""
    lock_dir = STATE_DIR / "locks"
    if not lock_dir.exists():
        return False
    for path in lock_dir.glob("*.lock"):
        try:
            fh = path.open("a+")
            try:
                fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.flock(fh, fcntl.LOCK_UN)
            except BlockingIOError:
                fh.close()
                return True
            fh.close()
        except OSError:
            continue
    return False


def escalate(service: dict[str, str], cfg: dict[str, str]) -> bool:
    if not service["project"] or not INSTRUCTIONS.exists() or orchestrator_busy():
        return False
    if not resources_allow_ai(cfg):
        log("ai_skipped_resources", service=service["name"], memory_mib=memory_mib(), load_1m=load_1m())
        return False
    task = (f"Read {INSTRUCTIONS} first. Restore only {service['name']} in {service['project']}. "
            "Make the smallest reversible repair and verify the configured health check.")
    log("ai_escalation", service=service["name"])
    proc = subprocess.run([cfg.get("NESUS_MANAGER_ORCHESTRATOR_BIN", "nesus_ai"), "run", "-C",
                           service["project"], task], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL,
                          timeout=as_int(cfg, "NESUS_MANAGER_AI_TIMEOUT", 900, 60, 7200), check=False)
    return proc.returncode == 0


def protect(service: dict[str, str], cfg: dict[str, str], settle: int) -> bool:
    healthy, detail = run(service["health"], 10)
    if healthy:
        return True
    log("health_failed", service=service["name"], detail=detail)
    if service["recover"]:
        ok, output = run(service["recover"], 30)
        log("recovery_command", service=service["name"], success=ok, detail=output)
        time.sleep(settle)
        healthy, detail = run(service["health"], 10)
        if healthy:
            log("recovered", service=service["name"], method="deterministic")
            return True
    escalate(service, cfg)
    healthy, detail = run(service["health"], 10)
    log("post_escalation", service=service["name"], healthy=healthy, detail=detail)
    return healthy


def main() -> int:
    parser = argparse.ArgumentParser(description="Ultra-light 24/7 trading service manager")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    cfg = parse_env(LOCAL_ENV)
    if not as_bool(cfg.get("NESUS_MANAGER_ENABLED"), True):
        return 0
    try:
        os.nice(19)
    except OSError:
        pass
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    lock = LOCK_FILE.open("w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return 0
    lock.write(str(os.getpid())); lock.flush()
    interval = as_int(cfg, "NESUS_MANAGER_INTERVAL", 60, 30, 3600)
    settle = as_int(cfg, "NESUS_MANAGER_SETTLE_SECONDS", 15, 3, 300)
    primary = service_cfg(cfg, "PRIORITY_SERVICE")
    secondary = service_cfg(cfg, "SECONDARY_SERVICE")
    log("manager_started", pid=os.getpid(), instructions=str(INSTRUCTIONS))
    while True:
        if protect(primary, cfg, settle):
            protect(secondary, cfg, settle)
        else:
            log("secondary_skipped", reason="priority service unhealthy")
        if args.once:
            return 0
        time.sleep(interval)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        log("manager_error", error=str(exc))
        print(f"manager.py: {exc}", file=sys.stderr)
        raise SystemExit(2)
