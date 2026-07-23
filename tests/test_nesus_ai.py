import asyncio
import importlib.util
import os
import sys
from pathlib import Path

MODULE_PATH = Path(__file__).parents[1] / "nesus_ai.py"
spec = importlib.util.spec_from_file_location("nesus_ai", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
assert spec.loader
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def make_config(accounts, models=None, strategy="least_recently_used"):
    general = mod.GeneralConfig(provider_order=["codex"], account_strategy=strategy, server_retries=0)
    models = models or [mod.ModelProfile("luna", "gpt-5.6-luna", "low", capabilities=["code", "general"])]
    provider = mod.ProviderConfig(
        name="codex", enabled=True, priority=100, capabilities=["code", "general"],
        command=[sys.executable, "-c", "print('ok')", "{prompt}"], env={}, accounts=accounts, models=models,
    )
    return mod.Config(general=general, providers={"codex": provider}), provider


def test_classify_errors():
    assert mod.classify_failure("unexpected status 401 Unauthorized: invalid API key", 1, False, False) == "auth"
    assert mod.classify_failure("HTTP 429 too many requests", 1, False, False) == "rate_limit"
    assert mod.classify_failure("503 upstream service temporarily unavailable", 1, False, False) == "server"
    assert mod.classify_failure("413 payload too large", 1, False, False) == "context"
    assert mod.classify_failure("model not found", 1, False, False) == "model_unavailable"


def test_natural_directory(tmp_path):
    prompt = f"fais le taff dans le dossier '{tmp_path}'"
    assert mod.resolve_workdir(None, prompt) == tmp_path.resolve()


def test_command_model_and_thinking_expansion(tmp_path):
    account = mod.AccountConfig("a")
    model = mod.ModelProfile("sol", "gpt-5.6-sol", "high")
    provider = mod.ProviderConfig("x", True, 1, ["general"],
        ["agent", "--model", "{model}", "--effort", "{thinking}", "{prompt}"], {}, [account], [model])
    cmd = mod.expand_command(provider, account, model, "hello", tmp_path)
    assert cmd[-1] == "hello"
    assert "gpt-5.6-sol" in cmd
    assert "high" in cmd


def test_selected_secret_only_is_exposed(monkeypatch):
    a1 = mod.AccountConfig("one", env_from={"GEMINI_API_KEY": "POOL_KEY_1"})
    a2 = mod.AccountConfig("two", env_from={"GEMINI_API_KEY": "POOL_KEY_2"})
    config, provider = make_config([a1, a2])
    monkeypatch.setenv("POOL_KEY_1", "secret-one-123")
    monkeypatch.setenv("POOL_KEY_2", "secret-two-456")
    env = mod.build_runtime_env(config, provider, a1, provider.models[0], {}, base_env=dict(os.environ))
    assert env["GEMINI_API_KEY"] == "secret-one-123"
    assert "POOL_KEY_1" not in env and "POOL_KEY_2" not in env
    assert "secret-two-456" not in env.values()


def test_lru_account_rotation():
    a1 = mod.AccountConfig("one", env_from={"X": "K1"})
    a2 = mod.AccountConfig("two", env_from={"X": "K2"})
    config, provider = make_config([a1, a2])
    state = {"providers": {"codex": {"accounts": {"one": {"last_run": 200}, "two": {"last_run": 100}}}}}
    ordered = mod.account_candidates(config, provider, state, {"K1": "a", "K2": "b"})
    assert [a.name for a in ordered] == ["two", "one"]


def test_complexity_routes_simple_to_luna_and_hard_to_sol():
    account = mod.AccountConfig("one")
    models = [
        mod.ModelProfile("luna", "gpt-5.6-luna", "low", priority=120, cost_rank=1,
                         min_complexity=0, max_complexity=45, capabilities=["code", "general"]),
        mod.ModelProfile("sol", "gpt-5.6-sol", "high", priority=100, cost_rank=4,
                         min_complexity=45, max_complexity=100, capabilities=["code", "debug", "security", "general"]),
    ]
    config, provider = make_config([account], models=models)
    simple = mod.model_candidates(config, provider, {"providers": {}}, {"code", "general"}, 20)
    hard = mod.model_candidates(config, provider, {"providers": {}}, {"code", "debug", "security"}, 90)
    assert simple[0].name == "luna"
    assert hard[0].name == "sol"


def test_large_context_prefers_fable():
    account = mod.AccountConfig("one")
    models = [
        mod.ModelProfile("sonnet", "claude-sonnet-4-6", "high", priority=112, cost_rank=2,
                         min_complexity=0, max_complexity=75, capabilities=["code", "analysis", "general"]),
        mod.ModelProfile("fable", "claude-fable-5", "high", priority=105, cost_rank=5,
                         min_complexity=40, max_complexity=100, capabilities=["large-context", "analysis", "general"], long_context=True),
    ]
    config, provider = make_config([account], models=models)
    provider.name = "claude"
    config.providers = {"claude": provider}
    candidates = mod.model_candidates(config, provider, {"providers": {}}, {"large-context", "analysis"}, 80)
    assert candidates[0].name == "fable"


def test_long_task_is_offloaded(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "RUNS_DIR", tmp_path)
    mod.ensure_dirs()
    ref, path = mod.prepare_task_payload("run1", "x" * 2000, 100)
    assert path is not None and path.exists()
    assert len(ref) < 500
    assert path.read_text() == "x" * 2000


def test_bounded_prompt(tmp_path):
    general = mod.GeneralConfig(provider_order=["codex"], max_prompt_chars=5000,
                                max_handoff_chars=1000, max_git_summary_chars=1000)
    model = mod.ModelProfile("sol", "gpt-5.6-sol", "high")
    previous = [mod.AttemptResult("codex", "a", "luna", "gpt-5.6-luna", "low", False, 1,
                                  "process", "z" * 20000, 1.0)]
    prompt = mod.build_agent_prompt("task", tmp_path, previous, general, model)
    assert len(prompt) <= 5000
    assert "PAYLOAD AND TOKEN CONTROL" in prompt


def test_cooldown_is_per_account_and_model():
    result = mod.AttemptResult("codex", "one", "luna", "gpt-5.6-luna", "low", False, 1, "auth", "401", 0.1)
    state = {"providers": {}}
    general = mod.GeneralConfig(provider_order=["codex"], auth_cooldown_seconds=100)
    mod.update_state(state, result, general)
    assert state["providers"]["codex"]["accounts"]["one"]["cooldown_until"] > mod.now_ts()
    assert "two" not in state["providers"]["codex"]["accounts"]
    assert "luna" in state["providers"]["codex"]["models"]


def test_failover_to_second_key(tmp_path, monkeypatch):
    fake = tmp_path / "fake_agent.py"
    fake.write_text("""
import os, pathlib, sys
key = os.environ.get('OPENAI_API_KEY')
if key == 'bad-key-123':
    print('unexpected status 401 Unauthorized: invalid API key')
    raise SystemExit(1)
pathlib.Path('done.txt').write_text(key)
print('NESUS_AI_STATUS: COMPLETE')
""".strip())
    a1 = mod.AccountConfig("bad", env_from={"OPENAI_API_KEY": "K1"})
    a2 = mod.AccountConfig("good", env_from={"OPENAI_API_KEY": "K2"})
    model = mod.ModelProfile("luna", "gpt-5.6-luna", "low", capabilities=["code", "general"])
    general = mod.GeneralConfig(provider_order=["codex"], account_strategy="priority", server_retries=0,
                                timeout_seconds=30, stall_timeout_seconds=10, max_total_attempts=5)
    provider = mod.ProviderConfig("codex", True, 100, ["code"],
        [sys.executable, str(fake), "{prompt}"], {}, [a1, a2], [model])
    config = mod.Config(general, {"codex": provider})
    state = {"providers": {}}; attempts = []
    monkeypatch.setattr(mod, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(mod, "STATE_PATH", tmp_path / "state" / "state.json")
    monkeypatch.setattr(mod, "RUNS_DIR", tmp_path / "state" / "runs")
    monkeypatch.setattr(mod, "LOCKS_DIR", tmp_path / "state" / "locks")
    mod.ensure_dirs()
    result = asyncio.run(mod.run_provider_ladder(config, provider, state,
        {"K1": "bad-key-123", "K2": "good-key-456"}, "create done.txt", tmp_path,
        attempts, tmp_path / "run.jsonl", False, {"code"}, 20))
    assert result is not None and result.success
    assert [a.account for a in attempts] == ["bad", "good"]
    assert (tmp_path / "done.txt").read_text() == "good-key-456"


def test_payload_error_compacts_then_escalates_model(tmp_path, monkeypatch):
    fake = tmp_path / "fake_context_agent.py"
    fake.write_text("""
import os, sys
model = os.environ.get('NESUS_AI_MODEL')
if model == 'gpt-5.6-luna':
    print('HTTP 413 payload too large')
    raise SystemExit(1)
print('NESUS_AI_STATUS: COMPLETE')
""".strip())
    account = mod.AccountConfig("one")
    models = [
        mod.ModelProfile("luna", "gpt-5.6-luna", "low", priority=120, cost_rank=1,
                         min_complexity=0, max_complexity=50, capabilities=["code", "general"]),
        mod.ModelProfile("sol", "gpt-5.6-sol", "high", priority=100, cost_rank=4,
                         min_complexity=40, max_complexity=100,
                         capabilities=["code", "debug", "large-context", "general"], long_context=True),
    ]
    general = mod.GeneralConfig(provider_order=["codex"], server_retries=0,
                                timeout_seconds=30, stall_timeout_seconds=10,
                                max_total_attempts=5, payload_compact_retry=True)
    provider = mod.ProviderConfig("codex", True, 100, ["code"],
        [sys.executable, str(fake), "{prompt}"], {}, [account], models)
    config = mod.Config(general, {"codex": provider})
    state = {"providers": {}}; attempts = []
    monkeypatch.setattr(mod, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(mod, "STATE_PATH", tmp_path / "state" / "state.json")
    monkeypatch.setattr(mod, "RUNS_DIR", tmp_path / "state" / "runs")
    monkeypatch.setattr(mod, "LOCKS_DIR", tmp_path / "state" / "locks")
    mod.ensure_dirs()
    result = asyncio.run(mod.run_provider_ladder(config, provider, state, {}, "fix it", tmp_path,
        attempts, tmp_path / "run.jsonl", False, {"code"}, 20))
    assert result is not None and result.success
    assert [a.model_profile for a in attempts] == ["luna", "luna", "sol"]
    assert [a.compact_mode for a in attempts] == [False, True, False]


def test_local_only_guards_are_injected(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(mod, "RUNS_DIR", tmp_path / "state" / "runs")
    monkeypatch.setattr(mod, "LOCKS_DIR", tmp_path / "state" / "locks")
    account = mod.AccountConfig("one")
    config, provider = make_config([account])
    env = mod.build_runtime_env(config, provider, account, provider.models[0], {}, base_env=dict(os.environ))
    shim_dir = Path(env["PATH"].split(os.pathsep)[0])
    assert env["NESUS_AI_LOCAL_ONLY"] == "1"
    assert (shim_dir / "git").exists()
    assert (shim_dir / "gh").exists()


def test_git_push_and_gh_are_blocked(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "STATE_DIR", tmp_path / "state")
    general = mod.GeneralConfig(provider_order=["codex"], local_only=True,
                                block_git_push=True, block_github_cli=True)
    shim_dir = mod.ensure_local_only_shims(general)
    git_result = __import__("subprocess").run([str(shim_dir / "git"), "push"], capture_output=True, text=True)
    gh_result = __import__("subprocess").run([str(shim_dir / "gh"), "repo", "create"], capture_output=True, text=True)
    assert git_result.returncode == 126
    assert "disabled" in git_result.stderr
    assert gh_result.returncode == 126
    assert "disabled" in gh_result.stderr
