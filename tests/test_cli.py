from __future__ import annotations

import argparse
import builtins
import json
import os
import subprocess
import sys
import urllib.error
from email.message import Message
from io import BytesIO, StringIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV = os.environ.copy()
ENV["PYTHONPATH"] = str(ROOT / "src")
ENV["AGENTICK_HOME"] = str(ROOT / ".test-agentick-home")


def run_agc(*args: str, input_text: str | None = None, env: dict[str, str] | None = None):
    merged = ENV.copy()
    if env:
        merged.update(env)
    return subprocess.run(
        [sys.executable, "-m", "agentick", *args],
        cwd=ROOT,
        env=merged,
        input=input_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def test_help_documents_core_examples_and_redirect_output():
    proc = run_agc("--help")
    assert proc.returncode == 0
    assert "turn reusable AI prompts into tiny developer commands" in proc.stdout
    assert "agc new ./pr-risk.md pr-risk" in proc.stdout
    assert "agc edit pr-risk" in proc.stdout
    assert "agc delete pr-risk --yes" in proc.stdout
    assert "agc release-drafter ./git-log.txt > CHANGELOG-draft.md" in proc.stdout
    assert "agc chats view pr-risk <session-id>" in proc.stdout
    assert "agc chats context pr-risk <session-id>" in proc.stdout
    assert "agc chats compact pr-risk <session-id>" in proc.stdout
    assert "agc chats reset pr-risk <session-id> --yes" in proc.stdout
    assert "agc clean" in proc.stdout
    assert "agc pr-risk ./src/payments/checkout.ts --no-context" in proc.stdout
    assert "context meter" in proc.stdout
    assert "C compaction" in proc.stdout
    assert "Redirected stdout writes raw model output" in proc.stdout


def test_first_run_without_config_enters_setup_guidance():
    proc = run_agc("--no-interactive")
    assert proc.returncode == 2
    assert "Agentick is not ready" in proc.stderr
    assert "Run `agc setup`" in proc.stderr


def test_clean_requires_confirmation_and_preserves_credentials(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    config = home / "config.json"
    config.write_text(json.dumps({
        "default_provider": "openai",
        "providers": {"openai": {"api_key": "test-key", "model": "gpt-4o-mini"}},
    }))
    credentials_dir = home / "credentials"
    credentials_dir.mkdir()
    (credentials_dir / "provider.token").write_text("token")
    for rel in [
        "tasks/review.json",
        "conversations/history/review/session.md",
        "runs/history/review/run.md",
        "routines/review.log",
        "last_prompt.txt",
        "last_agent_trace.json",
    ]:
        path = home / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("runtime data")

    refused = run_agc("clean", "--no-interactive", env={"AGENTICK_HOME": str(home)})
    assert refused.returncode == 2
    assert "without --yes" in refused.stderr
    assert (home / "tasks" / "review.json").exists()

    cleaned = run_agc("clean", "--yes", env={"AGENTICK_HOME": str(home)})
    assert cleaned.returncode == 0, cleaned.stderr
    assert "Cleaned Agentick data" in cleaned.stdout
    assert "Preserved credentials/config" in cleaned.stdout
    assert config.exists()
    assert json.loads(config.read_text())["providers"]["openai"]["api_key"] == "test-key"
    assert (credentials_dir / "provider.token").read_text() == "token"
    assert not (home / "tasks").exists()
    assert not (home / "conversations").exists()
    assert not (home / "runs").exists()
    assert not (home / "routines").exists()
    assert not (home / "last_prompt.txt").exists()


def test_clean_interactive_y_n_confirmation(monkeypatch, tmp_path: Path, capsys):
    from agentick import cli

    home = tmp_path / "home"
    task = home / "tasks" / "review.json"
    task.parent.mkdir(parents=True)
    task.write_text("{}")
    (home / "config.json").write_text(json.dumps({"providers": {}}))
    monkeypatch.setenv("AGENTICK_HOME", str(home))
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(builtins, "input", lambda prompt="": "n")

    cancelled = cli.clean_cmd(argparse.Namespace(yes=False, no_interactive=False))
    out = capsys.readouterr()
    assert cancelled == 0
    assert "Clean cancelled." in out.out
    assert task.exists()

    monkeypatch.setattr(builtins, "input", lambda prompt="": "y")
    cleaned = cli.clean_cmd(argparse.Namespace(yes=False, no_interactive=False))
    out = capsys.readouterr()
    assert cleaned == 0
    assert "Cleaned Agentick data" in out.out
    assert not (home / "tasks").exists()
    assert (home / "config.json").exists()


def test_setup_writes_secure_config_and_prints_usage():
    proc = run_agc(
        "setup",
        "--provider", "openai",
        "--model", "gpt-4o-mini",
        "--reasoning", "low",
        "--api-key", "test-key",
        "--no-interactive",
    )
    assert proc.returncode == 0, proc.stderr
    assert "agc new" in proc.stdout
    assert "agc <task-name>" in proc.stdout
    cfg = ROOT / ".test-agentick-home" / "config.json"
    assert cfg.exists()
    assert oct(cfg.stat().st_mode & 0o777) == "0o600"
    data = json.loads(cfg.read_text())
    assert data["providers"]["openai"]["auth_method"] == "api_key"
    assert data["providers"]["openai"]["api_key"] == "test-key"
    assert data["providers"]["openai"]["model"] == "gpt-4o-mini"
    assert data["providers"]["openai"]["reasoning_effort"] == "low"
    assert data["default_provider"] == "openai"


def test_setup_choice_menu_is_scrollable_and_hermes_style():
    from agentick.cli import render_choice_menu

    menu = render_choice_menu(
        "Select AI provider",
        ["OpenAI", "Gemini", "Grok", "OpenAI Codex OAuth", "Gemini OAuth", "Grok OAuth"],
        selected=3,
        offset=1,
        height=3,
        description="Choose how Agentick should call models.",
    )

    assert "Select AI provider" in menu
    assert "Choose how Agentick should call models." in menu
    assert "→" in menu and "(○)" in menu
    assert "↑/↓" in menu and "ENTER" in menu and "/ search" in menu
    assert "2-4 of 6" in menu


def test_setup_provider_choices_match_hermes_model_provider_rows():
    from agentick.cli import build_provider_choices

    labels = [row[1] for row in build_provider_choices()]

    assert labels[:8] == [
        "OpenAI (API key)",
        "OpenAI Codex (OAuth / ChatGPT/Codex account)",
        "OpenRouter (API key)",
        "Anthropic (API key)",
        "Google Gemini (API key)",
        "Google Gemini OAuth / Code Assist",
        "xAI / Grok (API key)",
        "xAI Grok OAuth (SuperGrok / Premium+)",
    ]
    for expected in [
        "DeepSeek (API key)",
        "Z.AI / GLM (API key)",
        "Kimi / Moonshot (API key)",
        "Alibaba / DashScope (API key)",
        "MiniMax (API key)",
        "Hugging Face (token)",
        "NVIDIA NIM (API key)",
        "Kilo Code (API key)",
        "AI Gateway / Vercel (API key)",
        "OpenCode Zen (API key)",
        "LM Studio (local OpenAI-compatible)",
        "Leave unchanged",
    ]:
        assert expected in labels


def test_openai_models_include_gpt_55_first():
    from agentick.cli import PROVIDERS

    assert PROVIDERS["openai"]["models"][:2] == ["gpt-5.5", "gpt-5.5-mini"]


def test_setup_oauth_provider_slug_maps_without_separate_auth_picker():
    from agentick.cli import resolve_provider_selection

    assert resolve_provider_selection("openai-codex") == ("openai", "oauth")
    assert resolve_provider_selection("google-gemini-cli") == ("gemini", "oauth")
    assert resolve_provider_selection("xai-oauth") == ("grok", "oauth")
    assert resolve_provider_selection("openai-api") == ("openai", "api_key")
    assert resolve_provider_selection("openrouter") == ("openrouter", "api_key")
    assert resolve_provider_selection("anthropic") == ("anthropic", "api_key")
    assert resolve_provider_selection("deepseek") == ("deepseek", "api_key")
    assert resolve_provider_selection("moonshot") == ("kimi-coding", "api_key")


def test_setup_picker_search_uses_hermes_fuzzy_subsequence_matching():
    from agentick.cli import _filter_options

    options = [
        "OpenAI (API key)",
        "OpenAI Codex (OAuth / ChatGPT/Codex account)",
        "Google Gemini OAuth / Code Assist",
    ]

    assert _filter_options(options, "op cod") == [1]
    assert _filter_options(options, "gg ca") == [2]


def test_setup_openai_oauth_language_uses_browser_or_device_code_copy():
    from agentick.cli import PROVIDERS, oauth_setup_guidance

    guidance = oauth_setup_guidance(PROVIDERS["openai"], "AGC_OPENAI_OAUTH_TOKEN")

    assert "Agentick will open your browser or show a device code. You do not need to paste a token." in guidance
    assert "Sign in with OpenAI" not in guidance
    assert "OAuth access token" not in guidance


def test_read_codex_access_token_from_auth_file(tmp_path: Path):
    from agentick.cli import read_codex_access_token

    auth_file = tmp_path / "auth.json"
    auth_file.write_text(json.dumps({"tokens": {"access_token": "codex-token"}}), encoding="utf-8")

    assert read_codex_access_token(auth_file) == "codex-token"


def test_openai_codex_device_login_uses_current_codex_oauth_client_id():
    from agentick import cli

    assert cli.CODEX_OAUTH_CLIENT_ID == "app_EMoamEEZ73f0CkXaXp7hrann"


def test_openai_codex_device_login_opens_browser_and_exchanges_token(monkeypatch):
    from agentick import cli

    calls: list[tuple[str, dict[str, object], bool]] = []

    def fake_json_post(url: str, payload: dict[str, object], *, form: bool = False, timeout: float = 15.0):
        del timeout
        calls.append((url, payload, form))
        if url.endswith("/api/accounts/deviceauth/usercode"):
            return {"user_code": "ABCD-EFGH", "device_auth_id": "device-1", "interval": 3}
        if url.endswith("/api/accounts/deviceauth/token"):
            return {"authorization_code": "auth-code", "code_verifier": "verifier"}
        if url == cli.CODEX_OAUTH_TOKEN_URL:
            return {"access_token": "oauth-access-token"}
        raise AssertionError(f"unexpected URL: {url}")

    opened: list[str] = []
    monkeypatch.setattr(cli, "_json_post", fake_json_post)
    monkeypatch.setattr(cli.webbrowser, "open", lambda url: opened.append(url) or True)
    monkeypatch.setattr(cli.time, "sleep", lambda _seconds: None)

    token = cli.openai_codex_device_login(open_browser=True)

    assert token == "oauth-access-token"
    assert opened == ["https://auth.openai.com/codex/device"]
    assert calls[0][0] == "https://auth.openai.com/api/accounts/deviceauth/usercode"
    assert calls[0][1] == {"client_id": cli.CODEX_OAUTH_CLIENT_ID}
    assert calls[1][0] == "https://auth.openai.com/api/accounts/deviceauth/token"
    assert calls[2][0] == cli.CODEX_OAUTH_TOKEN_URL
    assert calls[2][2] is True


def test_openai_codex_device_login_treats_401_poll_as_pending(monkeypatch):
    from agentick import cli

    attempts = 0

    def fake_json_post(url: str, payload: dict[str, object], *, form: bool = False, timeout: float = 15.0):
        nonlocal attempts
        del payload, form, timeout
        if url.endswith("/api/accounts/deviceauth/usercode"):
            return {"user_code": "ABCD-EFGH", "device_auth_id": "device-1", "interval": 3}
        if url.endswith("/api/accounts/deviceauth/token"):
            attempts += 1
            if attempts == 1:
                raise urllib.error.HTTPError(url, 401, "Unauthorized", Message(), BytesIO(b'{"error":"pending"}'))
            return {"authorization_code": "auth-code", "code_verifier": "verifier"}
        if url == cli.CODEX_OAUTH_TOKEN_URL:
            return {"access_token": "oauth-access-token"}
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(cli, "_json_post", fake_json_post)
    monkeypatch.setattr(cli.time, "sleep", lambda _seconds: None)

    assert cli.openai_codex_device_login(open_browser=False) == "oauth-access-token"
    assert attempts == 2


def test_obtain_openai_oauth_defaults_to_fresh_browser_login_when_codex_auth_exists(monkeypatch):
    from agentick import cli

    monkeypatch.setattr(cli, "read_codex_access_token", lambda: "existing-token")
    monkeypatch.setattr("builtins.input", lambda _prompt: "")
    launched: list[bool] = []
    monkeypatch.setattr(cli, "openai_codex_device_login", lambda *, open_browser: launched.append(open_browser) or "fresh-token")

    assert cli.obtain_openai_oauth_token("AGC_OPENAI_OAUTH_TOKEN") == "fresh-token"
    assert launched == [True]


def test_obtain_openai_oauth_can_import_existing_codex_auth(monkeypatch):
    from agentick import cli

    monkeypatch.setattr(cli, "read_codex_access_token", lambda: "existing-token")
    monkeypatch.setattr("builtins.input", lambda _prompt: "y")
    monkeypatch.setattr(cli, "openai_codex_device_login", lambda *, open_browser: (_ for _ in ()).throw(AssertionError("should not launch")))

    assert cli.obtain_openai_oauth_token("AGC_OPENAI_OAUTH_TOKEN") == "existing-token"


def test_setup_openai_oauth_path_saves_oauth_metadata_without_api_key():
    proc = run_agc(
        "setup",
        "--provider", "openai",
        "--auth", "oauth",
        "--model", "gpt-5.4",
        "--reasoning", "medium",
        "--oauth-token", "oauth-test-token",
        "--no-interactive",
    )
    assert proc.returncode == 0, proc.stderr
    data = json.loads((ROOT / ".test-agentick-home" / "config.json").read_text())
    saved = data["providers"]["openai"]
    assert saved["auth_method"] == "oauth"
    assert saved["oauth_provider"] == "openai-codex"
    assert saved["access_token"] == "oauth-test-token"
    assert "api_key" not in saved
    assert "OAuth" in proc.stdout


def test_noninteractive_setup_requires_oauth_token_for_oauth_auth():
    proc = run_agc(
        "setup",
        "--provider", "grok",
        "--auth", "oauth",
        "--model", "grok-4.3",
        "--reasoning", "low",
        "--no-interactive",
    )
    assert proc.returncode == 2
    assert "Missing OAuth token" in proc.stderr


def test_provider_key_reads_oauth_access_token_and_env_override(monkeypatch):
    from agentick.cli import provider_key

    config = {
        "providers": {
            "grok": {
                "auth_method": "oauth",
                "access_token": "stored-token",
            }
        }
    }
    assert provider_key(config, "grok") == "stored-token"
    monkeypatch.setenv("AGC_GROK_OAUTH_TOKEN", "env-token")
    assert provider_key(config, "grok") == "env-token"


def test_provider_key_does_not_mix_openai_api_key_into_oauth(monkeypatch):
    from agentick.cli import provider_key

    config = {
        "providers": {
            "openai": {
                "auth_method": "oauth",
                "access_token": "oauth-token",
            }
        }
    }
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    assert provider_key(config, "openai") == "oauth-token"
    monkeypatch.setenv("AGC_OPENAI_OAUTH_TOKEN", "oauth-env-token")
    assert provider_key(config, "openai") == "oauth-env-token"


def test_openai_oauth_calls_codex_responses_endpoint(monkeypatch):
    from agentick import cli

    captured = {}

    def fake_urlopen_sse_events(request, *, timeout=120.0):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        captured["payload"] = json.loads(request.data.decode())
        captured["timeout"] = timeout
        return [
            {"type": "response.output_text.delta", "delta": "answer"},
            {"type": "response.completed", "response": {"usage": {"input_tokens": 3, "output_tokens": 2, "total_tokens": 5}}},
        ]

    monkeypatch.setattr(cli, "_urlopen_sse_events", fake_urlopen_sse_events)
    cli.reset_ai_usage()
    config = {
        "providers": {
            "openai": {
                "auth_method": "oauth",
                "access_token": "oauth-token",
                "model": "gpt-5.5",
                "reasoning_effort": "minimal",
            }
        }
    }
    task = {"provider": "openai", "system_prompt": "Be brief."}

    assert cli.call_openai_compatible("openai", task, config, "hello") == "answer"
    assert captured["url"] == "https://chatgpt.com/backend-api/codex/responses"
    assert captured["headers"]["Authorization"] == "Bearer oauth-token"
    assert captured["headers"]["Originator"] == "codex_cli_rs"
    assert captured["payload"]["instructions"] == "Be brief."
    assert captured["payload"]["input"] == [{"role": "user", "content": "hello"}]
    assert captured["payload"]["reasoning"]["effort"] == "low"
    assert captured["payload"]["stream"] is True


def test_provider_key_reads_all_provider_env_aliases(monkeypatch):
    from agentick.cli import provider_key

    config = {"providers": {"anthropic": {"auth_method": "api_key", "api_key": "stored-key"}}}
    assert provider_key(config, "anthropic") == "stored-key"
    monkeypatch.setenv("ANTHROPIC_TOKEN", "anthropic-env-token")
    assert provider_key(config, "anthropic") == "anthropic-env-token"


def test_provider_readiness_requires_config_key_and_internet(monkeypatch):
    from agentick import cli

    assert "not been set up" in cli.provider_readiness_error(None, check_network=False)
    assert "No AI provider" in cli.provider_readiness_error({"providers": {}}, check_network=False)
    assert "Missing API key" in cli.provider_readiness_error({
        "default_provider": "openai",
        "providers": {"openai": {"auth_method": "api_key"}},
    }, check_network=False)

    monkeypatch.setattr(cli, "internet_connected", lambda: (False, "offline"))
    assert "Internet check failed" in cli.provider_readiness_error({
        "default_provider": "openai",
        "providers": {"openai": {"auth_method": "api_key", "api_key": "test-key"}},
    })

    monkeypatch.setattr(cli, "internet_connected", lambda: (True, ""))
    assert cli.provider_readiness_error({
        "default_provider": "openai",
        "providers": {"openai": {"auth_method": "api_key", "api_key": "test-key"}},
    }) == ""


def test_new_interactive_ctrl_c_exits_cleanly(monkeypatch, capsys):
    from argparse import Namespace
    from agentick import cli

    monkeypatch.setattr(cli, "load_config", lambda: {
        "default_provider": "openai",
        "providers": {"openai": {"auth_method": "api_key", "api_key": "test-key"}},
    })
    monkeypatch.setattr(cli, "choose", lambda *args, **kwargs: "one-line")
    monkeypatch.setattr("builtins.input", lambda _prompt="": (_ for _ in ()).throw(KeyboardInterrupt()))

    code = cli.new_cmd(Namespace(
        prompt_file=None,
        no_interactive=False,
        provider=None,
        reasoning=None,
        name=None,
        agent=False,
        model=None,
    ))

    captured = capsys.readouterr()
    assert code == 130
    assert "Cancelled." in captured.err
    assert "Traceback" not in captured.err


def test_new_rejects_non_markdown_or_text_prompt_files(tmp_path: Path):
    bad = tmp_path / "prompt.py"
    bad.write_text("print('no')")
    proc = run_agc("new", str(bad), "bad-task", "--no-interactive")
    assert proc.returncode == 2
    assert "Agentick is not ready" in proc.stderr
    assert "Run `agc setup`" in proc.stderr


def test_new_from_markdown_creates_named_task_with_provider_and_reasoning(tmp_path: Path):
    home = ROOT / ".test-agentick-home"
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.json").write_text(json.dumps({
        "default_provider": "openai",
        "providers": {"openai": {"auth_method": "api_key", "api_key": "test-key", "model": "gpt-4o-mini"}},
    }))
    prompt = tmp_path / "say-hello.md"
    prompt.write_text("---\nsystem: Be concise.\n---\nHello, AI")
    proc = run_agc(
        "new", str(prompt), "say-hello",
        "--provider", "openai",
        "--reasoning", "low",
        "--no-interactive",
    )
    assert proc.returncode == 0, proc.stderr
    assert "saved" in proc.stdout.lower()
    task = ROOT / ".test-agentick-home" / "tasks" / "say-hello.json"
    data = json.loads(task.read_text())
    assert data["name"] == "say-hello"
    assert data["system_prompt"] == "Be concise."
    assert data["user_prompt"] == "Hello, AI"
    assert data["provider"] == "openai"
    assert data["reasoning_effort"] == "low"


