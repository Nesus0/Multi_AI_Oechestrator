#!/usr/bin/env python3
"""nesus_ai: lightweight autonomous multi-provider API router."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

APP = "nesus-ai"
VERSION = "1.1.0"
CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / APP
CONFIG_PATH = CONFIG_DIR / "config.toml"
SECRETS_PATH = CONFIG_DIR / "secrets.env"
INSTRUCTIONS_PATH = CONFIG_DIR / "instructions.md"
CACHE_PATH = CONFIG_DIR / "models-cache.json"

DEFAULT_INSTRUCTIONS = """# nesus_ai Global Instructions

You are a lightweight orchestration agent.

- Complete the user request with the fewest API calls possible.
- Prefer correctness, small context, targeted edits, and reversible changes.
- Never invent results or claim tests passed when they were not run.
- If a provider or model fails, switch route and continue within configured limits.
- Never expose secrets.
- Stop when the task is complete and return a compact result.
"""

DEFAULT_CONFIG = """[general]
provider_order = ["cerebras", "groq", "openrouter"]
timeout_seconds = 90
max_attempts = 8
max_models_per_provider = 3
max_prompt_chars = 24000
models_cache_seconds = 600

[providers.cerebras]
enabled = true
protocol = "openai"
base_url = "https://api.cerebras.ai/v1"
model = "auto"
auth = "bearer"
key_env = "CEREBRAS_API_KEY"

[providers.groq]
enabled = true
protocol = "openai"
base_url = "https://api.groq.com/openai/v1"
model = "auto"
auth = "bearer"
key_env = "GROQ_API_KEY"

[providers.openrouter]
enabled = true
protocol = "openai"
base_url = "https://openrouter.ai/api/v1"
model = "auto"
auth = "bearer"
key_env = "OPENROUTER_API_KEY"
headers = { X-OpenRouter-Title = "nesus_ai" }

