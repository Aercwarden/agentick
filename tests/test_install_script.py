from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_install(*args: str, env: dict[str, str] | None = None):
    merged = os.environ.copy()
    if env:
        merged.update(env)
    return subprocess.run(
        ["bash", "scripts/install.sh", *args],
        cwd=ROOT,
        env=merged,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def test_install_script_help_documents_safe_install_flow():
    proc = run_install("--help")
    assert proc.returncode == 0
    assert "Agentick installer" in proc.stdout
    assert "--dry-run" in proc.stdout
    assert "--prefix" in proc.stdout
    assert "--no-shell-profile" in proc.stdout
    assert "agc setup" in proc.stdout


def test_install_script_dry_run_does_not_create_prefix(tmp_path: Path):
    prefix = tmp_path / "agentick-prefix"
    proc = run_install("--dry-run", "--prefix", str(prefix), "--python", sys.executable)
    assert proc.returncode == 0, proc.stderr
    assert "DRY RUN" in proc.stdout
    assert str(prefix) in proc.stdout
    assert "python -m venv" in proc.stdout
    assert "pip install" in proc.stdout
    assert "shell profile" in proc.stdout
    assert "agc setup" in proc.stdout
    assert not prefix.exists()


def test_install_script_creates_isolated_prefix_and_agc_binary(tmp_path: Path):
    prefix = tmp_path / "agentick-install"
    proc = run_install("--prefix", str(prefix), "--python", sys.executable, "--no-shell-profile")
    assert proc.returncode == 0, proc.stderr
    agc = prefix / "bin" / "agc"
    assert agc.exists()
    check = subprocess.run(
        [str(agc), "--help"],
        cwd=ROOT,
        env={**os.environ, "AGENTICK_HOME": str(tmp_path / "home")},
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert check.returncode == 0
    assert "Agentick" in check.stdout


def test_install_script_updates_shell_profile_once(tmp_path: Path):
    prefix = tmp_path / "agentick-install"
    home = tmp_path / "home"
    home.mkdir()
    env = {"HOME": str(home), "SHELL": "/bin/zsh"}

    first = run_install("--prefix", str(prefix), "--python", sys.executable, env=env)
    second = run_install("--prefix", str(prefix), "--python", sys.executable, env=env)

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    profile = home / ".zshrc"
    content = profile.read_text()
    line = f'export PATH="{prefix}/bin:$PATH"'
    assert content.count(line) == 1
    assert "Added Agentick to" in first.stdout
    assert "already configured" in second.stdout


def test_install_script_can_skip_shell_profile_update(tmp_path: Path):
    prefix = tmp_path / "agentick-install"
    home = tmp_path / "home"
    home.mkdir()
    proc = run_install(
        "--prefix", str(prefix), "--python", sys.executable, "--no-shell-profile",
        env={"HOME": str(home), "SHELL": "/bin/zsh"},
    )
    assert proc.returncode == 0, proc.stderr
    assert not (home / ".zshrc").exists()
    assert "Skipping shell profile update" in proc.stdout