def test_new_accepts_task_specific_model_flag(tmp_path: Path):
    home = ROOT / ".test-agentick-home"
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.json").write_text(json.dumps({
        "default_provider": "openai",
        "providers": {"openai": {"auth_method": "api_key", "api_key": "test-key", "model": "gpt-4o-mini"}},
    }))
    prompt = tmp_path / "review.md"
    prompt.write_text("Review {{file:0}}")

    proc = run_agc("new", str(prompt), "review-fast", "--provider", "openai", "--model", "gpt-4o", "--no-interactive")

    assert proc.returncode == 0, proc.stderr
    data = json.loads((home / "tasks" / "review-fast.json").read_text())
    assert data["model"] == "gpt-4o"


def test_new_interactive_model_picker_can_select_task_model(monkeypatch):
    from agentick import cli

    seen: dict[str, object] = {}

    def fake_choose(prompt: str, options: list[str], default: str | None = None, description: str | None = None) -> str:
        seen["prompt"] = prompt
        seen["options"] = options
        seen["default"] = default
        seen["description"] = description
        return "gpt-4o"

    monkeypatch.setattr(cli, "choose", fake_choose)
    picked = cli.choose_task_model(
        "openai",
        {"providers": {"openai": {"model": "gpt-4o-mini"}}},
        explicit_model=None,
        parsed_model=None,
        no_interactive=False,
    )

    assert picked == "gpt-4o"
    options = seen["options"]
    assert isinstance(options, list)
    assert seen["prompt"] == "Model for this task"
    assert options[0] == "Provider default (gpt-4o-mini)"
    assert "gpt-4o" in options


