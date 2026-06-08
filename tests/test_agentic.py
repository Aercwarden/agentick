from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV = os.environ.copy()
ENV["PYTHONPATH"] = str(ROOT / "src")
ENV["AGENTICK_HOME"] = str(ROOT / ".test-agentick-agent-home")


def run_agc(*args: str, env: dict[str, str] | None = None):
    merged = ENV.copy()
    if env:
        merged.update(env)
    return subprocess.run(
        [sys.executable, "-m", "agentick", *args],
        cwd=ROOT,
        env=merged,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def seed_config() -> None:
    home = ROOT / ".test-agentick-agent-home"
    home.mkdir(parents=True, exist_ok=True)
    for transient in (home / "mock_agent_index.txt", home / "last_agent_trace.json"):
        if transient.exists():
            transient.unlink()
    run_dir = home / "runs"
    if run_dir.exists():
        for file in run_dir.glob("*.md"):
            file.unlink()
    routines_dir = home / "routines"
    if routines_dir.exists():
        for file in routines_dir.glob("*"):
            if file.is_file():
                file.unlink()
    (home / "config.json").write_text(json.dumps({
        "default_provider": "openai",
        "providers": {"openai": {"auth_method": "api_key", "api_key": "test-key", "model": "gpt-4o-mini"}},
    }), encoding="utf-8")
    (home / "tasks").mkdir(exist_ok=True)


def test_new_can_save_agentic_task_from_frontmatter(tmp_path: Path):
    seed_config()
    prompt = tmp_path / "agent.md"
    prompt.write_text("---\nsystem: Be careful.\nagent: true\n---\nImprove the repo.", encoding="utf-8")

    proc = run_agc("new", str(prompt), "repo-agent", "--no-interactive")

    assert proc.returncode == 0, proc.stderr
    task = json.loads((ROOT / ".test-agentick-agent-home" / "tasks" / "repo-agent.json").read_text())
    assert task["agent"] is True


def test_agentic_task_runs_tool_loop_and_writes_trace(tmp_path: Path):
    seed_config()
    target = ROOT / "agentic-smoke.txt"
    if target.exists():
        target.unlink()
    task_dir = ROOT / ".test-agentick-agent-home" / "tasks"
    (task_dir / "make-file.json").write_text(json.dumps({
        "name": "make-file",
        "provider": "openai",
        "agent": True,
        "user_prompt": "Create agentic-smoke.txt",
    }), encoding="utf-8")
    responses = [
        {"thought": "Need create the requested file.", "tool": {"name": "write_file", "args": {"path": "agentic-smoke.txt", "content": "hello from agent\n"}}},
        {"thought": "Verify contents.", "tool": {"name": "read_file", "args": {"path": "agentic-smoke.txt"}}},
        {"final": "Created agentic-smoke.txt and verified its contents."},
    ]

    proc = run_agc(
        "make-file",
        "--headless",
        "--allow-write",
        env={"AGC_MOCK_AGENT_RESPONSES": json.dumps(responses)},
    )

    assert proc.returncode == 0, proc.stderr
    assert "Created agentic-smoke.txt" in proc.stdout
    assert target.read_text(encoding="utf-8") == "hello from agent\n"
    trace = ROOT / ".test-agentick-agent-home" / "last_agent_trace.json"
    assert "write_file" in trace.read_text(encoding="utf-8")
    log = ROOT / ".test-agentick-agent-home" / "runs" / "make-file.md"
    assert "Created agentic-smoke.txt" in log.read_text(encoding="utf-8")
    assert "write_file" in log.read_text(encoding="utf-8")
    target.unlink()


def test_agentic_write_requires_explicit_permission():
    seed_config()
    task_dir = ROOT / ".test-agentick-agent-home" / "tasks"
    (task_dir / "blocked-write.json").write_text(json.dumps({
        "name": "blocked-write",
        "provider": "openai",
        "agent": True,
        "user_prompt": "Try writing.",
    }), encoding="utf-8")
    responses = [
        {"tool": {"name": "write_file", "args": {"path": "blocked.txt", "content": "no"}}},
        {"final": "Tool failed as expected."},
    ]

    proc = run_agc("blocked-write", "--headless", env={"AGC_MOCK_AGENT_RESPONSES": json.dumps(responses)})

    assert proc.returncode == 0, proc.stderr
    trace = json.loads((ROOT / ".test-agentick-agent-home" / "last_agent_trace.json").read_text())
    assert "requires --allow-write" in trace[1]["observation"]
    assert not (ROOT / "blocked.txt").exists()


def test_agentic_curl_requires_explicit_network_permission():
    seed_config()
    task_dir = ROOT / ".test-agentick-agent-home" / "tasks"
    (task_dir / "blocked-curl.json").write_text(json.dumps({
        "name": "blocked-curl",
        "provider": "openai",
        "agent": True,
        "user_prompt": "Try network egress.",
    }), encoding="utf-8")
    responses = [
        {"tool": {"name": "curl", "args": {"url": "https://example.com"}}},
        {"final": "Network tool failed as expected."},
    ]

    proc = run_agc("blocked-curl", "--headless", env={"AGC_MOCK_AGENT_RESPONSES": json.dumps(responses)})

    assert proc.returncode == 0, proc.stderr
    trace = json.loads((ROOT / ".test-agentick-agent-home" / "last_agent_trace.json").read_text())
    assert "requires --allow-net" in trace[1]["observation"]


def test_routines_view_prints_last_agentic_run_log_headlessly():
    seed_config()
    run_dir = ROOT / ".test-agentick-agent-home" / "runs"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "branch-watch.md").write_text("# Agentick run: branch-watch\n\nprepared branch ready\n", encoding="utf-8")

    proc = run_agc("routines", "view", "branch-watch", "--headless")

    assert proc.returncode == 0, proc.stderr
    assert "prepared branch ready" in proc.stdout