# Google is fixed by design and never auto-selected.
# Add it with: nesus_ai add-provider
"""

DEFAULT_SECRETS = """# chmod 600 ~/.config/nesus-ai/secrets.env
CEREBRAS_API_KEY=
GROQ_API_KEY=
OPENROUTER_API_KEY=
"""

BLOCKED_MODEL_TERMS = (
    "embed", "embedding", "whisper", "tts", "speech", "audio", "moderation",
    "guard", "safety", "rerank", "transcribe", "vision-only", "image-gen",
)


def load_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) > 1 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        out[key.strip()] = value
    return out


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Run: {APP} init")
    with CONFIG_PATH.open("rb") as handle:
        return tomllib.load(handle)


def write_file(path: Path, content: str, mode: int = 0o600, force: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not force:
        return
    path.write_text(content, encoding="utf-8")
    os.chmod(path, mode)


def ask(label: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{label}{suffix}: ").strip()
    return value or default


def append_provider(name: str, protocol: str, base_url: str, model: str, auth: str,
                    key_env: str, header_name: str = "") -> None:
    safe = "".join(c if c.isalnum() or c in "_-" else "_" for c in name.lower()).strip("_")
    if not safe:
        raise ValueError("Invalid provider name")
    lines = [
        f"\n[providers.{safe}]", "enabled = true",
        f"protocol = {json.dumps(protocol)}",
        f"base_url = {json.dumps(base_url.rstrip('/'))}",
        f"model = {json.dumps(model)}",
        f"auth = {json.dumps(auth)}",
        f"key_env = {json.dumps(key_env)}",
    ]
    if header_name:
        lines.append(f"auth_header = {json.dumps(header_name)}")
    with CONFIG_PATH.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
    env = load_env(SECRETS_PATH)
    if key_env not in env:
        with SECRETS_PATH.open("a", encoding="utf-8") as handle:
            handle.write(f"{key_env}=\n")
    print(f"Added provider: {safe}")


def add_provider_interactive() -> None:
    print("Type: 1) Google Gemini  2) OpenAI-compatible/proxy  3) Claude-compatible/proxy")
    kind = ask("Choice", "2")
    if kind == "1":
        append_provider(
            "google", "openai",
            "https://generativelanguage.googleapis.com/v1beta/openai",
            "gemini-3.5-flash-lite", "bearer", "GEMINI_API_KEY",
        )
        return
    name = ask("Provider name", "custom")
    base = ask("Base URL")
    protocol = "anthropic" if kind == "3" else "openai"
    mode = ask("Authentication: bearer/header/none", "bearer").lower()
    header = ask("Header name", "x-api-key") if mode == "header" else ""
    key_env = ask("Environment variable", re.sub(r"\W+", "_", name.upper()) + "_API_KEY")
    fixed = ask("Fixed model or auto", "auto")
    append_provider(name, protocol, base, fixed, mode, key_env, header)


def init(force: bool = False) -> int:
    write_file(CONFIG_PATH, DEFAULT_CONFIG, force=force)
    write_file(SECRETS_PATH, DEFAULT_SECRETS, force=force)
    write_file(INSTRUCTIONS_PATH, DEFAULT_INSTRUCTIONS, force=force)
    print(f"Configuration: {CONFIG_PATH}\nSecrets: {SECRETS_PATH}\nInstructions: {INSTRUCTIONS_PATH}")
    if sys.stdin.isatty() and ask("Add Google or another provider now? y/N", "n").lower() in {"y", "yes", "o", "oui"}:
        add_provider_interactive()
    return 0


def headers_for(provider: dict[str, Any], key: str) -> dict[str, str]:
    headers = {"Content-Type": "application/json", "User-Agent": f"nesus-ai/{VERSION}"}
    headers.update({str(k): str(v) for k, v in provider.get("headers", {}).items()})
    auth = provider.get("auth", "bearer")
    if auth == "bearer" and key:
        headers["Authorization"] = f"Bearer {key}"
    elif auth == "header" and key:
        headers[str(provider.get("auth_header", "x-api-key"))] = key
    return headers


def http_json(url: str, headers: dict[str, str], timeout: int,
              body: dict[str, Any] | None = None) -> dict[str, Any]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers,
                                     method="GET" if body is None else "POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read(1600).decode(errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc


def cache_read() -> dict[str, Any]:
    try:
        value = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def cache_write(value: dict[str, Any]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(value, indent=2), encoding="utf-8")
    os.chmod(CACHE_PATH, 0o600)


def normalize_models(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw = payload.get("data", payload.get("models", []))
    if isinstance(raw, dict):
        raw = [raw]
    result: list[dict[str, Any]] = []
    for item in raw if isinstance(raw, list) else []:
        if isinstance(item, str):
            result.append({"id": item})
        elif isinstance(item, dict):
            model_id = item.get("id") or item.get("name")
            if model_id:
                result.append(dict(item, id=str(model_id).removeprefix("models/")))
    return result


def list_models(name: str, provider: dict[str, Any], secrets: dict[str, str],
                timeout: int, cache_seconds: int,
                refresh: bool = False) -> list[dict[str, Any]]:
    fixed = str(provider.get("model", "auto"))
    if name == "google" or fixed == "gemini-3.5-flash-lite":
        return [{"id": "gemini-3.5-flash-lite", "fixed": True}]
    if fixed and fixed != "auto":
        return [{"id": fixed, "fixed": True}]

    cache = cache_read()
    cached = cache.get(name, {}) if isinstance(cache.get(name), dict) else {}
    if not refresh and time.time() - float(cached.get("time", 0)) < cache_seconds:
        models = cached.get("models", [])
        if isinstance(models, list) and models:
            return models

    key = secrets.get(str(provider.get("key_env", "")), "")
    if provider.get("auth", "bearer") != "none" and not key:
        raise RuntimeError("missing API key")
    base = str(provider["base_url"]).rstrip("/")
    payload = http_json(base + "/models", headers_for(provider, key), timeout)
    models = normalize_models(payload)
    if not models:
        raise RuntimeError("models endpoint returned no usable model")
    cache[name] = {"time": time.time(), "models": models}
    cache_write(cache)
    return models


def task_profile(task: str) -> dict[str, bool]:
    text = task.lower()
    return {
        "simple": len(task) < 500 and not any(x in text for x in ("analyse", "architecture", "debug", "audit", "reason", "complex")),
        "code": any(x in text for x in ("code", "python", "javascript", "typescript", "bug", "debug", "test", "refactor", "docker", "linux", "api", "sql", "git")),
        "reasoning": any(x in text for x in ("analyse", "analysis", "reason", "architecture", "audit", "security", "compare", "plan", "strategy", "math")),
        "long": len(task) > 4000,
        "cheap": any(x in text for x in ("cheap", "low cost", "gratuit", "free", "économique", "rapide", "fast")),
    }


def model_score(model: dict[str, Any], profile: dict[str, bool]) -> float:
    model_id = str(model.get("id", ""))
    text = (model_id + " " + str(model.get("name", "")) + " " + str(model.get("description", ""))).lower()
    if any(term in text for term in BLOCKED_MODEL_TERMS):
        return -10000
    score = 0.0
    if profile["code"]:
        for term, value in (("coder", 35), ("code", 24), ("qwen", 12), ("deepseek", 15), ("gpt-oss", 18), ("glm", 10)):
            if term in text:
                score += value
    if profile["reasoning"]:
        for term, value in (("reason", 25), ("thinking", 20), ("120b", 22), ("70b", 16), ("32b", 10), ("pro", 8), ("deepseek", 14), ("gpt-oss", 14)):
            if term in text:
                score += value
    if profile["simple"] or profile["cheap"]:
        for term, value in (("instant", 22), ("lite", 18), ("flash", 16), ("mini", 14), ("8b", 12), ("small", 10), (":free", 25), ("free", 12)):
            if term in text:
                score += value
        if any(term in text for term in ("120b", "70b", "large", "max", "pro")):
            score -= 8
    context = None
    if isinstance(model.get("top_provider"), dict):
        context = model.get("context_length") or model["top_provider"].get("context_length")
    else:
        context = model.get("context_length")
    try:
        if profile["long"] and int(context or 0) >= 100000:
            score += 20
    except (TypeError, ValueError):
        pass
    pricing = model.get("pricing", {})
    if isinstance(pricing, dict):
        try:
            prompt_price = float(pricing.get("prompt", 0) or 0)
            completion_price = float(pricing.get("completion", 0) or 0)
            if prompt_price == 0 and completion_price == 0:
                score += 16
            elif profile["cheap"]:
                score -= min(20, (prompt_price + completion_price) * 1_000_000)
        except (TypeError, ValueError):
            pass
    score += min(5, len(str(model.get("supported_parameters", []))) / 4)
    return score


def ranked_models(models: list[dict[str, Any]], task: str, limit: int) -> list[str]:
    profile = task_profile(task)
    ranked = sorted(models,
                    key=lambda item: (model_score(item, profile), str(item.get("id", ""))),
                    reverse=True)
    return [str(item["id"]) for item in ranked
            if model_score(item, profile) > -1000][:max(1, limit)]


def request_provider(provider: dict[str, Any], model: str, prompt: str,
                     timeout: int, secrets: dict[str, str]) -> str:
    key = secrets.get(str(provider.get("key_env", "")), "")
    if provider.get("auth", "bearer") != "none" and not key:
        raise RuntimeError("missing API key")
    protocol = provider.get("protocol", "openai")
    base = str(provider["base_url"]).rstrip("/")
    if protocol == "anthropic":
        url = base if base.endswith("/v1/messages") else base + "/v1/messages"
        body = {"model": model, "max_tokens": 4096,
                "messages": [{"role": "user", "content": prompt}]}
        headers = headers_for(provider, key)
        headers.setdefault("anthropic-version", "2023-06-01")
    else:
        url = base if base.endswith("/chat/completions") else base + "/chat/completions"
        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": "Follow the supplied global instructions."},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
        }
        headers = headers_for(provider, key)
    payload = http_json(url, headers, timeout, body)
    if protocol == "anthropic":
        return "".join(str(item.get("text", ""))
                       for item in payload.get("content", []) if isinstance(item, dict))
    return str(payload["choices"][0]["message"]["content"])


def build_prompt(task: str, max_chars: int) -> str:
    instructions = INSTRUCTIONS_PATH.read_text(encoding="utf-8") if INSTRUCTIONS_PATH.exists() else DEFAULT_INSTRUCTIONS
    text = f"{instructions.strip()}\n\n# User task\n{task.strip()}"
    return text if len(text) <= max_chars else text[:max_chars] + "\n[context truncated]"


def run_task(task: str, provider_name: str | None = None,
             refresh_models: bool = False) -> int:
    cfg = load_config()
    general = cfg.get("general", {})
    providers = cfg.get("providers", {})
    secrets = {**load_env(SECRETS_PATH), **os.environ}
    order = [provider_name] if provider_name else list(general.get("provider_order", providers.keys()))
    timeout = int(general.get("timeout_seconds", 90))
    max_attempts = int(general.get("max_attempts", 8))
    max_models = int(general.get("max_models_per_provider", 3))
    cache_seconds = int(general.get("models_cache_seconds", 600))
    prompt = build_prompt(task, int(general.get("max_prompt_chars", 24000)))
    errors: list[str] = []
    attempts = 0

    for name in order:
        provider = providers.get(name)
        if not isinstance(provider, dict) or not provider.get("enabled", True):
            continue
        try:
            available = list_models(name, provider, secrets, timeout,
                                    cache_seconds, refresh_models)
            choices = ranked_models(available, task, max_models)
        except Exception as exc:
            errors.append(f"{name}/models: {exc}")
            print(errors[-1], file=sys.stderr)
            continue
        for model in choices:
            attempts += 1
            print(f"[{name}/{model}]", file=sys.stderr)
            try:
                print(request_provider(provider, model, prompt, timeout, secrets))
                return 0
            except Exception as exc:
                errors.append(f"{name}/{model}: {exc}")
                print(errors[-1], file=sys.stderr)
                if attempts >= max_attempts:
                    break
                time.sleep(min(2.0, 0.25 * attempts))
        if attempts >= max_attempts:
            break
    print("All routes failed:\n- " + "\n- ".join(errors), file=sys.stderr)
    return 1


def show_models(provider_name: str | None = None, refresh: bool = False) -> int:
    cfg = load_config()
    general = cfg.get("general", {})
    providers = cfg.get("providers", {})
    secrets = {**load_env(SECRETS_PATH), **os.environ}
    timeout = int(general.get("timeout_seconds", 90))
    cache_seconds = int(general.get("models_cache_seconds", 600))
    names = [provider_name] if provider_name else list(providers.keys())
    failed = False
    for name in names:
        provider = providers.get(name)
        if not isinstance(provider, dict) or not provider.get("enabled", True):
            continue
        try:
            models = list_models(name, provider, secrets, timeout,
                                 cache_seconds, refresh)
            print(f"\n{name} ({len(models)} models)")
            for item in models:
                print(f"- {item.get('id')}")
        except Exception as exc:
            failed = True
            print(f"{name}: {exc}", file=sys.stderr)
    return 1 if failed else 0


def doctor() -> int:
    cfg = load_config()
    secrets = {**load_env(SECRETS_PATH), **os.environ}
    bad = 0
    print(f"nesus_ai {VERSION}\npython={sys.version.split()[0]}\nconfig={CONFIG_PATH}\ninstructions={INSTRUCTIONS_PATH}")
    for name, provider in cfg.get("providers", {}).items():
        status = "configured" if secrets.get(str(provider.get("key_env", ""))) or provider.get("auth") == "none" else "missing-key"
        configured_model = str(provider.get("model", "auto"))
        mode = "fixed:" + configured_model if configured_model != "auto" else "auto-discovery"
        print(f"{name}: {status} {mode} url={provider.get('base_url')}")
        bad += status == "missing-key"
    return 1 if bad else 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="nesus_ai")
    parser.add_argument("--version", action="version", version=VERSION)
    sub = parser.add_subparsers(dest="cmd", required=True)
    init_parser = sub.add_parser("init")
    init_parser.add_argument("--force", action="store_true")
    sub.add_parser("add-provider")
    sub.add_parser("doctor")
    models_parser = sub.add_parser("models")
    models_parser.add_argument("--provider")
    models_parser.add_argument("--refresh", action="store_true")
    run_parser = sub.add_parser("run")
    run_parser.add_argument("task", nargs="?")
    run_parser.add_argument("--provider")
    run_parser.add_argument("--refresh-models", action="store_true")
    args = parser.parse_args()

    if args.cmd == "init":
        return init(args.force)
    if args.cmd == "add-provider":
        add_provider_interactive()
        return 0
    if args.cmd == "doctor":
        return doctor()
    if args.cmd == "models":
        return show_models(args.provider, args.refresh)
    task = args.task or sys.stdin.read()
    if not task.strip():
        print("Task required", file=sys.stderr)
        return 2
    return run_task(task, args.provider, args.refresh_models)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