def test_new_interactive_model_picker_can_keep_provider_default(monkeypatch):
    from agentick import cli

    monkeypatch.setattr(cli, "choose", lambda *_args, **_kwargs: "Provider default (gpt-4o-mini)")

    assert cli.choose_task_model(
        "openai",
        {"providers": {"openai": {"model": "gpt-4o-mini"}}},
        explicit_model=None,
        parsed_model=None,
        no_interactive=False,
    ) is None


def test_edit_replaces_existing_task_from_prompt_file(tmp_path: Path):
    home = ROOT / ".test-agentick-home"
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.json").write_text(json.dumps({
        "default_provider": "openai",
        "providers": {"openai": {"auth_method": "api_key", "api_key": "test-key", "model": "gpt-4o-mini", "reasoning_effort": "low"}},
    }))
    task_dir = home / "tasks"
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "review.json").write_text(json.dumps({
        "name": "review",
        "provider": "openai",
        "system_prompt": "Old system",
        "user_prompt": "Old prompt",
        "model": "gpt-4o",
        "reasoning_effort": "high",
    }))
    prompt = tmp_path / "review.md"
    prompt.write_text("---\nsystem: New system\nagent: true\n---\nNew prompt {{arg:0}}")

    proc = run_agc("edit", "review", str(prompt), "--model", "gpt-4o-mini", "--reasoning", "low", "--no-interactive")

    assert proc.returncode == 0, proc.stderr
    assert "Task updated" in proc.stdout
    data = json.loads((task_dir / "review.json").read_text())
    assert data["name"] == "review"
    assert data["system_prompt"] == "New system"
    assert data["user_prompt"] == "New prompt {{arg:0}}"
    assert data["model"] == "gpt-4o-mini"
    assert data["reasoning_effort"] == "low"
    assert data["agent"] is True


