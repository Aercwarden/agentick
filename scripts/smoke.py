from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[1]
venv_bin = root / ".venv" / "bin"
agc = venv_bin / "agc"
home = root / ".smoke-agentick-home"
if home.exists():
    shutil.rmtree(home)
env = os.environ.copy()
env["AGENTICK_HOME"] = str(home)

def run(args, extra_env=None, expected=0):
    e = env.copy()
    if extra_env:
        e.update(extra_env)
    proc = subprocess.run([str(agc), *args], cwd=root, env=e, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    print("$ agc", " ".join(args))
    print(proc.stdout, end="")
    if proc.stderr:
        print(proc.stderr, end="")
    assert proc.returncode == expected, proc.returncode

run(["--no-interactive"], expected=2)
run(["setup", "--provider", "openai", "--model", "gpt-4o-mini", "--api-key", "test-key", "--no-interactive"])
prompt = root / ".smoke-prompt.md"
prompt.write_text("---\nsystem: Be concise.\n---\nHello {{arg:0}}\n", encoding="utf-8")
run(["new", str(prompt), "say-hello", "--provider", "openai", "--reasoning", "low", "--no-interactive"])
run(["say-hello", "James", "--headless"], extra_env={"AGC_MOCK_RESPONSE": "Hello from Agentick smoke test."})
print("config mode", oct((home / "config.json").stat().st_mode & 0o777))
print("last prompt", (home / "last_prompt.txt").read_text(encoding="utf-8"))
