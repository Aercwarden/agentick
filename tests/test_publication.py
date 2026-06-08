from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_publication_files_are_present_and_linked():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert (ROOT / "LICENSE").exists()
    assert "MIT License" in (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert (ROOT / "scripts" / "install.sh").exists()
    assert (ROOT / "scripts" / "install.ps1").exists()
    assert (ROOT / "docs" / "screenshots" / "setup.svg").exists()
    assert (ROOT / "docs" / "screenshots" / "viewer.svg").exists()

    for phrase in [
        "The problem",
        "How Agentick works",
        "copy-paste",
        "small CLI commands",
        "Token and cost efficiency",
        "model, reasoning effort",
        "Savings are not automatic",
        "macOS",
        "Linux",
        "Windows PowerShell",
        "agc task > file.md",
        "Security and privacy notes",
        "docs/screenshots/setup.svg",
        "docs/screenshots/viewer.svg",
        "programming ligatures depend on the",
        "human-designed, vibe-coded project",
        "AI-assisted coding",
    ]:
        assert phrase in readme


def test_gitignore_blocks_local_credentials_and_runtime_homes():
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for pattern in [".env", ".env.*", ".test-agentick-home/", ".smoke-agentick-home/"]:
        assert pattern in gitignore