def test_edit_non_interactive_requires_prompt_file():
    home = ROOT / ".test-agentick-home"
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.json").write_text(json.dumps({
        "default_provider": "openai",
        "providers": {"openai": {"auth_method": "api_key", "api_key": "test-key", "model": "gpt-4o-mini"}},
    }))
    task_dir = home / "tasks"
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "review.json").write_text(json.dumps({
        "name": "review",
        "provider": "openai",
        "user_prompt": "Existing",
    }))

    proc = run_agc("edit", "review", "--no-interactive")

    assert proc.returncode == 2
    assert "edit requires a prompt file" in proc.stderr


def test_delete_task_requires_yes_in_non_interactive_mode():
    home = ROOT / ".test-agentick-home"
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.json").write_text(json.dumps({
        "default_provider": "openai",
        "providers": {"openai": {"auth_method": "api_key", "api_key": "test-key", "model": "gpt-4o-mini"}},
    }))
    task_dir = home / "tasks"
    task_dir.mkdir(parents=True, exist_ok=True)
    task_file = task_dir / "review.json"
    task_file.write_text(json.dumps({"name": "review", "provider": "openai", "user_prompt": "Existing"}))

    proc = run_agc("delete", "review", "--no-interactive")

    assert proc.returncode == 2
    assert "without --yes" in proc.stderr
    assert task_file.exists()


def test_delete_task_removes_saved_task_with_yes():
    home = ROOT / ".test-agentick-home"
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.json").write_text(json.dumps({
        "default_provider": "openai",
        "providers": {"openai": {"auth_method": "api_key", "api_key": "test-key", "model": "gpt-4o-mini"}},
    }))
    task_dir = home / "tasks"
    task_dir.mkdir(parents=True, exist_ok=True)
    task_file = task_dir / "review.json"
    task_file.write_text(json.dumps({"name": "review", "provider": "openai", "user_prompt": "Existing"}))

    proc = run_agc("delete", "review", "--yes", "--no-interactive")

    assert proc.returncode == 0, proc.stderr
    assert "Task deleted" in proc.stdout
    assert not task_file.exists()


def test_delete_unknown_task_returns_clear_error():
    home = ROOT / ".test-agentick-home"
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.json").write_text(json.dumps({
        "default_provider": "openai",
        "providers": {"openai": {"auth_method": "api_key", "api_key": "test-key", "model": "gpt-4o-mini"}},
    }))
    (home / "tasks").mkdir(parents=True, exist_ok=True)

    proc = run_agc("delete", "missing", "--yes", "--no-interactive")

    assert proc.returncode == 2
    assert "Unknown task: missing" in proc.stderr


def test_new_without_task_model_or_reasoning_defers_to_runtime_defaults(tmp_path: Path):
    home = ROOT / ".test-agentick-home"
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.json").write_text(json.dumps({
        "default_provider": "openai",
        "providers": {"openai": {"api_key": "test-key", "model": "gpt-4o-mini", "reasoning_effort": "high"}},
    }))
    prompt = tmp_path / "defaulted.md"
    prompt.write_text("Use defaults please")
    proc = run_agc("new", str(prompt), "defaulted", "--no-interactive")
    assert proc.returncode == 0, proc.stderr
    data = json.loads((home / "tasks" / "defaulted.json").read_text())
    assert "model" not in data
    assert "reasoning_effort" not in data