def test_routines_list_shows_agent_and_view_hint():
    seed_config()
    task_dir = ROOT / ".test-agentick-agent-home" / "tasks"
    (task_dir / "branch-watch.json").write_text(json.dumps({
        "name": "branch-watch",
        "provider": "openai",
        "agent": True,
        "user_prompt": "Watch branch",
        "routine": {"every": "15m", "scheduler": "launchd", "installed": False},
    }), encoding="utf-8")

    proc = run_agc("routines", "--no-interactive")

    assert proc.returncode == 0, proc.stderr
    assert "branch-watch" in proc.stdout
    assert "stopped" in proc.stdout
    assert "15m via launchd" in proc.stdout
    assert "agent" in proc.stdout
    assert "view|status|start|stop|edit|delete branch-watch" in proc.stdout


def test_routines_create_prompts_for_schedule_metadata_and_writes_launchd_artifacts():
    seed_config()
    task_dir = ROOT / ".test-agentick-agent-home" / "tasks"
    (task_dir / "branch-watch.json").write_text(json.dumps({
        "name": "branch-watch",
        "provider": "openai",
        "agent": True,
        "user_prompt": "Watch branch {{arg:0}}",
    }), encoding="utf-8")

    proc = run_agc(
        "routines", "create", "branch-watch",
        "--every", "15m",
        "--arg", "main",
        "--scheduler", "launchd",
        "--agent",
        "--allow-shell",
        "--allow-net",
        "--no-install",
        "--no-interactive",
    )

    assert proc.returncode == 0, proc.stderr
    assert "Routine created" in proc.stdout
    task = json.loads((task_dir / "branch-watch.json").read_text())
    routine = task["routine"]
    assert routine["every"] == "15m"
    assert routine["scheduler"] == "launchd"
    assert routine["args"] == ["main"]
    assert routine["installed"] is False
    assert routine["permissions"]["agent"] is True
    assert routine["permissions"]["allow_shell"] is True
    assert routine["permissions"]["allow_net"] is True
    plist = ROOT / ".test-agentick-agent-home" / "routines" / "branch-watch.plist"
    script = ROOT / ".test-agentick-agent-home" / "routines" / "branch-watch.sh"
    assert "StartInterval" in plist.read_text(encoding="utf-8")
    assert "900" in plist.read_text(encoding="utf-8")
    assert "--allow-shell" in script.read_text(encoding="utf-8")
    assert "--allow-net" in script.read_text(encoding="utf-8")


def test_routines_create_can_write_cron_artifact_on_linux_style_scheduler():
    seed_config()
    task_dir = ROOT / ".test-agentick-agent-home" / "tasks"
    (task_dir / "daily-report.json").write_text(json.dumps({
        "name": "daily-report",
        "provider": "openai",
        "user_prompt": "Report",
    }), encoding="utf-8")

    proc = run_agc("routines", "create", "daily-report", "--every", "2h", "--scheduler", "cron", "--no-install", "--no-interactive")

    assert proc.returncode == 0, proc.stderr
    cron = ROOT / ".test-agentick-agent-home" / "routines" / "daily-report.cron"
    assert cron.exists()
    assert "0 */2 * * *" in cron.read_text(encoding="utf-8")


def test_routines_edit_stop_and_delete_update_saved_routine_without_touching_os_scheduler():
    seed_config()
    task_dir = ROOT / ".test-agentick-agent-home" / "tasks"
    (task_dir / "branch-watch.json").write_text(json.dumps({
        "name": "branch-watch",
        "provider": "openai",
        "user_prompt": "Watch branch",
        "routine": {"every": "15m", "scheduler": "manual", "installed": True, "args": ["main"], "permissions": {}},
    }), encoding="utf-8")

    edit = run_agc("routines", "edit", "branch-watch", "--every", "30m", "--arg", "dev", "--no-install", "--no-interactive")
    assert edit.returncode == 0, edit.stderr
    routine = json.loads((task_dir / "branch-watch.json").read_text())["routine"]
    assert routine["every"] == "30m"
    assert routine["args"] == ["dev"]

    stop = run_agc("routines", "stop", "branch-watch", "--no-install", "--no-interactive")
    assert stop.returncode == 0, stop.stderr
    assert json.loads((task_dir / "branch-watch.json").read_text())["routine"]["installed"] is False

    delete = run_agc("routines", "delete", "branch-watch", "--yes", "--no-install", "--no-interactive")
    assert delete.returncode == 0, delete.stderr
    assert "routine" not in json.loads((task_dir / "branch-watch.json").read_text())


def test_help_mentions_agentic_workflows():
    proc = run_agc("--help")

    assert proc.returncode == 0
    assert "--agent" in proc.stdout
    assert "--allow-write" in proc.stdout
    assert "--allow-net" in proc.stdout
    assert "agc branch-watch main --agent --allow-write --allow-shell" in proc.stdout
    assert "agc routines create branch-watch --every 15m" in proc.stdout
    assert "agc routines view branch-watch" in proc.stdout
    assert "agc routines stop branch-watch" in proc.stdout