def test_runtime_applies_provider_default_model_and_reasoning_when_task_omits_them():
    from agentick.cli import resolved_model, resolved_reasoning_effort

    config = {
        "default_provider": "openai",
        "providers": {"openai": {"model": "gpt-4o-mini", "reasoning_effort": "high"}},
    }
    task = {"provider": "openai", "user_prompt": "Hello"}

    assert resolved_model(task, config, "openai") == "gpt-4o-mini"
    assert resolved_reasoning_effort(task, config, "openai") == "high"


def test_task_specific_model_and_reasoning_override_provider_defaults():
    from agentick.cli import resolved_model, resolved_reasoning_effort

    config = {
        "default_provider": "openai",
        "providers": {"openai": {"model": "gpt-4o-mini", "reasoning_effort": "low"}},
    }
    task = {"provider": "openai", "model": "gpt-4o", "reasoning_effort": "medium", "user_prompt": "Hello"}

    assert resolved_model(task, config, "openai") == "gpt-4o"
    assert resolved_reasoning_effort(task, config, "openai") == "medium"


def test_openai_chat_completions_omits_reasoning_for_gpt_4o_mini(monkeypatch):
    from agentick import cli

    captured: dict[str, object] = {}

    def fake_urlopen_json(request, *, timeout: float = 120):
        del timeout
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return {"choices": [{"message": {"content": "PONG"}}]}

    monkeypatch.setattr(cli, "_urlopen_json", fake_urlopen_json)
    response = cli.call_openai_compatible(
        "openai",
        {"provider": "openai", "model": "gpt-4o-mini", "reasoning_effort": "minimal", "user_prompt": "Hi"},
        {"providers": {"openai": {"auth_method": "api_key", "api_key": "test-key"}}},
        "Hi",
    )

    assert response == "PONG"
    assert captured["payload"] == {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": ""},
            {"role": "user", "content": "Hi"},
        ],
    }


def test_non_openai_provider_uses_openai_compatible_endpoint(monkeypatch):
    from agentick import cli

    captured: dict[str, object] = {}

    def fake_urlopen_json(request, *, timeout: float = 120):
        del timeout
        captured["url"] = request.full_url
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        captured["auth"] = request.headers.get("Authorization")
        return {"choices": [{"message": {"content": "DS"}}], "usage": {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3}}

    monkeypatch.setattr(cli, "_urlopen_json", fake_urlopen_json)
    response = cli.call_ai(
        {"provider": "deepseek", "model": "deepseek-chat", "reasoning_effort": "medium", "user_prompt": "Hi"},
        {"providers": {"deepseek": {"auth_method": "api_key", "api_key": "deep-key"}}},
        "Hi",
    )

    assert response == "DS"
    assert captured["url"] == "https://api.deepseek.com/v1/chat/completions"
    assert captured["auth"] == "Bearer deep-key"
    assert captured["payload"] == {
        "model": "deepseek-chat",
        "messages": [{"role": "system", "content": ""}, {"role": "user", "content": "Hi"}],
    }


def test_anthropic_provider_uses_messages_api(monkeypatch):
    from agentick import cli

    captured: dict[str, object] = {}

    def fake_urlopen_json(request, *, timeout: float = 120):
        del timeout
        captured["url"] = request.full_url
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        captured["api_key"] = request.headers.get("X-api-key")
        captured["version"] = request.headers.get("Anthropic-version")
        return {"content": [{"type": "text", "text": "CLAUDE"}], "usage": {"input_tokens": 4, "output_tokens": 2}}

    monkeypatch.setattr(cli, "_urlopen_json", fake_urlopen_json)
    response = cli.call_ai(
        {"provider": "anthropic", "model": "claude-sonnet-4-6", "system_prompt": "Be terse", "user_prompt": "Hi"},
        {"providers": {"anthropic": {"auth_method": "api_key", "api_key": "anthropic-key"}}},
        "Hi",
    )

    assert response == "CLAUDE"
    assert captured["url"] == "https://api.anthropic.com/v1/messages"
    assert captured["api_key"] == "anthropic-key"
    assert captured["version"] == "2023-06-01"
    assert captured["payload"] == {
        "model": "claude-sonnet-4-6",
        "max_tokens": 4096,
        "messages": [{"role": "user", "content": "Hi"}],
        "system": "Be terse",
    }


class TtyStringIO(StringIO):
    def isatty(self) -> bool:
        return True


def test_loader_shows_tty_progress_and_success(monkeypatch):
    from agentick import cli

    stderr = TtyStringIO()
    monkeypatch.setattr(cli.sys, "stderr", stderr)
    monkeypatch.delenv("AGC_MOCK_RESPONSE", raising=False)
    monkeypatch.delenv("AGC_NO_LOADER", raising=False)

    assert cli.with_loader("Running demo…", lambda: "done") == "done"

    output = stderr.getvalue()
    assert "Running demo…" in output
    assert "✓" in output


def test_interactive_output_prints_raw_markdown_when_redirected(monkeypatch):
    from agentick import cli

    stdout = StringIO()
    monkeypatch.setattr(cli.sys, "stdout", stdout)

    cli.interactive_output("# Title\n\n```python\nprint('hi')\n```")

    assert stdout.getvalue() == "# Title\n\n```python\nprint('hi')\n```\n"


def test_response_line_numbers_use_plain_numeric_prefixes():
    from agentick.cli import response_with_line_numbers

    assert response_with_line_numbers("Example\nEXample") == "1 Example\n2 EXample"


def test_render_numbered_response_preserves_markdown_line_breaks():
    from agentick import cli

    sample = """In Neovim/netrw:

```vim
let g:netrw_browsex_viewer = "open"
```

Lua:

```lua
vim.g.netrw_browsex_viewer = "open"
```

Then pressing gx on a PDF/path opens it with macOS open.

Or directly:

```vim
:!open %
```"""

    rendered = cli.strip_ansi(cli.render_numbered_response_ansi(sample))
    lines = rendered.splitlines()

    assert lines[0] == " 1 In Neovim/netrw:"
    assert lines[1] == " 2 "
    assert lines[3] == ' 4  let g:netrw_browsex_viewer = "open"'
    assert lines[6] == " 7 Lua:"
    assert lines[9] == '10  vim.g.netrw_browsex_viewer = "open"'
    assert lines[12] == "13 Then pressing gx on a PDF/path opens it with macOS open."
    assert lines[17] == "18  :!open %"
    assert not any("1 In Neovim/netrw: 2" in line for line in lines)


def test_reply_prompt_and_hotkey_overlay_do_not_show_citation_hint(monkeypatch):
    from agentick import cli

    messages = [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "world"}]
    monkeypatch.setenv("AGC_CONTEXT_LIMIT_TOKENS", "1000")

    overlay = cli.hotkey_overlay_text(messages, "openai", "gpt-4o-mini")
    assert cli.REPLY_PROMPT == "Reply: "
    assert "(" not in cli.REPLY_PROMPT and "@cite" not in cli.REPLY_PROMPT
    assert "citation" not in overlay.lower()
    assert "@cite" not in overlay


def test_reply_mode_slash_commands_cancel_or_open_visual():
    from agentick import cli

    assert cli.resolve_reply_command("/exit") == ""
    assert cli.resolve_reply_command(" /exit ") == ""
    assert cli.resolve_reply_command("/visual") == cli.REPLY_VISUAL_ACTION
    assert cli.resolve_reply_command("regular reply") is None

    slash = cli.strip_ansi(cli.render_reply_command_suggestions("/"))
    assert "/exit" in slash
    assert "/visual" in slash
    assert "return to the response viewer" in slash
    assert "multiline reply" in slash

    assert cli.complete_reply_command("/e") == "/exit"
    assert cli.complete_reply_command("/v") == "/visual"
    assert cli.complete_reply_command("/unknown") == "/unknown"
    assert cli._reply_command_completer("/e", 0) == "/exit "
    assert cli._reply_command_completer("/e", 1) is None
    hint = cli.strip_ansi(cli.reply_mode_hint())
    assert "arrows move cursor" in hint
    assert "Tab completes slash commands" in hint


def test_reply_prompt_uses_terminal_line_editor_for_arrow_cursor_editing():
    if os.name == "nt":
        return
    import pty
    import select
    import signal
    import time

    code = (
        "import sys; sys.path.insert(0, 'src'); "
        "from agentick.cli import _prompt_line; "
        "reply = _prompt_line('Reply: ', previous_response='previous'); "
        "print('RESULT:' + reply)"
    )
    master, slave = pty.openpty()
    proc = subprocess.Popen(
        [sys.executable, "-c", code],
        cwd=ROOT,
        stdin=slave,
        stdout=slave,
        stderr=slave,
    )
    os.close(slave)
    output = b""
    sent = False
    deadline = time.time() + 8
    try:
        while time.time() < deadline:
            readable, _, _ = select.select([master], [], [], 0.1)
            if readable:
                chunk = os.read(master, 4096)
                if not chunk:
                    break
                output += chunk
                if b"Reply: " in output and not sent:
                    # abc, left, left, X, enter => aXbc only if cursor movement works.
                    os.write(master, b"abc\x1b[D\x1b[DX\r")
                    sent = True
            if proc.poll() is not None:
                break
        if proc.poll() is None:
            proc.send_signal(signal.SIGINT)
            proc.wait(timeout=2)
    finally:
        os.close(master)

    assert sent
    assert proc.returncode == 0
    assert b"RESULT:aXbc" in output


def test_conversation_footer_shows_top_hotkeys_and_overlay_lists_all_keys(monkeypatch):
    from agentick import cli

    messages = [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "world"}]
    monkeypatch.setenv("AGC_CONTEXT_LIMIT_TOKENS", "1000")

    footer = cli.conversation_footer(messages, "openai", "gpt-4o-mini", 0, 10, 20, color=False)
    assert "R reply" in footer
    assert "C compact" in footer
    assert "q quit" in footer
    assert "? all keys" in footer
    assert "E editor" not in footer

    overlay = cli.hotkey_overlay_text(messages, "openai", "gpt-4o-mini")
    assert "Agentick hotkeys" in overlay
    assert "Press ? or q to close" in overlay
    assert "E / V" in overlay
    assert "Ctrl-S" in overlay
    assert "Space / PgDn" in overlay


def test_compact_chat_messages_summarizes_older_context_and_keeps_recent(monkeypatch):
    from agentick import cli

    captured = {}

    def fake_call_ai_messages(task, cfg, messages):
        captured["task"] = task
        captured["prompt"] = messages[0]["content"]
        return "## Goal\nKeep the useful bits."

    monkeypatch.setattr(cli, "call_ai_messages", fake_call_ai_messages)
    original = [
        {"role": "system", "content": "Be useful."},
        {"role": "user", "content": "old user"},
        {"role": "assistant", "content": "old assistant"},
        {"role": "user", "content": "recent user"},
        {"role": "assistant", "content": "recent assistant"},
    ]

    compacted = cli.compact_chat_messages({"reasoning_effort": "high"}, {"providers": {}}, original)

    assert captured["task"]["reasoning_effort"] == "minimal"
    assert "OLDER_MESSAGES JSON" in captured["prompt"]
    assert "old user" in captured["prompt"]
    assert "RECENT_MESSAGES KEPT VERBATIM" in captured["prompt"]
    assert compacted[0] == original[0]
    assert "Compacted conversation summary for continuity" in compacted[1]["content"]
    assert compacted[-2:] == original[-2:]


def test_cite_ranges_extract_previous_response_chunks():
    from agentick.cli import CiteRange, build_cited_reply, extract_citation_chunk, parse_cite_ranges

    response = "abcdef\nsecond line\nthird"
    cite = CiteRange("@cite:L1C2..L2C6", 1, 2, 2, 6)

    assert extract_citation_chunk(response, cite) == "bcdef\nsecond"
    parsed = parse_cite_ranges("why @cite:L1C2..L2C6 ?")
    assert parsed[0].start_line == 1
    assert parsed[0].start_col == 2
    cited = build_cited_reply("why @cite:L1C2..L2C6 ?", response)
    assert "Citation @cite:L1C2..L2C6" in cited
    assert "bcdef\nsecond" in cited


def test_save_conversation_writes_markdown_and_json(monkeypatch, tmp_path: Path):
    from agentick import cli

    monkeypatch.setenv("AGENTICK_HOME", str(tmp_path))
    out = cli.save_conversation("debug-thread", [
        {"role": "user", "content": "What failed?"},
        {"role": "assistant", "content": "The webhook returned 500."},
    ])

    assert out == tmp_path / "conversations" / "debug-thread.md"
    assert "# Agentick conversation: debug-thread" in out.read_text(encoding="utf-8")
    saved_json = json.loads((tmp_path / "conversations" / "debug-thread.json").read_text(encoding="utf-8"))
    assert saved_json["messages"][1]["content"] == "The webhook returned 500."


def test_interactive_output_pages_rendered_markdown_for_tty(monkeypatch):
    from agentick import cli

    stdout = TtyStringIO()
    paged: list[str] = []
    monkeypatch.setattr(cli.sys, "stdout", stdout)
    monkeypatch.setattr(cli, "page_response", lambda rendered: paged.append(rendered) or True)

    cli.interactive_output("| A | B |\n| - | - |\n| 1 | 2 |\n\n```python\nprint('hi')\n```")

    assert stdout.getvalue() == ""
    assert paged
    assert "print" in paged[0]
    assert "\x1b[" in paged[0]


def test_run_task_expands_arguments_and_file_line_slices(tmp_path: Path):
    code = tmp_path / "index.js"
    code.write_text("const store = new Map();\nstore.set(\"john\", \"doe\");\n")
    home = ROOT / ".test-agentick-home"
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.json").write_text(json.dumps({
        "default_provider": "openai",
        "providers": {"openai": {"api_key": "test-key", "model": "gpt-4o-mini"}},
    }))
    task_dir = home / "tasks"
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "js-explain.json").write_text(json.dumps({
        "name": "js-explain",
        "provider": "openai",
        "model": "gpt-4o-mini",
        "reasoning_effort": "medium",
        "system_prompt": "You are expert in explaining things",
        "user_prompt": "Explain the relevant programming concepts used here:\n{{arg:0}}\n\nCode:\n{{file:0}}",
    }))
    proc = run_agc("js-explain", f"{code}:L1..L2", "--headless", env={"AGC_MOCK_RESPONSE": "Map stores key-value pairs."})
    assert proc.returncode == 0, proc.stderr
    assert "Map stores key-value pairs." in proc.stdout
    rendered = ROOT / ".test-agentick-home" / "last_prompt.txt"
    assert "const store = new Map();" in rendered.read_text()
    assert "store.set" in rendered.read_text()


def test_edit_args_opens_editor_for_long_parameter_and_uses_description(tmp_path: Path):
    home = tmp_path / "home"
    editor = tmp_path / "editor.sh"
    editor.write_text("""#!/bin/sh
cat > \"$1\" <<'EOF'
# Parameter 1: production incident notes
# Do not edit or delete this heading. Agentick uses it to scrape the argument.
# Write/paste the full argument below the marker, then save and quit.
--- AGENTICK ARGUMENT VALUE BELOW ---
Line one of a long paragraph.
Line two includes details.
EOF
""")
    editor.chmod(0o700)
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.json").write_text(json.dumps({
        "default_provider": "openai",
        "providers": {"openai": {"api_key": "test-key", "model": "gpt-4o-mini"}},
    }))
    task_dir = home / "tasks"
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "incident.json").write_text(json.dumps({
        "name": "incident",
        "provider": "openai",
        "user_prompt": "Turn this into a handoff:\n{{arg:0}}",
        "parameter_descriptions": ["production incident notes"],
    }))

    proc = run_agc(
        "incident",
        "--edit-args",
        "--headless",
        env={"AGENTICK_HOME": str(home), "EDITOR": str(editor), "AGC_MOCK_RESPONSE": "handoff"},
    )
    assert proc.returncode == 0, proc.stderr
    prompt = (home / "last_prompt.txt").read_text()
    assert "Line one of a long paragraph." in prompt
    assert "Line two includes details." in prompt
    assert "# Parameter 1" not in prompt


def test_prompt_files_round_trip_parameter_descriptions(tmp_path: Path):
    from agentick import cli

    prompt_file = tmp_path / "prompt.md"
    prompt_file.write_text("""---
system: "Be direct"
param_0: "incident notes pasted from Slack"
---
Summarize {{arg:0}}
""")

    parsed = cli.parse_prompt_file(prompt_file)
    assert parsed["parameter_descriptions"] == ["incident notes pasted from Slack"]
    task = cli.build_task_from_parsed("incident", "openai", parsed)
    rendered = cli.task_to_prompt_markdown(task)
    assert 'param_0: "incident notes pasted from Slack"' in rendered


def test_editor_reply_template_parses_multiline_reply():
    from agentick import cli

    initial = cli.reply_editor_initial("First line\nSecond line")

    assert "@cite:L1C1..L2C5" in initial
    assert "#   1 First line" in initial
    reply = cli.parse_reply_editor_value(initial + "Please expand this.\nWith details.\n")
    assert reply == "Please expand this.\nWith details."


def test_task_runs_save_execution_history_and_history_view(tmp_path: Path):
    home = tmp_path / "home"
    env = {
        "AGENTICK_HOME": str(home),
        "AGC_MOCK_RESPONSE": "first answer",
        "AGC_MOCK_USAGE_JSON": json.dumps({"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18}),
    }
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.json").write_text(json.dumps({
        "default_provider": "openai",
        "providers": {"openai": {"api_key": "test-key", "model": "gpt-4o-mini"}},
    }))
    task_dir = home / "tasks"
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "js-explain.json").write_text(json.dumps({
        "name": "js-explain",
        "provider": "openai",
        "user_prompt": "Explain {{arg:0}}",
    }))

    first = run_agc("js-explain", "Map", "--headless", env=env)
    assert first.returncode == 0, first.stderr
    second = run_agc("js-explain", "Set", "--headless", env={**env, "AGC_MOCK_RESPONSE": "second answer"})
    assert second.returncode == 0, second.stderr

    latest = (home / "runs" / "js-explain.md").read_text()
    assert "second answer" in latest
    assert "## Usage" in latest
    assert "Total tokens: 18" in latest
    assert "| 1 | openai | gpt-4o-mini | medium | 11 | 7 | 18 |" in latest
    history_files = sorted((home / "runs" / "history" / "js-explain").glob("*.md"))
    assert len(history_files) == 2
    assert any("first answer" in path.read_text() for path in history_files)
    assert any("second answer" in path.read_text() for path in history_files)

    listed = run_agc("history", "js-explain", env={"AGENTICK_HOME": str(home)})
    assert listed.returncode == 0, listed.stderr
    assert "Execution history" in listed.stdout
    assert "js-explain" in listed.stdout
    run_id = history_files[0].stem
    viewed = run_agc("history", "view", "js-explain", run_id, "--headless", env={"AGENTICK_HOME": str(home)})
    assert viewed.returncode == 0, viewed.stderr
    assert "# Agentick run: js-explain" in viewed.stdout
    assert "## Usage" in viewed.stdout

    chat_files = sorted((home / "conversations" / "history" / "js-explain").glob("*.md"))
    assert len(chat_files) == 2
    assert any("# Agentick chat: js-explain" in path.read_text() for path in chat_files)
    assert any("Explain Map" in path.read_text() and "first answer" in path.read_text() for path in chat_files)
    assert any("Explain Set" in path.read_text() and "second answer" in path.read_text() for path in chat_files)

    chats = run_agc("chats", "js-explain", env={"AGENTICK_HOME": str(home)})
    assert chats.returncode == 0, chats.stderr
    assert "Chat sessions" in chats.stdout
    assert "js-explain" in chats.stdout
    session_id = chat_files[0].stem
    chat_view = run_agc("chats", "view", "js-explain", session_id, "--headless", env={"AGENTICK_HOME": str(home)})
    assert chat_view.returncode == 0, chat_view.stderr
    assert "# Agentick chat: js-explain" in chat_view.stdout
    assert f"Session id: `{session_id}`" in chat_view.stdout

    resumed = run_agc(
        "chats", "resume", "js-explain", session_id,
        "--reply", "Please continue from here.",
        "--headless",
        env={"AGENTICK_HOME": str(home), "AGC_MOCK_RESPONSE": "resumed answer", "AGC_CONTEXT_LIMIT_TOKENS": "10"},
    )
    assert resumed.returncode == 0, resumed.stderr
    assert "resumed answer" in resumed.stdout
    assert "agc warning: Context" in resumed.stderr
    assert "compact soon" in resumed.stderr
    resumed_markdown = (home / "conversations" / "history" / "js-explain" / f"{session_id}.md").read_text()
    assert "Please continue from here." in resumed_markdown
    assert "resumed answer" in resumed_markdown
    resumed_json = json.loads((home / "conversations" / "history" / "js-explain" / f"{session_id}.json").read_text())
    assert resumed_json["session_id"] == session_id
    assert resumed_json["messages"][-2]["content"] == "Please continue from here."
    assert resumed_json["messages"][-1]["content"] == "resumed answer"

    context = run_agc("chats", "context", "js-explain", session_id, "--headless", env={"AGENTICK_HOME": str(home), "AGC_CONTEXT_LIMIT_TOKENS": "10"})
    assert context.returncode == 0, context.stderr
    assert "# Agentick chat context: js-explain" in context.stdout
    assert "Estimated input context tokens" in context.stdout
    assert "Estimated context used" in context.stdout
    assert "Warning: context is at or above 50%" in context.stdout

    compacted = run_agc("chats", "compact", "js-explain", session_id, env={"AGENTICK_HOME": str(home), "AGC_MOCK_RESPONSE": "compact summary", "AGC_CONTEXT_LIMIT_TOKENS": "10"})
    assert compacted.returncode == 0, compacted.stderr
    assert "Compacted chat session" in compacted.stdout
    assert "Before: Context" in compacted.stdout
    assert "After:  Context" in compacted.stdout
    compacted_json = json.loads((home / "conversations" / "history" / "js-explain" / f"{session_id}.json").read_text())
    assert any("Compacted conversation summary for continuity" in message["content"] for message in compacted_json["messages"])
    assert any("compact summary" in message["content"] for message in compacted_json["messages"])

    reset = run_agc("chats", "reset", "js-explain", session_id, "--yes", env={"AGENTICK_HOME": str(home)})
    assert reset.returncode == 0, reset.stderr
    assert f"Reset chat context: js-explain {session_id}" in reset.stdout
    assert not (home / "conversations" / "history" / "js-explain" / f"{session_id}.md").exists()
    assert not (home / "conversations" / "history" / "js-explain" / f"{session_id}.json").exists()


def test_run_task_no_context_skips_chat_persistence(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.json").write_text(json.dumps({
        "default_provider": "openai",
        "providers": {"openai": {"api_key": "test-key", "model": "gpt-4o-mini"}},
    }))
    task_dir = home / "tasks"
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "js-explain.json").write_text(json.dumps({
        "name": "js-explain",
        "provider": "openai",
        "user_prompt": "Explain {{arg:0}}",
    }))

    proc = run_agc(
        "js-explain", "Map", "--headless", "--no-context",
        env={"AGENTICK_HOME": str(home), "AGC_MOCK_RESPONSE": "answer"},
    )

    assert proc.returncode == 0, proc.stderr
    assert "answer" in proc.stdout
    assert (home / "runs" / "js-explain.md").exists()
    assert not (home / "conversations" / "history" / "js-explain").exists()


def test_tasks_list_saved_tasks_with_agent_and_routine_labels():
    home = ROOT / ".test-agentick-home"
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.json").write_text(json.dumps({
        "default_provider": "openai",
        "providers": {"openai": {"api_key": "test-key", "model": "gpt-4o-mini", "reasoning_effort": "low"}},
    }))
    task_dir = home / "tasks"
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "review.json").write_text(json.dumps({
        "name": "review",
        "provider": "openai",
        "user_prompt": "Review code",
    }))
    (task_dir / "branch-watch.json").write_text(json.dumps({
        "name": "branch-watch",
        "provider": "openai",
        "model": "gpt-4o",
        "reasoning_effort": "high",
        "user_prompt": "Watch branch",
        "agent": True,
        "routine": "every 15m",
    }))

    proc = run_agc("tasks", "--no-interactive")

    assert proc.returncode == 0, proc.stderr
    assert "review" in proc.stdout
    assert "openai/gpt-4o-mini" in proc.stdout
    assert "branch-watch" in proc.stdout
    assert "openai/gpt-4o" in proc.stdout
    assert "agent, routine" in proc.stdout


def test_routine_tasks_list_due_items():
    home = ROOT / ".test-agentick-home"
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.json").write_text(json.dumps({
        "default_provider": "gemini",
        "providers": {"gemini": {"auth_method": "api_key", "api_key": "test-key", "model": "gemini-3-flash-preview"}},
    }))
    task_dir = ROOT / ".test-agentick-home" / "tasks"
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "daily-brief.json").write_text(json.dumps({
        "name": "daily-brief",
        "provider": "gemini",
        "model": "gemini-3-flash-preview",
        "user_prompt": "Summarize my day",
        "routine": {"every": "daily", "at": "09:00"},
    }))
    proc = run_agc("routines", "--no-interactive")
    assert proc.returncode == 0
    assert "daily-brief" in proc.stdout
    assert "daily at 09:00" in proc.stdout


def test_routines_show_task_specific_or_default_model_and_reasoning():
    home = ROOT / ".test-agentick-home"
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.json").write_text(json.dumps({
        "default_provider": "openai",
        "providers": {"openai": {"api_key": "test-key", "model": "gpt-4o-mini", "reasoning_effort": "low"}},
    }))
    task_dir = home / "tasks"
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "default-routine.json").write_text(json.dumps({
        "name": "default-routine",
        "provider": "openai",
        "user_prompt": "Default model",
        "routine": {"every": "daily", "at": "09:00"},
    }))
    (task_dir / "specific-routine.json").write_text(json.dumps({
        "name": "specific-routine",
        "provider": "openai",
        "model": "gpt-4o",
        "reasoning_effort": "high",
        "user_prompt": "Specific model",
        "routine": {"every": "hourly"},
    }))
    proc = run_agc("routines", "--no-interactive")
    assert proc.returncode == 0
    assert "default-routine" in proc.stdout
    assert "gpt-4o-mini" in proc.stdout
    assert "reasoning low" in proc.stdout
    assert "specific-routine" in proc.stdout
    assert "gpt-4o" in proc.stdout
    assert "reasoning high" in proc.stdout
