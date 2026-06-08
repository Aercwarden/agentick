from __future__ import annotations

import argparse
import getpass
from io import StringIO
import json
import os
import platform
import plistlib
import re
import shlex
import shutil
import ssl
import subprocess
import sys
import tempfile
import termios
import threading
import textwrap
import time
import tty
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, TypeVar

import certifi
from rich.console import Console
from rich.markdown import Markdown

RESET = "\033[0m"
CYAN = "\033[96m"
MAGENTA = "\033[95m"
DIM = "\033[2m"
BOLD = "\033[1m"
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"

T = TypeVar("T")

PROVIDERS: dict[str, dict[str, Any]] = {
    "openai": {
        "label": "OpenAI",
        "env": "OPENAI_API_KEY",
        "env_vars": ["OPENAI_API_KEY"],
        "models": ["gpt-5.5", "gpt-5.5-mini", "gpt-5.4", "gpt-5.4-mini", "gpt-4o", "gpt-4o-mini"],
        "reasoning": ["minimal", "low", "medium", "high"],
        "url": "https://api.openai.com/v1/chat/completions",
        "api": "openai",
        "auth_methods": ["api_key", "oauth"],
        "oauth_label": "OpenAI Codex OAuth (ChatGPT/Codex account)",
        "oauth_provider": "openai-codex",
        "oauth_env": "AGC_OPENAI_OAUTH_TOKEN",
    },
    "openrouter": {
        "label": "OpenRouter",
        "env": "OPENROUTER_API_KEY",
        "env_vars": ["OPENROUTER_API_KEY"],
        "models": ["anthropic/claude-sonnet-4.6", "openai/gpt-5.5", "google/gemini-3-pro-preview", "x-ai/grok-4.3", "deepseek/deepseek-v4-pro"],
        "reasoning": ["minimal", "low", "medium", "high"],
        "url": "https://openrouter.ai/api/v1/chat/completions",
        "api": "openai",
        "auth_methods": ["api_key"],
    },
    "anthropic": {
        "label": "Anthropic",
        "env": "ANTHROPIC_API_KEY",
        "env_vars": ["ANTHROPIC_API_KEY", "ANTHROPIC_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN"],
        "models": ["claude-opus-4-8", "claude-sonnet-4-6", "claude-haiku-4-5-20251001", "claude-sonnet-4-20250514"],
        "reasoning": ["low", "medium", "high"],
        "url": "https://api.anthropic.com/v1/messages",
        "api": "anthropic",
        "auth_methods": ["api_key"],
    },
    "gemini": {
        "label": "Gemini",
        "env": "GEMINI_API_KEY",
        "alt_env": "GOOGLE_API_KEY",
        "env_vars": ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
        "models": ["gemini-3.1-pro-preview", "gemini-3-pro-preview", "gemini-3-flash-preview", "gemini-2.5-flash"],
        "reasoning": ["low", "medium", "high"],
        "url_template": "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}",
        "api": "gemini",
        "auth_methods": ["api_key", "oauth"],
        "oauth_label": "Google Gemini OAuth (Gemini CLI / Cloud Code)",
        "oauth_provider": "google-gemini-cli",
        "oauth_env": "AGC_GEMINI_OAUTH_TOKEN",
    },
    "grok": {
        "label": "xAI / Grok",
        "env": "XAI_API_KEY",
        "env_vars": ["XAI_API_KEY"],
        "models": ["grok-4.3", "grok-4.20-0309-reasoning", "grok-4.20-0309-non-reasoning"],
        "reasoning": ["low", "medium", "high"],
        "url": "https://api.x.ai/v1/chat/completions",
        "api": "openai",
        "auth_methods": ["api_key", "oauth"],
        "oauth_label": "xAI Grok OAuth (SuperGrok / Premium+)",
        "oauth_provider": "xai-oauth",
        "oauth_env": "AGC_GROK_OAUTH_TOKEN",
    },
    "deepseek": {
        "label": "DeepSeek",
        "env": "DEEPSEEK_API_KEY",
        "env_vars": ["DEEPSEEK_API_KEY"],
        "models": ["deepseek-v4-pro", "deepseek-v4-flash", "deepseek-chat", "deepseek-reasoner"],
        "reasoning": ["low", "medium", "high"],
        "url": "https://api.deepseek.com/v1/chat/completions",
        "api": "openai",
        "auth_methods": ["api_key"],
    },
    "zai": {
        "label": "Z.AI / GLM",
        "env": "GLM_API_KEY",
        "env_vars": ["GLM_API_KEY", "ZAI_API_KEY", "Z_AI_API_KEY"],
        "models": ["glm-5.1", "glm-5", "glm-5-turbo", "glm-4.5", "glm-4.5-flash"],
        "reasoning": ["low", "medium", "high"],
        "url": "https://api.z.ai/api/paas/v4/chat/completions",
        "api": "openai",
        "auth_methods": ["api_key"],
    },
    "kimi-coding": {
        "label": "Kimi / Moonshot",
        "env": "KIMI_API_KEY",
        "env_vars": ["KIMI_API_KEY", "KIMI_CODING_API_KEY"],
        "models": ["kimi-k2.6", "kimi-k2.5", "kimi-for-coding", "kimi-k2-thinking"],
        "reasoning": ["low", "medium", "high"],
        "url": "https://api.moonshot.ai/v1/chat/completions",
        "api": "openai",
        "auth_methods": ["api_key"],
    },
    "alibaba": {
        "label": "Alibaba / DashScope",
        "env": "DASHSCOPE_API_KEY",
        "env_vars": ["DASHSCOPE_API_KEY"],
        "models": ["qwen3.7-max", "qwen3.6-plus", "qwen3.5-plus", "qwen3-coder-plus"],
        "reasoning": ["low", "medium", "high"],
        "url": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions",
        "api": "openai",
        "auth_methods": ["api_key"],
    },
    "minimax": {
        "label": "MiniMax",
        "env": "MINIMAX_API_KEY",
        "env_vars": ["MINIMAX_API_KEY"],
        "models": ["MiniMax-M3", "MiniMax-M2.7", "MiniMax-M2.5", "MiniMax-M2"],
        "reasoning": ["low", "medium", "high"],
        "url": "https://api.minimax.io/v1/text/chatcompletion_v2",
        "api": "openai",
        "auth_methods": ["api_key"],
    },
    "minimax-cn": {
        "label": "MiniMax CN",
        "env": "MINIMAX_CN_API_KEY",
        "env_vars": ["MINIMAX_CN_API_KEY"],
        "models": ["MiniMax-M3", "MiniMax-M2.7", "MiniMax-M2.5", "MiniMax-M2"],
        "reasoning": ["low", "medium", "high"],
        "url": "https://api.minimaxi.com/v1/text/chatcompletion_v2",
        "api": "openai",
        "auth_methods": ["api_key"],
    },
    "huggingface": {
        "label": "Hugging Face",
        "env": "HF_TOKEN",
        "env_vars": ["HF_TOKEN"],
        "models": ["moonshotai/Kimi-K2.5", "Qwen/Qwen3.5-397B-A17B", "deepseek-ai/DeepSeek-V3.2", "zai-org/GLM-5"],
        "reasoning": ["low", "medium", "high"],
        "url": "https://router.huggingface.co/v1/chat/completions",
        "api": "openai",
        "auth_methods": ["api_key"],
    },
    "nvidia": {
        "label": "NVIDIA NIM",
        "env": "NVIDIA_API_KEY",
        "env_vars": ["NVIDIA_API_KEY"],
        "models": ["nvidia/nemotron-3-super-120b-a12b", "nvidia/nemotron-3-nano-30b-a3b", "openai/gpt-oss-120b"],
        "reasoning": ["low", "medium", "high"],
        "url": "https://integrate.api.nvidia.com/v1/chat/completions",
        "api": "openai",
        "auth_methods": ["api_key"],
    },
    "xiaomi": {
        "label": "Xiaomi MiMo",
        "env": "XIAOMI_API_KEY",
        "env_vars": ["XIAOMI_API_KEY"],
        "models": ["mimo-v2.5-pro", "mimo-v2.5", "mimo-v2-pro", "mimo-v2-flash"],
        "reasoning": ["low", "medium", "high"],
        "url": "https://api.xiaomimimo.com/v1/chat/completions",
        "api": "openai",
        "auth_methods": ["api_key"],
    },
    "kilocode": {
        "label": "Kilo Code",
        "env": "KILOCODE_API_KEY",
        "env_vars": ["KILOCODE_API_KEY"],
        "models": ["anthropic/claude-sonnet-4.6", "openai/gpt-5.4", "google/gemini-3-pro-preview"],
        "reasoning": ["low", "medium", "high"],
        "url": "https://api.kilo.ai/api/gateway/chat/completions",
        "api": "openai",
        "auth_methods": ["api_key"],
    },
    "ai-gateway": {
        "label": "AI Gateway (Vercel)",
        "env": "AI_GATEWAY_API_KEY",
        "env_vars": ["AI_GATEWAY_API_KEY"],
        "models": ["openai/gpt-5.4", "anthropic/claude-sonnet-4.6", "google/gemini-3-pro-preview"],
        "reasoning": ["low", "medium", "high"],
        "url": "https://ai-gateway.vercel.sh/v1/chat/completions",
        "api": "openai",
        "auth_methods": ["api_key"],
    },
    "opencode-zen": {
        "label": "OpenCode Zen",
        "env": "OPENCODE_ZEN_API_KEY",
        "env_vars": ["OPENCODE_ZEN_API_KEY"],
        "models": ["kimi-k2.5", "gpt-5.4", "claude-sonnet-4.6", "gemini-3-pro"],
        "reasoning": ["low", "medium", "high"],
        "url": "https://opencode.ai/zen/v1/chat/completions",
        "api": "openai",
        "auth_methods": ["api_key"],
    },
    "opencode-go": {
        "label": "OpenCode Go",
        "env": "OPENCODE_GO_API_KEY",
        "env_vars": ["OPENCODE_GO_API_KEY"],
        "models": ["kimi-k2.6", "glm-5.1", "mimo-v2.5-pro", "qwen3.7-max"],
        "reasoning": ["low", "medium", "high"],
        "url": "https://opencode.ai/zen/go/v1/chat/completions",
        "api": "openai",
        "auth_methods": ["api_key"],
    },
    "lmstudio": {
        "label": "LM Studio",
        "env": "LM_API_KEY",
        "env_vars": ["LM_API_KEY"],
        "models": ["local-model"],
        "reasoning": ["low", "medium", "high"],
        "url": "http://127.0.0.1:1234/v1/chat/completions",
        "api": "openai",
        "auth_methods": ["api_key"],
        "allow_dummy_key": True,
    },
    "ollama-cloud": {
        "label": "Ollama Cloud",
        "env": "OLLAMA_API_KEY",
        "env_vars": ["OLLAMA_API_KEY"],
        "models": ["gpt-oss:120b", "llama3.3", "qwen3"],
        "reasoning": ["low", "medium", "high"],
        "url": "https://ollama.com/v1/chat/completions",
        "api": "openai",
        "auth_methods": ["api_key"],
    },
    "tencent-tokenhub": {
        "label": "Tencent TokenHub",
        "env": "TOKENHUB_API_KEY",
        "env_vars": ["TOKENHUB_API_KEY"],
        "models": ["hy3-preview"],
        "reasoning": ["low", "medium", "high"],
        "url": "https://tokenhub.tencentmaas.com/v1/chat/completions",
        "api": "openai",
        "auth_methods": ["api_key"],
    },
}


SETUP_PROVIDER_ROWS: list[tuple[str, str, str, str]] = [
    ("openai-api", "OpenAI (API key)", "openai", "api_key"),
    ("openai-codex", "OpenAI Codex (OAuth / ChatGPT/Codex account)", "openai", "oauth"),
    ("openrouter", "OpenRouter (API key)", "openrouter", "api_key"),
    ("anthropic", "Anthropic (API key)", "anthropic", "api_key"),
    ("gemini", "Google Gemini (API key)", "gemini", "api_key"),
    ("google-gemini-cli", "Google Gemini OAuth / Code Assist", "gemini", "oauth"),
    ("xai", "xAI / Grok (API key)", "grok", "api_key"),
    ("xai-oauth", "xAI Grok OAuth (SuperGrok / Premium+)", "grok", "oauth"),
    ("deepseek", "DeepSeek (API key)", "deepseek", "api_key"),
    ("zai", "Z.AI / GLM (API key)", "zai", "api_key"),
    ("kimi-coding", "Kimi / Moonshot (API key)", "kimi-coding", "api_key"),
    ("alibaba", "Alibaba / DashScope (API key)", "alibaba", "api_key"),
    ("minimax", "MiniMax (API key)", "minimax", "api_key"),
    ("minimax-cn", "MiniMax CN (API key)", "minimax-cn", "api_key"),
    ("huggingface", "Hugging Face (token)", "huggingface", "api_key"),
    ("nvidia", "NVIDIA NIM (API key)", "nvidia", "api_key"),
    ("xiaomi", "Xiaomi MiMo (API key)", "xiaomi", "api_key"),
    ("kilocode", "Kilo Code (API key)", "kilocode", "api_key"),
    ("ai-gateway", "AI Gateway / Vercel (API key)", "ai-gateway", "api_key"),
    ("opencode-zen", "OpenCode Zen (API key)", "opencode-zen", "api_key"),
    ("opencode-go", "OpenCode Go (API key)", "opencode-go", "api_key"),
    ("lmstudio", "LM Studio (local OpenAI-compatible)", "lmstudio", "api_key"),
    ("ollama-cloud", "Ollama Cloud (API key)", "ollama-cloud", "api_key"),
    ("tencent-tokenhub", "Tencent TokenHub (API key)", "tencent-tokenhub", "api_key"),
    ("cancel", "Leave unchanged", "", ""),
]


SETUP_PROVIDER_ALIASES = {
    "openai": "openai-api",
    "grok": "xai",
    "xai-api": "xai",
    "moonshot": "kimi-coding",
    "kimi": "kimi-coding",
    "dashscope": "alibaba",
    "qwen": "alibaba",
    "glm": "zai",
    "vercel": "ai-gateway",
}



def build_provider_choices() -> list[tuple[str, str]]:
    """Return Hermes-style provider rows: concrete API-key/OAuth providers."""
    return [(slug, label) for slug, label, _provider, _auth in SETUP_PROVIDER_ROWS]


def provider_env_names(provider: str) -> list[str]:
    meta = PROVIDERS[provider]
    names = [str(item) for item in meta.get("env_vars", []) if str(item)]
    for key in ("env", "alt_env"):
        value = str(meta.get(key, ""))
        if value and value not in names:
            names.append(value)
    return names


def provider_env_display(provider: str) -> str:
    return " / ".join(provider_env_names(provider))


def resolve_provider_selection(selection: str) -> tuple[str, str]:
    """Map a Hermes-style provider slug to Agentick's runtime provider/auth."""
    normalized = SETUP_PROVIDER_ALIASES.get(selection, selection)
    for slug, _label, provider, auth_method in SETUP_PROVIDER_ROWS:
        if slug == normalized and provider:
            return provider, auth_method
    raise ValueError(f"Unknown provider: {selection}")


@dataclass
class Paths:
    home: Path
    config: Path
    tasks: Path
    routines: Path
    conversations: Path


def agentick_home() -> Path:
    return Path(os.environ.get("AGENTICK_HOME", Path.home() / ".agentick")).expanduser()


def paths() -> Paths:
    home = agentick_home()
    return Paths(home=home, config=home / "config.json", tasks=home / "tasks", routines=home / "routines", conversations=home / "conversations")


def secure_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(content)
    try:
        os.chmod(path, 0o600)
        os.chmod(path.parent, 0o700)
    except OSError:
        pass


def load_config() -> dict[str, Any] | None:
    p = paths().config
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def save_config(config: dict[str, Any]) -> None:
    secure_write(paths().config, json.dumps(config, indent=2, sort_keys=True) + "\n")


def banner() -> str:
    return f"{MAGENTA}{BOLD}▰ Agentick{RESET} {CYAN}agc{RESET} {DIM}minimal cyberpunk prompt runner{RESET}"


def print_setup_guidance() -> None:
    print(banner())
    print()
    print(f"{YELLOW}Agentick setup required.{RESET}")
    print("Configure a provider first:")
    print("  agc setup")
    print()
    print("Supported provider setup paths:")
    for slug, label in build_provider_choices():
        if slug == "cancel":
            continue
        provider, auth_method = resolve_provider_selection(slug)
        meta = PROVIDERS[provider]
        envs = provider_env_display(provider)
        auth = "API key" if auth_method == "api_key" else f"OAuth ({meta['oauth_provider']})"
        print(f"  • {label} — {envs if auth_method == 'api_key' else auth}")


def usage_after_setup() -> str:
    return textwrap.dedent("""
    Ready. Usage:
      agc new ./prompt.md say-hello
      agc new                       # interactive creator
      agc edit <task-name>          # edit an existing task
      agc delete <task-name>        # delete a saved task
      agc tasks                     # list saved tasks
      agc <task-name> [args...]     # run a saved task
      agc routines create <task-name> --every 1h
      agc routines                  # list routine tasks
      agc routines stop <task-name>
      agc routines delete <task-name> --yes

    Prompt files: .txt, .md, .yaml, .json
    Task vault: ~/.agentick/tasks (or AGENTICK_HOME/tasks)
    """).strip()


def strip_ansi(text: str) -> str:
    return re.sub(r"\033\[[0-9;]*m", "", text)


def render_choice_menu(
    title: str,
    options: list[str],
    selected: int = 0,
    offset: int = 0,
    height: int = 8,
    description: str | None = None,
    query: str = "",
) -> str:
    """Render the same radio-list shape Hermes uses for provider/model setup."""
    if not options:
        return f"  {title}\n  No options"
    selected = max(0, min(selected, len(options) - 1))
    height = max(1, height)
    offset = max(0, min(offset, max(0, len(options) - height)))
    visible = options[offset : offset + height]
    lines = [f"  {title}"]
    if description:
        lines.extend(description.splitlines())
    if query:
        lines.append(f"  Search: {query}▎  BACKSPACE edit  Ctrl+U clear  ESC stop")
    else:
        lines.append("  ↑/↓ navigate  ENTER/SPACE select  / search  ESC cancel")
    lines.append("")
    for index, option in enumerate(visible, start=offset):
        arrow = "→" if index == selected else " "
        radio = "●" if index == selected else "○"
        lines.append(f" {arrow} ({radio}) {option}")
    end = min(offset + len(visible), len(options))
    lines.append("")
    lines.append(f"  {offset + 1}-{end} of {len(options)}")
    return "\n".join(lines)


_WORD_BOUNDARY = frozenset("-_/. ")


def _is_boundary(target: str, index: int) -> bool:
    if index == 0:
        return True
    prev = target[index - 1]
    if prev in _WORD_BOUNDARY:
        return True
    cur = target[index]
    return prev == prev.lower() and cur != cur.lower() and cur == cur.upper()


def _token_score(orig: str, lower: str, token: str) -> float | None:
    score = 0.0
    prev = -1
    search_from = 0
    positions: list[int] = []
    for ch in token:
        idx = lower.find(ch, search_from)
        if idx < 0:
            return None
        positions.append(idx)
        score += 1
        if prev >= 0 and idx == prev + 1:
            score += 5
        elif prev >= 0:
            score -= min(idx - prev - 1, 3)
        if _is_boundary(orig, idx):
            score += 3
        if idx == 0:
            score += 5
        prev = idx
        search_from = idx + 1
    if positions and positions[0] == 0 and positions[-1] == len(positions) - 1:
        score += 8
    if lower == token:
        score += 20
    score -= len(lower) * 0.01
    return score


def _fuzzy_score(label: str, query: str) -> float | None:
    lower = label.lower()
    tokens = query.lower().split()
    if not tokens:
        return 0.0
    total = 0.0
    for token in tokens:
        token_score = _token_score(label, lower, token)
        if token_score is None:
            return None
        total += token_score
    return total


def _filter_options(options: list[str], query: str) -> list[int]:
    q = query.strip()
    if not q:
        return list(range(len(options)))
    scored = []
    for idx, value in enumerate(options):
        score = _fuzzy_score(value, q)
        if score is not None:
            scored.append((idx, score))
    scored.sort(key=lambda pair: (-pair[1], pair[0]))
    return [idx for idx, _score in scored]


def curses_choose(prompt: str, options: list[str], default: str | None = None, description: str | None = None) -> str | None:
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        return None
    try:
        import curses
    except Exception:
        return None
    default_idx = options.index(default) if default in options else 0

    def run(stdscr: Any) -> str:
        curses.curs_set(0)
        stdscr.keypad(True)
        selected = default_idx
        offset = 0
        query = ""
        searching = False
        while True:
            filtered = _filter_options(options, query)
            if filtered and selected not in filtered:
                selected = filtered[0]
            rows, _cols = stdscr.getmaxyx()
            height = max(3, rows - 7)
            position = filtered.index(selected) if selected in filtered else 0
            offset = max(0, min(offset, max(0, len(filtered) - height)))
            if position < offset:
                offset = position
            elif position >= offset + height:
                offset = position - height + 1
            visible_indices = filtered[offset : offset + height]
            visible_options = [options[idx] for idx in visible_indices]
            selected_visible = visible_indices.index(selected) if selected in visible_indices else 0
            stdscr.erase()
            rendered = render_choice_menu(prompt, visible_options or ["No matches"], selected_visible, 0, height, description, query)
            for row, line in enumerate(strip_ansi(rendered).splitlines()[: rows - 1]):
                stdscr.addnstr(row, 0, line, max(0, _cols - 1))
            stdscr.refresh()
            key = stdscr.getch()
            if searching:
                if key in (10, 13, curses.KEY_ENTER):
                    searching = False
                elif key in (27,):
                    query = ""
                    searching = False
                elif key in (curses.KEY_BACKSPACE, 127, 8):
                    query = query[:-1]
                elif 32 <= key < 127:
                    query += chr(key)
                continue
            if key in (ord("q"), 27):
                return default or options[0]
            if key == ord("/"):
                searching = True
                continue
            if key in (curses.KEY_UP, ord("k")) and filtered:
                selected = filtered[(position - 1) % len(filtered)]
            elif key in (curses.KEY_DOWN, ord("j")) and filtered:
                selected = filtered[(position + 1) % len(filtered)]
            elif key in (10, 13, curses.KEY_ENTER) and filtered:
                return options[selected]

    try:
        return curses.wrapper(run)
    except Exception:
        return None


def choose(prompt: str, options: list[str], default: str | None = None, description: str | None = None) -> str:
    if not sys.stdin.isatty():
        return default or options[0]
    picked = curses_choose(prompt, options, default, description)
    if picked:
        return picked
    print(render_choice_menu(prompt, options, options.index(default) if default in options else 0, 0, min(8, len(options)), description))
    for idx, option in enumerate(options, 1):
        marker = "*" if option == default else " "
        print(f"  {idx}. {marker} {option}")
    raw = input("› ").strip()
    if not raw and default:
        return default
    if raw.isdigit() and 1 <= int(raw) <= len(options):
        return options[int(raw) - 1]
    return raw if raw in options else (default or options[0])


def oauth_setup_guidance(meta: dict[str, Any], oauth_env: str) -> str:
    return "\n".join(
        [
            "Agentick will open your browser or show a device code. You do not need to paste a token.",
            f"For non-interactive setup, set {oauth_env} or pass --oauth-token.",
        ]
    )


def read_codex_access_token(auth_file: Path | None = None) -> str:
    auth_file = auth_file or (Path.home() / ".codex" / "auth.json")
    try:
        data = json.loads(auth_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    tokens = data.get("tokens")
    if not isinstance(tokens, dict):
        return ""
    token = tokens.get("access_token")
    return token if isinstance(token, str) and token.strip() else ""


CODEX_OAUTH_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
CODEX_OAUTH_TOKEN_URL = "https://auth.openai.com/oauth/token"
CODEX_DEVICE_ISSUER = "https://auth.openai.com"
CODEX_DEVICE_AUTH_TIMEOUT_SECONDS = 15 * 60


def _urlopen_json(request: urllib.request.Request, *, timeout: float = 15.0) -> Any:
    context = ssl.create_default_context(cafile=certifi.where())
    with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
        return json.loads(response.read().decode("utf-8"))


def _json_post(url: str, payload: dict[str, Any], *, form: bool = False, timeout: float = 15.0) -> dict[str, Any]:
    if form:
        body = urllib.parse.urlencode(payload).encode("utf-8")
        content_type = "application/x-www-form-urlencoded"
    else:
        body = json.dumps(payload).encode("utf-8")
        content_type = "application/json"
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": content_type,
            "Accept": "application/json",
            "User-Agent": "agentick/0.1.0",
        },
        method="POST",
    )
    return _urlopen_json(req, timeout=timeout)


def openai_codex_device_login(*, open_browser: bool = True) -> str:
    """Run the same direct OpenAI Codex device-code flow Hermes uses.

    This intentionally does not shell out to `codex login`: Agentick owns the
    OAuth session and can open the browser itself instead of depending on Codex
    CLI behavior/version flags.
    """
    device_data = _json_post(
        f"{CODEX_DEVICE_ISSUER}/api/accounts/deviceauth/usercode",
        {"client_id": CODEX_OAUTH_CLIENT_ID},
    )
    user_code = str(device_data.get("user_code") or "")
    device_auth_id = str(device_data.get("device_auth_id") or "")
    poll_interval = max(3, int(device_data.get("interval") or 5))
    if not user_code or not device_auth_id:
        raise RuntimeError("OpenAI device-code response was missing required fields.")

    verification_url = f"{CODEX_DEVICE_ISSUER}/codex/device"
    print("To continue, follow these steps:\n")
    print("  1. Open this URL in your browser:")
    print(f"     {CYAN}{verification_url}{RESET}\n")
    print("  2. Enter this code:")
    print(f"     {CYAN}{user_code}{RESET}\n")
    if open_browser:
        try:
            opened = webbrowser.open(verification_url)
        except Exception:
            opened = False
        if opened:
            print("  (Opened browser for verification)")
        else:
            print("  Could not open browser automatically — use the URL above.")
    print("Waiting for sign-in... (press Ctrl+C to cancel)")

    deadline = time.monotonic() + CODEX_DEVICE_AUTH_TIMEOUT_SECONDS
    code_resp: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        time.sleep(poll_interval)
        try:
            code_resp = _json_post(
                f"{CODEX_DEVICE_ISSUER}/api/accounts/deviceauth/token",
                {"device_auth_id": device_auth_id, "user_code": user_code},
            )
            break
        except urllib.error.HTTPError as exc:
            if exc.code in {401, 403, 404}:
                continue
            raise RuntimeError(f"OpenAI device-code polling returned status {exc.code}.") from exc
    if code_resp is None:
        raise TimeoutError("OpenAI sign-in timed out after 15 minutes.")

    authorization_code = str(code_resp.get("authorization_code") or "")
    code_verifier = str(code_resp.get("code_verifier") or "")
    if not authorization_code or not code_verifier:
        raise RuntimeError("OpenAI device auth response was missing authorization_code or code_verifier.")

    token_data = _json_post(
        CODEX_OAUTH_TOKEN_URL,
        {
            "grant_type": "authorization_code",
            "code": authorization_code,
            "redirect_uri": f"{CODEX_DEVICE_ISSUER}/deviceauth/callback",
            "client_id": CODEX_OAUTH_CLIENT_ID,
            "code_verifier": code_verifier,
        },
        form=True,
    )
    access_token = str(token_data.get("access_token") or "").strip()
    if not access_token:
        raise RuntimeError("OpenAI token exchange did not return an access_token.")
    return access_token


def obtain_openai_oauth_token(oauth_env: str) -> str:
    existing = read_codex_access_token()
    if existing:
        print("Found existing OpenAI Codex/ChatGPT credentials at ~/.codex/auth.json.")
        print("Agentick can import them, but a separate Agentick sign-in is recommended.")
        try:
            do_import = input("Import existing credentials? [y/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            do_import = "n"
        if do_import in {"y", "yes"}:
            return existing
    print(oauth_setup_guidance(PROVIDERS["openai"], oauth_env))
    try:
        return openai_codex_device_login(open_browser=True)
    except KeyboardInterrupt:
        print("\nOpenAI sign-in cancelled.", file=sys.stderr)
        return ""
    except Exception as exc:
        print(f"OpenAI device sign-in failed: {exc}", file=sys.stderr)
        print(f"For non-interactive setup, set {oauth_env} or pass --oauth-token.", file=sys.stderr)
        return ""


def setup_cmd(args: argparse.Namespace) -> int:
    selected_slug = args.provider
    selection_auth_method = ""
    if not selected_slug:
        provider_rows = build_provider_choices()
        picked = choose(
            "Select provider:",
            [label for _slug, label in provider_rows],
            "OpenAI (API key)",
            "Current model:    (not set)\nActive provider:  none",
        )
        slug_by_label = {label: slug for slug, label in provider_rows}
        selected_slug = slug_by_label.get(picked, "cancel")
    if selected_slug == "cancel":
        print("No change.")
        return 0
    try:
        provider, selection_auth_method = resolve_provider_selection(selected_slug)
    except ValueError:
        print(f"Unknown provider: {selected_slug}", file=sys.stderr)
        return 2
    meta = PROVIDERS[provider]
    auth_method = args.auth or selection_auth_method or "api_key"
    if auth_method not in meta.get("auth_methods", ["api_key"]):
        print(f"Auth method for {provider} must be one of: {', '.join(meta.get('auth_methods', ['api_key']))}", file=sys.stderr)
        return 2
    model = args.model or choose("Select model", meta["models"], meta["models"][0], "Pick the default model for newly executed tasks.")
    reasoning = args.reasoning
    if not reasoning and not args.no_interactive:
        reasoning = choose("Default reasoning effort", meta["reasoning"], "medium")
    reasoning = reasoning or "medium"
    if reasoning not in meta["reasoning"]:
        print(f"Reasoning effort for {provider} must be one of: {', '.join(meta['reasoning'])}", file=sys.stderr)
        return 2
    secret_fields: dict[str, Any]
    if auth_method == "oauth":
        oauth_env = str(meta["oauth_env"])
        token = args.oauth_token or os.environ.get(oauth_env, "")
        if not token and not args.no_interactive and sys.stdin.isatty():
            if provider == "openai":
                token = obtain_openai_oauth_token(oauth_env)
            else:
                print(f"OAuth path: {meta['oauth_label']}")
                print(f"Paste an access token, or set {oauth_env} before running setup.")
                token = getpass.getpass(f"{meta['label']} OAuth token ({oauth_env}): ").strip()
        if not token:
            print(f"Missing OAuth token. Set {oauth_env} or pass --oauth-token.", file=sys.stderr)
            return 2
        secret_fields = {
            "auth_method": "oauth",
            "oauth_provider": meta["oauth_provider"],
            "oauth_label": meta["oauth_label"],
            "access_token": token,
        }
    else:
        api_key = args.api_key or next((os.environ.get(name, "") for name in provider_env_names(provider) if os.environ.get(name, "")), "")
        if not api_key and meta.get("allow_dummy_key") and args.no_interactive:
            api_key = "dummy-lm-api-key"
        if not api_key and not args.no_interactive and sys.stdin.isatty():
            api_key = getpass.getpass(f"{meta['label']} API key ({provider_env_display(provider)}): ").strip()
        if not api_key:
            print(f"Missing API key. Set {provider_env_display(provider)} or pass --api-key.", file=sys.stderr)
            return 2
        secret_fields = {"auth_method": "api_key", "api_key": api_key}
    config = load_config() or {"providers": {}}
    config.setdefault("providers", {})[provider] = {
        **secret_fields,
        "model": model,
        "reasoning_effort": reasoning,
    }
    config["default_provider"] = provider
    save_config(config)
    paths().tasks.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(paths().tasks, 0o700)
    except OSError:
        pass
    print(banner())
    auth_label = "OAuth" if auth_method == "oauth" else "API key"
    print(f"{GREEN}Provider saved securely:{RESET} {meta['label']} / {auth_label} / {model} / reasoning {reasoning}")
    print(usage_after_setup())
    return 0


def parse_front_matter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n"):
        return {}, text.strip()
    end = text.find("\n---", 4)
    if end == -1:
        return {}, text.strip()
    raw = text[4:end]
    body = text[end + 4 :]
    meta: dict[str, str] = {}
    for line in raw.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            meta[key.strip()] = value.strip().strip('"\'')
    return meta, body.strip()


def truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def normalize_parameter_descriptions(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value]
    if isinstance(value, dict):
        indexed: dict[int, str] = {}
        for key, item in value.items():
            match = re.fullmatch(r"(?:(?:param|parameter|arg)[_-]?)?(\d+)", str(key))
            if match:
                indexed[int(match.group(1))] = str(item).strip()
        if indexed:
            return [indexed.get(idx, "") for idx in range(max(indexed) + 1)]
    return []


def parameter_indices(template: str) -> list[int]:
    found = {int(match.group(1)) for match in re.finditer(r"\{\{(?:arg|file):(\d+)\}\}", template)}
    return sorted(found)


def parameter_description(task: dict[str, Any], idx: int) -> str:
    descriptions = task.get("parameter_descriptions")
    if isinstance(descriptions, list) and idx < len(descriptions) and str(descriptions[idx]).strip():
        return str(descriptions[idx]).strip()
    return f"Parameter {idx + 1}"


def prompt_for_parameter_descriptions(template: str) -> list[str]:
    indices = parameter_indices(template)
    if not indices:
        return []
    descriptions: list[str] = []
    print("Detected task parameters:")
    for idx in indices:
        label = f"Parameter {idx + 1} description (for {{{{arg:{idx}}}}}/{{{{file:{idx}}}}}; blank to skip): "
        descriptions.append(input(label).strip())
    return descriptions


def parameter_editor_initial(idx: int, description: str, value: str = "") -> str:
    return textwrap.dedent(
        f"""
        # Parameter {idx + 1}: {description}
        # Do not edit or delete this heading. Agentick uses it to scrape the argument.
        # Write/paste the full argument below the marker, then save and quit.
        --- AGENTICK ARGUMENT VALUE BELOW ---
        {value}
        """
    ).lstrip()


def parse_parameter_editor_value(text: str) -> str:
    marker = "--- AGENTICK ARGUMENT VALUE BELOW ---"
    if marker in text:
        return text.split(marker, 1)[1].strip()
    lines = text.splitlines()
    while lines and lines[0].lstrip().startswith("#"):
        lines.pop(0)
    return "\n".join(lines).strip()


def collect_editor_arguments(task: dict[str, Any], argv: list[str]) -> list[str]:
    indices = parameter_indices(str(task.get("user_prompt", "")))
    if not indices:
        indices = list(range(len(argv)))
    if not indices:
        raise ValueError("--edit-args needs explicit {{arg:N}}/{{file:N}} placeholders or at least one existing argument to edit.")
    edited = list(argv)
    for idx in indices:
        while len(edited) <= idx:
            edited.append("")
        description = parameter_description(task, idx)
        initial = parameter_editor_initial(idx, description, edited[idx])
        edited[idx] = parse_parameter_editor_value(open_editor(initial))
    return edited


def parse_prompt_file(path: Path) -> dict[str, Any]:
    if path.suffix.lower() not in {".txt", ".md", ".yaml", ".yml", ".json"}:
        raise ValueError("Only .txt, .md, .yaml, or .json prompt files are accepted")
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        data = json.loads(text)
        return {
            "system_prompt": str(data.get("system") or data.get("system_prompt") or "").strip(),
            "user_prompt": str(data.get("user") or data.get("user_prompt") or "").strip(),
            "routine": data.get("routine"),
            "model": data.get("model"),
            "reasoning_effort": data.get("reasoning") or data.get("reasoning_effort"),
            "agent": truthy(data.get("agent")),
            "parameter_descriptions": normalize_parameter_descriptions(data.get("parameter_descriptions") or data.get("parameters") or data),
        }
    if path.suffix.lower() in {".yaml", ".yml"}:
        data: dict[str, Any] = {}
        current = None
        buf: list[str] = []
        for line in text.splitlines():
            if line.startswith("system:") or line.startswith("system_prompt:") or line.startswith("user:") or line.startswith("user_prompt:") or line.startswith("model:") or line.startswith("reasoning:") or line.startswith("reasoning_effort:") or line.startswith("agent:") or line.startswith("routine:"):
                if current:
                    data[current] = "\n".join(buf).strip()
                current, value = line.split(":", 1)
                current = current.strip()
                buf = [value.strip().strip('"\'')] if value.strip() else []
            elif current:
                buf.append(line.removeprefix("  "))
        if current:
            data[current] = "\n".join(buf).strip()
        return {
            "system_prompt": str(data.get("system") or data.get("system_prompt") or "").strip(),
            "user_prompt": str(data.get("user") or data.get("user_prompt") or text).strip(),
            "model": data.get("model"),
            "reasoning_effort": data.get("reasoning") or data.get("reasoning_effort"),
            "agent": truthy(data.get("agent")),
            "routine": data.get("routine"),
            "parameter_descriptions": normalize_parameter_descriptions(data),
        }
    meta, body = parse_front_matter(text)
    return {
        "system_prompt": meta.get("system", ""),
        "user_prompt": body,
        "model": meta.get("model"),
        "reasoning_effort": meta.get("reasoning") or meta.get("reasoning_effort"),
        "agent": truthy(meta.get("agent")),
        "routine": meta.get("routine"),
        "parameter_descriptions": normalize_parameter_descriptions(meta),
    }


def open_editor(initial: str = "") -> str:
    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR") or "vim"
    with tempfile.NamedTemporaryFile("w+", suffix=".md", delete=False) as handle:
        handle.write(initial)
        handle.flush()
        temp = handle.name
    try:
        subprocess.run([editor, temp], check=False)
        return Path(temp).read_text(encoding="utf-8").strip()
    finally:
        try:
            Path(temp).unlink()
        except OSError:
            pass


def valid_task_name(name: str) -> bool:
    return bool(re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,80}", name))


def choose_task_model(provider: str, config: dict[str, Any] | None, explicit_model: str | None, parsed_model: str | None, no_interactive: bool) -> str | None:
    if explicit_model or parsed_model:
        return explicit_model or parsed_model
    if no_interactive:
        return None
    provider_default = str(provider_config(config or {}, provider).get("model") or PROVIDERS[provider]["models"][0])
    default_label = f"Provider default ({provider_default})"
    custom_label = "Custom model name..."
    options = [default_label, *PROVIDERS[provider]["models"], custom_label]
    picked = choose("Model for this task", options, default_label, "Pick a task-specific model, or keep the provider default.")
    if picked == default_label:
        return None
    if picked == custom_label:
        try:
            custom = input("Model name: ").strip()
        except (KeyboardInterrupt, EOFError):
            return None
        return custom or None
    return picked


def new_cmd(args: argparse.Namespace) -> int:
    cfg = load_config()
    provider_names = list((cfg or {}).get("providers", {}).keys())
    provider = args.provider or ((cfg or {}).get("default_provider") if cfg else None)
    if not provider and len(provider_names) == 1:
        provider = provider_names[0]
    if not provider and not args.no_interactive:
        provider = choose("Provider for this task", provider_names or list(PROVIDERS), provider_names[0] if provider_names else "openai")
    provider = provider or "openai"
    if provider not in PROVIDERS:
        print(f"Unknown provider: {provider}", file=sys.stderr)
        return 2

    try:
        if args.prompt_file:
            parsed = parse_prompt_file(Path(args.prompt_file))
        elif not args.no_interactive:
            mode = choose("Prompt source", ["one-line", "editor"], "one-line")
            if mode == "editor":
                parsed = {"system_prompt": "", "user_prompt": open_editor()}
            else:
                parsed = {"system_prompt": input("System prompt (optional): ").strip(), "user_prompt": input("User prompt: ").strip()}
        else:
            print("new requires a prompt file in --no-interactive mode", file=sys.stderr)
            return 2
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled.", file=sys.stderr)
        return 130
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    reasoning = args.reasoning or parsed.get("reasoning_effort")
    if not reasoning and not args.no_interactive:
        reasoning = choose("Reasoning effort (Enter to use provider default at runtime)", PROVIDERS[provider]["reasoning"], "medium")
    if reasoning and reasoning not in PROVIDERS[provider]["reasoning"]:
        print(f"Reasoning effort for {provider} must be one of: {', '.join(PROVIDERS[provider]['reasoning'])}", file=sys.stderr)
        return 2
    parameter_descriptions = normalize_parameter_descriptions(parsed.get("parameter_descriptions"))
    if not args.no_interactive:
        try:
            prompted_descriptions = prompt_for_parameter_descriptions(str(parsed.get("user_prompt", "")))
        except (KeyboardInterrupt, EOFError):
            print("\nCancelled.", file=sys.stderr)
            return 130
        if prompted_descriptions:
            parameter_descriptions = prompted_descriptions

    name = args.name
    if not name and not args.no_interactive:
        name = input("Task name (e.g. say-hello): ").strip()
    if not name or not valid_task_name(name):
        print("Task name must be 1-81 chars: letters, numbers, dot, underscore, dash.", file=sys.stderr)
        return 2
    task = {
        "name": name,
        "provider": provider,
        "system_prompt": parsed.get("system_prompt", ""),
        "user_prompt": parsed.get("user_prompt", ""),
    }
    if args.agent or parsed.get("agent"):
        task["agent"] = True
    model = choose_task_model(provider, cfg, args.model, parsed.get("model"), args.no_interactive)
    if model:
        task["model"] = model
    if reasoning:
        task["reasoning_effort"] = reasoning
    if parameter_descriptions and any(parameter_descriptions):
        task["parameter_descriptions"] = parameter_descriptions
    if parsed.get("routine"):
        task["routine"] = parsed["routine"]
    paths().tasks.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(paths().tasks, 0o700)
    except OSError:
        pass
    secure_write(paths().tasks / f"{name}.json", json.dumps(task, indent=2, sort_keys=True) + "\n")
    print(banner())
    print(f"{GREEN}Task saved:{RESET} agc {name}")
    return 0


def task_path(name: str) -> Path:
    return paths().tasks / f"{name}.json"


def load_task(name: str) -> dict[str, Any] | None:
    p = task_path(name)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def scalar_meta_line(key: str, value: Any) -> str:
    text = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'{key}: "{text}"'


def task_to_prompt_markdown(task: dict[str, Any]) -> str:
    meta: list[str] = []
    if task.get("system_prompt"):
        meta.append(scalar_meta_line("system", task.get("system_prompt", "")))
    if task.get("model"):
        meta.append(scalar_meta_line("model", task["model"]))
    if task.get("reasoning_effort"):
        meta.append(scalar_meta_line("reasoning", task["reasoning_effort"]))
    if task.get("agent"):
        meta.append("agent: true")
    if task.get("routine"):
        meta.append(scalar_meta_line("routine", task["routine"]))
    descriptions = normalize_parameter_descriptions(task.get("parameter_descriptions"))
    for idx, description in enumerate(descriptions):
        if description:
            meta.append(scalar_meta_line(f"param_{idx}", description))
    body = str(task.get("user_prompt", "")).rstrip()
    if not meta:
        return body + "\n"
    return "---\n" + "\n".join(meta) + "\n---\n" + body + "\n"


def build_task_from_parsed(name: str, provider: str, parsed: dict[str, Any], *, agent_override: bool | None = None, reasoning_override: str | None = None, model_override: str | None = None) -> dict[str, Any]:
    task: dict[str, Any] = {
        "name": name,
        "provider": provider,
        "system_prompt": parsed.get("system_prompt", ""),
        "user_prompt": parsed.get("user_prompt", ""),
    }
    use_agent = parsed.get("agent") if agent_override is None else agent_override
    if use_agent:
        task["agent"] = True
    model = model_override or parsed.get("model")
    if model:
        task["model"] = model
    reasoning = reasoning_override or parsed.get("reasoning_effort")
    if reasoning:
        task["reasoning_effort"] = reasoning
    descriptions = normalize_parameter_descriptions(parsed.get("parameter_descriptions"))
    if descriptions and any(descriptions):
        task["parameter_descriptions"] = descriptions
    if parsed.get("routine"):
        task["routine"] = parsed["routine"]
    return task


def save_task(task: dict[str, Any]) -> None:
    paths().tasks.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(paths().tasks, 0o700)
    except OSError:
        pass
    secure_write(task_path(str(task["name"])), json.dumps(task, indent=2, sort_keys=True) + "\n")


def detected_scheduler() -> str:
    system = platform.system().lower()
    if system == "darwin":
        return "launchd"
    if system == "linux":
        return "cron"
    return "manual"


def routine_interval_seconds(every: str) -> int:
    text = every.strip().lower()
    aliases = {"hourly": 3600, "daily": 86400, "weekly": 604800}
    if text in aliases:
        return aliases[text]
    match = re.fullmatch(r"(\d+)\s*([smhdw])", text)
    if not match:
        raise ValueError("Routine interval must look like 15m, 1h, daily, hourly, or weekly.")
    value = int(match.group(1))
    unit = match.group(2)
    multiplier = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}[unit]
    seconds = value * multiplier
    if seconds < 60:
        raise ValueError("Routine interval must be at least 60 seconds.")
    return seconds


def routine_cron_expression(every: str) -> str:
    seconds = routine_interval_seconds(every)
    minutes = max(1, seconds // 60)
    if minutes < 60:
        return f"*/{minutes} * * * *"
    if minutes % 1440 == 0:
        return "0 9 * * *"
    if minutes % 60 == 0 and minutes < 1440:
        return f"0 */{minutes // 60} * * *"
    raise ValueError("Cron routines currently support minute/hour/day intervals such as 15m, 2h, or daily.")


def routine_label(name: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "-", name)
    return f"com.agentick.routine.{safe}"


def routine_artifacts(name: str) -> dict[str, Path]:
    base = paths().routines
    return {
        "script": base / f"{name}.sh",
        "plist": base / f"{name}.plist",
        "cron": base / f"{name}.cron",
        "log": base / f"{name}.log",
    }


def routine_permissions_from_args(args: argparse.Namespace) -> dict[str, bool]:
    return {
        "agent": bool(getattr(args, "agent", False)),
        "allow_write": bool(getattr(args, "allow_write", False)),
        "allow_shell": bool(getattr(args, "allow_shell", False)),
        "allow_net": bool(getattr(args, "allow_net", False)),
        "allow_commit": bool(getattr(args, "allow_commit", False)),
    }


def routine_run_argv(name: str, routine: dict[str, Any]) -> list[str]:
    command = [str(routine.get("python") or sys.executable), "-m", "agentick", name, "--headless"]
    for arg in routine.get("args") or []:
        command.append(str(arg))
    permissions = routine.get("permissions") or {}
    if permissions.get("agent"):
        command.append("--agent")
    if permissions.get("allow_write"):
        command.append("--allow-write")
    if permissions.get("allow_shell"):
        command.append("--allow-shell")
    if permissions.get("allow_net"):
        command.append("--allow-net")
    if permissions.get("allow_commit"):
        command.append("--allow-commit")
    return command


def write_routine_artifacts(name: str, routine: dict[str, Any]) -> dict[str, Path]:
    paths().routines.mkdir(parents=True, exist_ok=True)
    artifacts = routine_artifacts(name)
    cwd = str(routine.get("cwd") or Path.cwd())
    env_home = str(paths().home)
    command = " ".join(shlex.quote(part) for part in routine_run_argv(name, routine))
    script = textwrap.dedent(f"""
        #!/bin/sh
        cd {shlex.quote(cwd)} || exit 1
        export AGENTICK_HOME={shlex.quote(env_home)}
        exec {command} >> {shlex.quote(str(artifacts['log']))} 2>&1
        """).lstrip()
    secure_write(artifacts["script"], script)
    artifacts["script"].chmod(0o700)
    scheduler = str(routine.get("scheduler") or detected_scheduler())
    if scheduler == "launchd":
        plist = {
            "Label": routine_label(name),
            "ProgramArguments": ["/bin/sh", str(artifacts["script"])],
            "StartInterval": routine_interval_seconds(str(routine.get("every", "1h"))),
            "StandardOutPath": str(artifacts["log"]),
            "StandardErrorPath": str(artifacts["log"]),
        }
        secure_write(artifacts["plist"], plistlib.dumps(plist).decode("utf-8"))
    elif scheduler == "cron":
        expression = routine.get("cron") or routine_cron_expression(str(routine.get("every", "1h")))
        secure_write(artifacts["cron"], f"{expression} /bin/sh {shlex.quote(str(artifacts['script']))}\n")
    return artifacts


def install_routine_schedule(name: str, routine: dict[str, Any]) -> None:
    artifacts = write_routine_artifacts(name, routine)
    scheduler = str(routine.get("scheduler") or detected_scheduler())
    if scheduler == "manual":
        return
    if scheduler == "launchd":
        launch_agents = Path.home() / "Library" / "LaunchAgents"
        launch_agents.mkdir(parents=True, exist_ok=True)
        target = launch_agents / f"{routine_label(name)}.plist"
        target.write_text(artifacts["plist"].read_text(encoding="utf-8"), encoding="utf-8")
        subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}", str(target)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=30)
        proc = subprocess.run(["launchctl", "bootstrap", f"gui/{os.getuid()}", str(target)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=30)
        if proc.returncode != 0:
            raise RuntimeError(proc.stdout.strip() or "launchctl bootstrap failed")
        return
    if scheduler == "cron":
        marker_start = f"# AGENTICK routine {name} start"
        marker_end = f"# AGENTICK routine {name} end"
        existing = subprocess.run(["crontab", "-l"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=30)
        current = existing.stdout if existing.returncode == 0 else ""
        block = f"{marker_start}\n{artifacts['cron'].read_text(encoding='utf-8').rstrip()}\n{marker_end}\n"
        cleaned = re.sub(re.escape(marker_start) + r".*?" + re.escape(marker_end) + r"\n?", "", current, flags=re.S)
        proc = subprocess.run(["crontab", "-"], input=cleaned.rstrip() + "\n" + block, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=30)
        if proc.returncode != 0:
            raise RuntimeError(proc.stdout.strip() or "crontab install failed")
        return
    raise ValueError(f"Unsupported scheduler: {scheduler}")


def stop_routine_schedule(name: str, routine: dict[str, Any]) -> None:
    scheduler = str(routine.get("scheduler") or detected_scheduler())
    if scheduler == "launchd":
        target = Path.home() / "Library" / "LaunchAgents" / f"{routine_label(name)}.plist"
        subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}", str(target)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=30)
        return
    if scheduler == "cron":
        marker_start = f"# AGENTICK routine {name} start"
        marker_end = f"# AGENTICK routine {name} end"
        existing = subprocess.run(["crontab", "-l"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=30)
        current = existing.stdout if existing.returncode == 0 else ""
        cleaned = re.sub(re.escape(marker_start) + r".*?" + re.escape(marker_end) + r"\n?", "", current, flags=re.S)
        subprocess.run(["crontab", "-"], input=cleaned, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=30)


def update_routine_task(name: str, routine: dict[str, Any]) -> dict[str, Any] | None:
    task = load_task(name)
    if task is None:
        return None
    task["routine"] = routine
    save_task(task)
    return task


def clear_routine_task(name: str) -> dict[str, Any] | None:
    task = load_task(name)
    if task is None:
        return None
    task.pop("routine", None)
    save_task(task)
    return task


def delete_cmd(args: argparse.Namespace) -> int:
    name = args.name
    if not name or not valid_task_name(name):
        print("Task name must be 1-81 chars: letters, numbers, dot, underscore, dash.", file=sys.stderr)
        return 2
    path = task_path(name)
    if not path.exists():
        print(f"Unknown task: {name}", file=sys.stderr)
        return 2
    if not getattr(args, "yes", False):
        if getattr(args, "no_interactive", False) or not sys.stdin.isatty():
            print(f"Refusing to delete task {name!r} without --yes in non-interactive mode.", file=sys.stderr)
            return 2
        try:
            answer = input(f"Delete task {name!r}? Type the task name to confirm: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nCancelled.", file=sys.stderr)
            return 130
        if answer != name:
            print("Delete cancelled.")
            return 0
    try:
        path.unlink()
    except OSError as exc:
        print(f"Could not delete task {name}: {exc}", file=sys.stderr)
        return 1
    print(banner())
    print(f"{GREEN}Task deleted:{RESET} {name}")
    return 0


def edit_cmd(args: argparse.Namespace) -> int:
    cfg = load_config()
    name = args.name
    if not name or not valid_task_name(name):
        print("Task name must be 1-81 chars: letters, numbers, dot, underscore, dash.", file=sys.stderr)
        return 2
    existing = load_task(name)
    if existing is None:
        print(f"Unknown task: {name}", file=sys.stderr)
        return 2
    provider = args.provider or existing.get("provider") or ((cfg or {}).get("default_provider") if cfg else None) or "openai"
    if provider not in PROVIDERS:
        print(f"Unknown provider: {provider}", file=sys.stderr)
        return 2
    reasoning = args.reasoning
    if reasoning and reasoning not in PROVIDERS[provider]["reasoning"]:
        print(f"Reasoning effort for {provider} must be one of: {', '.join(PROVIDERS[provider]['reasoning'])}", file=sys.stderr)
        return 2
    agent_override: bool | None = None
    if getattr(args, "agent", False):
        agent_override = True
    if getattr(args, "no_agent", False):
        agent_override = False
    try:
        if args.prompt_file:
            parsed = parse_prompt_file(Path(args.prompt_file))
        elif not args.no_interactive:
            edited = open_editor(task_to_prompt_markdown(existing))
            if not edited.strip():
                print("Edit cancelled: task content was empty.", file=sys.stderr)
                return 2
            with tempfile.NamedTemporaryFile("w+", suffix=".md", delete=False) as handle:
                handle.write(edited)
                handle.flush()
                temp = Path(handle.name)
            try:
                parsed = parse_prompt_file(temp)
            finally:
                try:
                    temp.unlink()
                except OSError:
                    pass
        else:
            print("edit requires a prompt file in --no-interactive mode", file=sys.stderr)
            return 2
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled.", file=sys.stderr)
        return 130
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    task = build_task_from_parsed(
        name,
        provider,
        parsed,
        agent_override=agent_override,
        reasoning_override=reasoning,
        model_override=args.model,
    )
    save_task(task)
    print(banner())
    print(f"{GREEN}Task updated:{RESET} agc {name}")
    return 0


def read_slice(slug: str) -> str:
    # ./file.js:L1..L2, ./file.js:1..2, or just ./file.js
    match = re.match(r"^(.*?)(?::L?(\d+)\.\.L?(\d+))?$", slug)
    if not match:
        return slug
    file_part, start, end = match.groups()
    path = Path(file_part).expanduser()
    if not path.exists() or not path.is_file():
        return slug
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if start and end:
        selected = lines[int(start) - 1 : int(end)]
    else:
        selected = lines
    return "\n".join(f"{idx} > {line}" for idx, line in enumerate(selected, int(start or 1)))


def render_prompt(template: str, argv: list[str]) -> str:
    rendered = template
    for idx, value in enumerate(argv):
        rendered = rendered.replace(f"{{{{arg:{idx}}}}}", value)
        rendered = rendered.replace(f"{{{{file:{idx}}}}}", read_slice(value))
    # Convenience: if no explicit placeholder but args exist, append them.
    if argv and "{{arg:" not in template and "{{file:" not in template:
        rendered += "\n\nArguments:\n" + "\n".join(argv)
    return rendered


def provider_key(config: dict[str, Any], provider: str) -> str:
    provider_cfg = ((config.get("providers") or {}).get(provider) or {})
    saved = provider_cfg.get("access_token", "") if provider_cfg.get("auth_method") == "oauth" else provider_cfg.get("api_key", "")
    oauth_env = PROVIDERS[provider].get("oauth_env", "") if provider_cfg.get("auth_method") == "oauth" else ""
    if oauth_env and os.environ.get(oauth_env):
        return os.environ[oauth_env]
    for env_name in provider_env_names(provider):
        if os.environ.get(env_name):
            return os.environ[env_name]
    return saved


def provider_config(config: dict[str, Any], provider: str) -> dict[str, Any]:
    value = (config.get("providers") or {}).get(provider) or {}
    return value if isinstance(value, dict) else {}


def internet_connected(timeout: float = 5.0) -> tuple[bool, str]:
    request = urllib.request.Request(
        "https://www.gstatic.com/generate_204",
        headers={"User-Agent": "agentick/0.1.0"},
        method="GET",
    )
    try:
        context = ssl.create_default_context(cafile=certifi.where())
        with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
            if 200 <= response.status < 400:
                return True, ""
            return False, f"internet check returned HTTP {response.status}"
    except Exception as exc:
        return False, str(exc)


def provider_readiness_error(config: dict[str, Any] | None, provider: str | None = None, *, check_network: bool = True) -> str:
    if not isinstance(config, dict):
        return "Agentick has not been set up yet."
    providers = config.get("providers")
    if not isinstance(providers, dict) or not providers:
        return "No AI provider is configured."
    selected = provider or config.get("default_provider")
    if not isinstance(selected, str) or not selected:
        return "No default AI provider is configured."
    if selected not in PROVIDERS:
        return f"Configured AI provider is unknown: {selected}."
    if not isinstance(providers.get(selected), dict):
        return f"AI provider is not configured: {selected}."
    if not provider_key(config, selected):
        cfg = provider_config(config, selected)
        if cfg.get("auth_method") == "oauth":
            return f"Missing OAuth token for {selected}."
        return f"Missing API key for {selected}."
    if check_network:
        ok, detail = internet_connected()
        if not ok:
            return f"Internet check failed: {detail}"
    return ""


def enforce_ready_or_setup(config: dict[str, Any] | None = None, provider: str | None = None, *, check_network: bool = True) -> bool:
    error = provider_readiness_error(config if config is not None else load_config(), provider, check_network=check_network)
    if not error:
        return True
    print(f"{RED}Agentick is not ready: {error}{RESET}", file=sys.stderr)
    print("Run `agc setup` and complete a working AI provider before using Agentick.", file=sys.stderr)
    return False


def resolved_model(task: dict[str, Any], config: dict[str, Any], provider: str) -> str:
    return str(task.get("model") or provider_config(config, provider).get("model") or PROVIDERS[provider]["models"][0])


def resolved_reasoning_effort(task: dict[str, Any], config: dict[str, Any], provider: str) -> str:
    return str(task.get("reasoning_effort") or provider_config(config, provider).get("reasoning_effort") or "medium")


AI_USAGE_EVENTS: list[dict[str, Any]] = []


def reset_ai_usage() -> None:
    AI_USAGE_EVENTS.clear()


def usage_number(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return None


def normalize_openai_usage(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    result: dict[str, Any] = {
        "input_tokens": usage_number(raw.get("prompt_tokens") or raw.get("input_tokens")),
        "output_tokens": usage_number(raw.get("completion_tokens") or raw.get("output_tokens")),
        "total_tokens": usage_number(raw.get("total_tokens")),
    }
    details: dict[str, Any] = {}
    for key in ["prompt_tokens_details", "completion_tokens_details", "input_tokens_details", "output_tokens_details"]:
        if isinstance(raw.get(key), dict):
            details[key] = raw[key]
    if details:
        result["details"] = details
    return {key: value for key, value in result.items() if value is not None and value != {}}


def normalize_gemini_usage(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    result = {
        "input_tokens": usage_number(raw.get("promptTokenCount")),
        "output_tokens": usage_number(raw.get("candidatesTokenCount")),
        "total_tokens": usage_number(raw.get("totalTokenCount")),
    }
    return {key: value for key, value in result.items() if value is not None}


def record_ai_usage(provider: str, model: str, reasoning: str, usage: dict[str, Any] | None) -> None:
    event = {"provider": provider, "model": model, "reasoning_effort": reasoning or "provider default"}
    if usage:
        event.update(usage)
    AI_USAGE_EVENTS.append(event)


def consume_ai_usage() -> list[dict[str, Any]]:
    events = [dict(item) for item in AI_USAGE_EVENTS]
    AI_USAGE_EVENTS.clear()
    return events


def aggregate_usage(events: list[dict[str, Any]]) -> dict[str, int]:
    totals = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    for event in events:
        for key in totals:
            value = usage_number(event.get(key))
            if value is not None:
                totals[key] += value
    return totals


def format_usage_log(events: list[dict[str, Any]]) -> list[str]:
    if not events:
        return []
    totals = aggregate_usage(events)
    lines = ["## Usage", ""]
    if any(totals.values()):
        lines.extend([
            f"Total tokens: {totals['total_tokens']}",
            f"Input tokens: {totals['input_tokens']}",
            f"Output tokens: {totals['output_tokens']}",
            "",
        ])
    else:
        lines.extend(["Token counts: not reported by provider or mock response.", ""])
    lines.extend(["| Call | Provider | Model | Reasoning | Input | Output | Total |", "| --- | --- | --- | --- | ---: | ---: | ---: |"])
    for idx, event in enumerate(events, 1):
        lines.append(
            "| {idx} | {provider} | {model} | {reasoning} | {input} | {output} | {total} |".format(
                idx=idx,
                provider=event.get("provider", ""),
                model=event.get("model", ""),
                reasoning=event.get("reasoning_effort", ""),
                input=event.get("input_tokens", "—"),
                output=event.get("output_tokens", "—"),
                total=event.get("total_tokens", "—"),
            )
        )
    lines.append("")
    return lines


def supports_reasoning_effort(provider: str, model: str) -> bool:
    if provider == "grok":
        return True
    if provider != "openai":
        return False
    normalized = model.lower()
    return normalized.startswith(("o1", "o3", "o4", "gpt-5"))


def is_openai_compatible(provider: str) -> bool:
    return str(PROVIDERS[provider].get("api") or "openai") == "openai"


def anthropic_headers(config: dict[str, Any], provider: str) -> dict[str, str]:
    key = provider_key(config, provider)
    if provider == "anthropic":
        return {
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
    return {
        "Authorization": f"Bearer {key}",
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }


def extract_anthropic_text(data: dict[str, Any]) -> str:
    parts = data.get("content")
    if isinstance(parts, list):
        texts = [str(part.get("text", "")) for part in parts if isinstance(part, dict) and part.get("type") in {"text", None}]
        if texts:
            return "".join(texts)
    return str(data.get("text") or "")


def normalize_anthropic_usage(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    input_tokens = usage_number(raw.get("input_tokens"))
    output_tokens = usage_number(raw.get("output_tokens"))
    result = {"input_tokens": input_tokens, "output_tokens": output_tokens}
    if input_tokens is not None and output_tokens is not None:
        result["total_tokens"] = input_tokens + output_tokens
    return {key: value for key, value in result.items() if value is not None}


def call_openai_compatible(provider: str, task: dict[str, Any], config: dict[str, Any], prompt: str) -> str:
    meta = PROVIDERS[provider]
    model = resolved_model(task, config, provider)
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": task.get("system_prompt", "")},
            {"role": "user", "content": prompt},
        ],
    }
    reasoning = resolved_reasoning_effort(task, config, provider)
    if reasoning and supports_reasoning_effort(provider, model):
        payload["reasoning_effort"] = reasoning
    request = urllib.request.Request(
        meta["url"],
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {provider_key(config, provider)}", "Content-Type": "application/json"},
        method="POST",
    )
    data = _urlopen_json(request, timeout=120)
    record_ai_usage(provider, model, reasoning, normalize_openai_usage(data.get("usage")))
    return data["choices"][0]["message"]["content"]


def call_anthropic(provider: str, task: dict[str, Any], config: dict[str, Any], prompt: str) -> str:
    meta = PROVIDERS[provider]
    model = resolved_model(task, config, provider)
    payload: dict[str, Any] = {
        "model": model,
        "max_tokens": 4096,
        "messages": [{"role": "user", "content": prompt}],
    }
    if task.get("system_prompt"):
        payload["system"] = str(task.get("system_prompt", ""))
    request = urllib.request.Request(
        meta["url"],
        data=json.dumps(payload).encode(),
        headers=anthropic_headers(config, provider),
        method="POST",
    )
    data = _urlopen_json(request, timeout=120)
    reasoning = resolved_reasoning_effort(task, config, provider)
    record_ai_usage(provider, model, reasoning, normalize_anthropic_usage(data.get("usage")))
    return extract_anthropic_text(data)


def http_error_detail(exc: urllib.error.HTTPError) -> str:
    try:
        body = exc.read().decode("utf-8", errors="replace").strip()
    except Exception:
        body = ""
    if not body:
        return str(exc)
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        return f"HTTP {exc.code}: {body}"
    error = parsed.get("error") if isinstance(parsed, dict) else None
    if isinstance(error, dict):
        message = error.get("message") or error.get("code") or body
        return f"HTTP {exc.code}: {message}"
    return f"HTTP {exc.code}: {body}"


def call_gemini(task: dict[str, Any], config: dict[str, Any], prompt: str) -> str:
    model = resolved_model(task, config, "gemini")
    key = provider_key(config, "gemini")
    url = PROVIDERS["gemini"]["url_template"].format(model=model, key=key)
    parts = []
    if task.get("system_prompt"):
        parts.append({"text": f"System: {task['system_prompt']}"})
    parts.append({"text": prompt})
    request = urllib.request.Request(
        url,
        data=json.dumps({"contents": [{"parts": parts}]}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    data = _urlopen_json(request, timeout=120)
    record_ai_usage("gemini", model, resolved_reasoning_effort(task, config, "gemini"), normalize_gemini_usage(data.get("usageMetadata")))
    return data["candidates"][0]["content"]["parts"][0]["text"]


def call_ai(task: dict[str, Any], config: dict[str, Any], prompt: str) -> str:
    if os.environ.get("AGC_MOCK_RESPONSE"):
        provider = str(task.get("provider") or config.get("default_provider") or "mock")
        model = resolved_model(task, config, provider) if provider in PROVIDERS else "mock"
        reasoning = resolved_reasoning_effort(task, config, provider) if provider in PROVIDERS else "mock"
        usage = normalize_openai_usage(json.loads(os.environ.get("AGC_MOCK_USAGE_JSON", "{}")))
        record_ai_usage(provider, model, reasoning, usage)
        return os.environ["AGC_MOCK_RESPONSE"]
    provider = task.get("provider") or config.get("default_provider")
    if not provider:
        raise RuntimeError("No provider configured. Run agc setup.")
    if not provider_key(config, provider):
        provider_cfg = provider_config(config, provider)
        if provider_cfg.get("auth_method") == "oauth":
            raise RuntimeError(f"Missing OAuth token for {provider}. Run agc setup or set {PROVIDERS[provider]['oauth_env']}.")
        raise RuntimeError(f"Missing API key for {provider}. Run agc setup or set {provider_env_display(provider)}.")
    if provider == "gemini":
        return call_gemini(task, config, prompt)
    if str(PROVIDERS[provider].get("api")) == "anthropic":
        return call_anthropic(provider, task, config, prompt)
    if is_openai_compatible(provider):
        return call_openai_compatible(provider, task, config, prompt)
    raise RuntimeError(f"Unsupported provider: {provider}")



AGENT_MAX_STEPS = 12
AGENT_TOOL_SCHEMA = """
Agentic mode protocol:
Return exactly one JSON object, no markdown fences.
To use a tool:
  {"thought":"why this is the next safe step","tool":{"name":"read_file","args":{"path":"src/app.py"}}}
To finish:
  {"final":"concise result for the user, including files changed and verification."}

Available tools:
- read_file {"path": str, "start": int optional, "end": int optional}
- write_file {"path": str, "content": str}                 requires write permission
- patch_file {"path": str, "old": str, "new": str}         requires write permission
- shell {"command": str}                                     requires shell permission
- curl {"url": str, "method": "GET|POST" optional, "body": str optional, "headers": dict optional} requires network permission
- git_status {}
- git_diff {}
- git_commit {"message": str}                               requires commit permission

Rules:
- Inspect before editing. Prefer patch_file over write_file for existing files.
- Run verification after edits when possible.
- Never invent tool results. Use final only after enough observations.
- Keep commands non-interactive and scoped to the current working directory.
""".strip()

@dataclass
class AgentPermissions:
    write: bool = False
    shell: bool = False
    net: bool = False
    commit: bool = False


def call_ai_messages(task: dict[str, Any], config: dict[str, Any], messages: list[dict[str, str]]) -> str:
    if os.environ.get("AGC_MOCK_AGENT_RESPONSES"):
        provider = str(task.get("provider") or config.get("default_provider") or "mock")
        model = resolved_model(task, config, provider) if provider in PROVIDERS else "mock"
        reasoning = resolved_reasoning_effort(task, config, provider) if provider in PROVIDERS else "mock"
        usage = normalize_openai_usage(json.loads(os.environ.get("AGC_MOCK_USAGE_JSON", "{}")))
        responses = json.loads(os.environ["AGC_MOCK_AGENT_RESPONSES"])
        idx_path = paths().home / "mock_agent_index.txt"
        try:
            idx = int(idx_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            idx = 0
        response = responses[min(idx, len(responses) - 1)]
        secure_write(idx_path, str(idx + 1))
        record_ai_usage(provider, model, reasoning, usage)
        return response if isinstance(response, str) else json.dumps(response)
    if os.environ.get("AGC_MOCK_RESPONSE"):
        provider = str(task.get("provider") or config.get("default_provider") or "mock")
        model = resolved_model(task, config, provider) if provider in PROVIDERS else "mock"
        reasoning = resolved_reasoning_effort(task, config, provider) if provider in PROVIDERS else "mock"
        usage = normalize_openai_usage(json.loads(os.environ.get("AGC_MOCK_USAGE_JSON", "{}")))
        record_ai_usage(provider, model, reasoning, usage)
        return os.environ["AGC_MOCK_RESPONSE"]
    provider = task.get("provider") or config.get("default_provider")
    if not provider:
        raise RuntimeError("No provider configured. Run agc setup.")
    if provider == "gemini":
        prompt = "\n\n".join(f"{m['role'].upper()}: {m['content']}" for m in messages)
        return call_gemini({**task, "system_prompt": ""}, config, prompt)
    if str(PROVIDERS[provider].get("api")) == "anthropic":
        system = "\n\n".join(m["content"] for m in messages if m.get("role") == "system")
        anthropic_messages = [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages if m.get("role") != "system"]
        meta = PROVIDERS[provider]
        model = resolved_model(task, config, provider)
        payload: dict[str, Any] = {"model": model, "max_tokens": 4096, "messages": anthropic_messages or [{"role": "user", "content": ""}]}
        if system:
            payload["system"] = system
        reasoning = resolved_reasoning_effort(task, config, provider)
        request = urllib.request.Request(meta["url"], data=json.dumps(payload).encode(), headers=anthropic_headers(config, provider), method="POST")
        data = _urlopen_json(request, timeout=120)
        record_ai_usage(provider, model, reasoning, normalize_anthropic_usage(data.get("usage")))
        return extract_anthropic_text(data)
    if is_openai_compatible(provider):
        meta = PROVIDERS[provider]
        model = resolved_model(task, config, provider)
        payload: dict[str, Any] = {"model": model, "messages": messages}
        reasoning = resolved_reasoning_effort(task, config, provider)
        if reasoning and supports_reasoning_effort(provider, model):
            payload["reasoning_effort"] = reasoning
        request = urllib.request.Request(
            meta["url"],
            data=json.dumps(payload).encode(),
            headers={"Authorization": f"Bearer {provider_key(config, provider)}", "Content-Type": "application/json"},
            method="POST",
        )
        data = _urlopen_json(request, timeout=120)
        record_ai_usage(provider, model, reasoning, normalize_openai_usage(data.get("usage")))
        return data["choices"][0]["message"]["content"]
    raise RuntimeError(f"Unsupported provider: {provider}")


def parse_agent_action(text: str) -> dict[str, Any]:
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = re.sub(r"^```(?:json)?\s*", "", candidate)
        candidate = re.sub(r"\s*```$", "", candidate).strip()
    try:
        value = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise ValueError(f"agent response was not valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError("agent response must be a JSON object")
    return value


def _safe_path(path_value: Any) -> Path:
    raw = str(path_value or "").strip()
    if not raw:
        raise ValueError("missing path")
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    root = Path.cwd().resolve()
    resolved = path.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise PermissionError(f"path escapes current directory: {raw}") from exc
    return resolved


def run_agent_tool(name: str, args: dict[str, Any], perms: AgentPermissions) -> str:
    args = args or {}
    if name == "read_file":
        path = _safe_path(args.get("path"))
        text = path.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        start = int(args.get("start") or 1)
        end = int(args.get("end") or len(lines))
        start = max(1, start)
        end = min(len(lines), end)
        return "\n".join(f"{idx}|{line}" for idx, line in enumerate(lines[start - 1:end], start))[:12000]
    if name == "write_file":
        if not perms.write:
            raise PermissionError("write_file requires --allow-write")
        path = _safe_path(args.get("path"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(args.get("content") or ""), encoding="utf-8")
        return f"wrote {path.relative_to(Path.cwd())}"
    if name == "patch_file":
        if not perms.write:
            raise PermissionError("patch_file requires --allow-write")
        path = _safe_path(args.get("path"))
        text = path.read_text(encoding="utf-8")
        old = str(args.get("old") or "")
        new = str(args.get("new") or "")
        if not old:
            raise ValueError("patch_file requires non-empty old")
        count = text.count(old)
        if count != 1:
            raise ValueError(f"patch_file expected exactly one match, found {count}")
        path.write_text(text.replace(old, new, 1), encoding="utf-8")
        return f"patched {path.relative_to(Path.cwd())}"
    if name == "shell":
        if not perms.shell:
            raise PermissionError("shell requires --allow-shell")
        command = str(args.get("command") or "").strip()
        if not command:
            raise ValueError("shell requires command")
        proc = subprocess.run(command, shell=True, cwd=Path.cwd(), text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
        return f"exit {proc.returncode}\n{proc.stdout}"[:12000]
    if name == "curl":
        if not perms.net:
            raise PermissionError("curl requires --allow-net")
        url = str(args.get("url") or "").strip()
        if not url.startswith(("http://", "https://")):
            raise ValueError("curl URL must start with http:// or https://")
        method = str(args.get("method") or ("POST" if args.get("body") else "GET")).upper()
        headers = args.get("headers") if isinstance(args.get("headers"), dict) else {}
        req = urllib.request.Request(url, data=(str(args.get("body")).encode() if args.get("body") is not None else None), headers={str(k): str(v) for k, v in headers.items()}, method=method)
        with urllib.request.urlopen(req, timeout=30) as response:
            body = response.read(60000).decode("utf-8", errors="replace")
            return f"HTTP {response.status}\n{body}"[:12000]
    if name == "git_status":
        proc = subprocess.run(["git", "status", "--short"], cwd=Path.cwd(), text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=30)
        return f"exit {proc.returncode}\n{proc.stdout}"[:12000]
    if name == "git_diff":
        proc = subprocess.run(["git", "diff", "--", "."], cwd=Path.cwd(), text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=30)
        return f"exit {proc.returncode}\n{proc.stdout}"[:12000]
    if name == "git_commit":
        if not perms.commit:
            raise PermissionError("git_commit requires --allow-commit")
        message = str(args.get("message") or "").strip()
        if not message:
            raise ValueError("git_commit requires message")
        subprocess.run(["git", "add", "-A"], cwd=Path.cwd(), check=False, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=30)
        proc = subprocess.run(["git", "commit", "-m", message], cwd=Path.cwd(), text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
        return f"exit {proc.returncode}\n{proc.stdout}"[:12000]
    raise ValueError(f"unknown tool: {name}")


def build_agent_messages(task: dict[str, Any], user_prompt: str) -> list[dict[str, str]]:
    base_system = str(task.get("system_prompt") or "")
    system = (base_system + "\n\n" if base_system else "") + AGENT_TOOL_SCHEMA
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user_prompt},
    ]


def run_agent_loop(task: dict[str, Any], config: dict[str, Any], prompt: str, perms: AgentPermissions, *, max_steps: int = AGENT_MAX_STEPS) -> str:
    messages = build_agent_messages(task, prompt)
    transcript: list[dict[str, Any]] = []
    for step in range(1, max_steps + 1):
        raw = call_ai_messages(task, config, messages)
        action = parse_agent_action(raw)
        transcript.append({"step": step, "assistant": action})
        if "final" in action:
            save_agent_trace(transcript)
            return str(action["final"])
        tool = action.get("tool")
        if not isinstance(tool, dict):
            raise RuntimeError("agent response must contain either final or tool")
        tool_name = str(tool.get("name") or "")
        tool_args = tool.get("args") if isinstance(tool.get("args"), dict) else {}
        try:
            observation = run_agent_tool(tool_name, tool_args, perms)
        except Exception as exc:
            observation = f"ERROR: {type(exc).__name__}: {exc}"
        transcript.append({"step": step, "tool": tool_name, "observation": observation})
        messages.append({"role": "assistant", "content": raw})
        messages.append({"role": "user", "content": f"Observation from {tool_name}:\n{observation}\n\nContinue with the next JSON action."})
    save_agent_trace(transcript)
    raise RuntimeError(f"agent reached max steps ({max_steps}) without final")


def save_agent_trace(transcript: list[dict[str, Any]]) -> None:
    secure_write(paths().home / "last_agent_trace.json", json.dumps(transcript, indent=2, sort_keys=True) + "\n")


def run_logs_dir() -> Path:
    return paths().home / "runs"


def task_slug(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "-", name).strip("-.") or "task"


def task_run_log_path(name: str) -> Path:
    return run_logs_dir() / f"{task_slug(name)}.md"


def history_dir() -> Path:
    return run_logs_dir() / "history"


def task_history_dir(name: str) -> Path:
    return history_dir() / task_slug(name)


def new_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def task_history_path(name: str, run_id: str) -> Path:
    safe_run = re.sub(r"[^0-9TZ_.-]+", "-", run_id).strip("-.") or "run"
    return task_history_dir(name) / f"{safe_run}.md"


def _fence(text: Any) -> str:
    value = str(text)
    ticks = "```"
    while ticks in value:
        ticks += "`"
    return f"{ticks}text\n{value}\n{ticks}"


def format_agent_run_log(name: str, response: str, transcript: list[dict[str, Any]], usage_events: list[dict[str, Any]] | None = None) -> str:
    lines = [f"# Agentick run: {name}", "", "## Final", "", response.strip() or "(empty response)", ""]
    lines.extend(format_usage_log(usage_events or []))
    if transcript:
        lines.extend(["## Agent steps", ""])
    for entry in transcript:
        step = entry.get("step", "?")
        if "assistant" in entry:
            assistant = entry.get("assistant")
            thought = assistant.get("thought") if isinstance(assistant, dict) else None
            tool = assistant.get("tool") if isinstance(assistant, dict) else None
            lines.append(f"### Step {step}: assistant")
            if thought:
                lines.extend(["", str(thought)])
            if tool:
                lines.extend(["", _fence(json.dumps(tool, indent=2, sort_keys=True))])
            if isinstance(assistant, dict) and "final" in assistant:
                lines.extend(["", "Final action:", "", str(assistant["final"])])
            lines.append("")
        elif "tool" in entry:
            lines.append(f"### Step {step}: tool `{entry.get('tool')}`")
            lines.extend(["", _fence(entry.get("observation", "")), ""])
    return "\n".join(lines).rstrip() + "\n"


def save_task_run_log(name: str, response: str, *, agent: bool) -> None:
    run_id = new_run_id()
    usage_events = consume_ai_usage()
    if agent:
        try:
            transcript = json.loads((paths().home / "last_agent_trace.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            transcript = []
        if not isinstance(transcript, list):
            transcript = []
        content = format_agent_run_log(name, response, transcript, usage_events)
    else:
        lines = [f"# Agentick run: {name}", "", response.strip(), ""]
        lines.extend(format_usage_log(usage_events))
        content = "\n".join(lines).rstrip() + "\n"
    if content.startswith(f"# Agentick run: {name}\n"):
        content = content.replace(f"# Agentick run: {name}\n", f"# Agentick run: {name}\n\nRun id: `{run_id}`\n", 1)
    secure_write(task_run_log_path(name), content)
    history_path = task_history_path(name, run_id)
    suffix = 1
    while history_path.exists():
        suffix += 1
        history_path = task_history_path(name, f"{run_id}-{suffix}")
    secure_write(history_path, content)


def history_entries(name: str | None = None) -> list[tuple[str, str, Path]]:
    base = history_dir()
    if not base.exists():
        return []
    files: list[Path]
    if name:
        files = list(task_history_dir(name).glob("*.md"))
    else:
        files = list(base.glob("*/*.md"))
    entries: list[tuple[str, str, Path]] = []
    for path in files:
        entries.append((path.parent.name, path.stem, path))
    return sorted(entries, key=lambda item: item[2].stat().st_mtime, reverse=True)


def load_history_run(name: str, run_id: str | None = None) -> str | None:
    entries = history_entries(name)
    if not entries:
        return None
    if run_id:
        for _task, candidate_id, path in entries:
            if candidate_id == run_id:
                return path.read_text(encoding="utf-8", errors="replace")
        return None
    return entries[0][2].read_text(encoding="utf-8", errors="replace")


def load_task_run_log(name: str) -> str | None:
    path = task_run_log_path(name)
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8", errors="replace")

def with_loader(message: str, func: Callable[[], T]) -> T:
    """Run func while showing a tiny TTY-only spinner on stderr."""
    disabled = os.environ.get("AGC_NO_LOADER") or os.environ.get("AGC_MOCK_RESPONSE")
    if disabled or not sys.stderr.isatty():
        return func()

    done = threading.Event()
    started = time.monotonic()
    frames = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")

    def spin() -> None:
        idx = 0
        while not done.is_set():
            elapsed = int(time.monotonic() - started)
            sys.stderr.write(f"\r{CYAN}{frames[idx % len(frames)]}{RESET} {message} {DIM}{elapsed}s{RESET}")
            sys.stderr.flush()
            idx += 1
            done.wait(0.12)

    thread = threading.Thread(target=spin, daemon=True)
    thread.start()
    try:
        return func()
    finally:
        done.set()
        thread.join(timeout=0.3)
        elapsed = int(time.monotonic() - started)
        sys.stderr.write(f"\r{GREEN}✓{RESET} {message} {DIM}{elapsed}s{RESET}\n")
        sys.stderr.flush()


def save_last_prompt(prompt: str) -> None:
    secure_write(paths().home / "last_prompt.txt", prompt)


CITE_PATTERN = re.compile(r"@cite:L(\d+)C(\d+)\.\.L(\d+)C(\d+)")


@dataclass
class CiteRange:
    token: str
    start_line: int
    start_col: int
    end_line: int
    end_col: int


def parse_cite_ranges(text: str) -> list[CiteRange]:
    ranges: list[CiteRange] = []
    for match in CITE_PATTERN.finditer(text):
        start_line, start_col, end_line, end_col = (int(value) for value in match.groups())
        ranges.append(CiteRange(match.group(0), start_line, start_col, end_line, end_col))
    return ranges


def extract_citation_chunk(response: str, cite: CiteRange) -> str:
    lines = response.splitlines()
    if cite.start_line < 1 or cite.end_line < cite.start_line or cite.start_line > len(lines):
        raise ValueError(f"Invalid citation range: {cite.token}")
    if cite.end_line > len(lines):
        raise ValueError(f"Citation range exceeds response length: {cite.token}")
    chunks: list[str] = []
    for line_no in range(cite.start_line, cite.end_line + 1):
        line = lines[line_no - 1]
        if line_no == cite.start_line and line_no == cite.end_line:
            start = max(0, cite.start_col - 1)
            end = min(len(line), cite.end_col)
            chunks.append(line[start:end])
        elif line_no == cite.start_line:
            chunks.append(line[max(0, cite.start_col - 1):])
        elif line_no == cite.end_line:
            chunks.append(line[: min(len(line), cite.end_col)])
        else:
            chunks.append(line)
    return "\n".join(chunks)


def build_cited_reply(reply: str, previous_response: str) -> str:
    ranges = parse_cite_ranges(reply)
    if not ranges:
        return reply
    blocks = []
    for cite in ranges:
        chunk = extract_citation_chunk(previous_response, cite)
        blocks.append(f"Citation {cite.token} from the previous assistant response:\n```text\n{chunk}\n```")
    return reply + "\n\n" + "\n\n".join(blocks)


def response_with_line_numbers(response: str) -> str:
    lines = response.splitlines() or [""]
    return "\n".join(f"L{idx}: {line}" for idx, line in enumerate(lines, 1))


def save_conversation(name: str, messages: list[dict[str, str]]) -> Path:
    if not valid_task_name(name):
        raise ValueError("Conversation name must be 1-81 chars: letters, numbers, dot, underscore, dash.")
    paths().conversations.mkdir(parents=True, exist_ok=True)
    parts = [f"# Agentick conversation: {name}", ""]
    for message in messages:
        role = message.get("role", "message").title()
        content = message.get("content", "")
        parts.append(f"## {role}")
        parts.append("")
        parts.append(content.rstrip())
        parts.append("")
    out = paths().conversations / f"{name}.md"
    secure_write(out, "\n".join(parts).rstrip() + "\n")
    secure_write(paths().conversations / f"{name}.json", json.dumps({"name": name, "messages": messages}, indent=2) + "\n")
    return out


def render_response_ansi(response: str) -> str:
    width = shutil.get_terminal_size((100, 40)).columns
    sink = StringIO()
    console = Console(
        force_terminal=True,
        color_system="auto",
        width=width,
        record=True,
        file=sink,
    )
    console.print(Markdown(response, code_theme="monokai"))
    return console.export_text(clear=True, styles=True)


def _read_pager_key() -> str:
    ch = sys.stdin.read(1)
    if ch != "\x1b":
        return ch
    seq = sys.stdin.read(2)
    if seq in {"[5", "[6"}:
        seq += sys.stdin.read(1)
    return ch + seq


def _prompt_line(prompt: str, *, previous_response: str | None = None, old_settings: list[Any] | None = None) -> str:
    fd = sys.stdin.fileno()
    if previous_response is None:
        if old_settings is not None:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        try:
            sys.stdout.write("\x1b[?25h\n" + prompt)
            sys.stdout.flush()
            line = sys.stdin.readline()
            return line.rstrip("\n")
        finally:
            if old_settings is not None:
                tty.setcbreak(fd)

    buffer = ""

    def citation_preview(text: str) -> str:
        ranges = parse_cite_ranges(text)
        if not ranges:
            return ""
        try:
            chunk = extract_citation_chunk(previous_response, ranges[-1])
        except ValueError as exc:
            return f"{RED}{exc}{RESET}"
        one_line = chunk.replace("\n", " ↵ ")
        if len(one_line) > 100:
            one_line = one_line[:97] + "..."
        return f"{GREEN}citing:{RESET} {BOLD}{one_line}{RESET}"

    try:
        tty.setcbreak(fd)
        sys.stdout.write("\x1b[?25h\n")
        while True:
            preview = citation_preview(buffer)
            sys.stdout.write("\r\x1b[2K" + prompt + buffer)
            sys.stdout.write("\x1b[K")
            if preview:
                sys.stdout.write("\n\r\x1b[2K" + preview + "\x1b[A")
            sys.stdout.flush()
            ch = sys.stdin.read(1)
            if ch in {"\r", "\n"}:
                sys.stdout.write("\n")
                return buffer
            if ch == "\x03":
                raise KeyboardInterrupt
            if ch in {"\x7f", "\b"}:
                buffer = buffer[:-1]
                continue
            if ch >= " ":
                buffer += ch
    finally:
        if old_settings is not None:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
            tty.setcbreak(fd)


def conversation_pager(response: str, messages: list[dict[str, str]]) -> str | None:
    if os.environ.get("AGC_NO_PAGER") or not sys.stdin.isatty() or not sys.stdout.isatty():
        return None
    numbered = response_with_line_numbers(response)
    rendered = render_response_ansi(numbered)
    lines = rendered.splitlines() or [""]
    top = 0
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)

    def repaint(status: str = "") -> None:
        nonlocal top
        size = shutil.get_terminal_size((100, 30))
        body_height = max(1, size.lines - 2)
        max_top = max(0, len(lines) - body_height)
        top = max(0, min(top, max_top))
        visible = lines[top : top + body_height]
        footer = f"{DIM}h/k/↑ up · j/↓ down · Space/PgDn · b/PgUp · R reply · Ctrl-S save · q quit · {top + 1}-{min(top + body_height, len(lines))}/{len(lines)}{RESET}"
        sys.stdout.write("\x1b[?25l\x1b[H\x1b[2J")
        sys.stdout.write("\n".join(visible))
        if visible:
            sys.stdout.write("\n")
        if status:
            sys.stdout.write(status[: size.columns] + "\n")
        sys.stdout.write(footer[: size.columns])
        sys.stdout.flush()

    try:
        tty.setcbreak(fd)
        status = ""
        while True:
            repaint(status)
            status = ""
            key = _read_pager_key()
            size = shutil.get_terminal_size((100, 30))
            page = max(1, size.lines - 3)
            if key in {"q", "Q", "\x03"}:
                return None
            if key in {"R", "r"}:
                reply = _prompt_line("Reply (@cite:L1C1..L2C5 supported): ", previous_response=response, old_settings=old_settings).strip()
                if reply:
                    return reply
                status = f"{YELLOW}Empty reply cancelled.{RESET}"
            elif key == "\x13":
                name = _prompt_line("Save conversation as: ", old_settings=old_settings).strip()
                if name:
                    try:
                        out = save_conversation(name, messages)
                        status = f"{GREEN}Saved conversation:{RESET} {out}"
                    except ValueError as exc:
                        status = f"{RED}{exc}{RESET}"
            elif key in {"h", "k", "\x1b[A"}:
                top -= 1
            elif key in {"j", "\x1b[B", "\r", "\n"}:
                top += 1
            elif key in {" ", "\x06", "\x1b[6~"}:
                top += page
            elif key in {"b", "\x02", "\x1b[5~"}:
                top -= page
            elif key == "g":
                top = 0
            elif key == "G":
                top = len(lines)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        # Keep the last response screen visible after quitting so users can still
        # scroll/copy from their terminal history even if they did not save yet.
        sys.stdout.write("\x1b[?25h\n")
        sys.stdout.flush()


def builtin_pager(rendered: str) -> bool:
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        return False
    lines = rendered.splitlines() or [""]
    top = 0
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)

    def repaint() -> None:
        nonlocal top
        size = shutil.get_terminal_size((100, 30))
        body_height = max(1, size.lines - 1)
        max_top = max(0, len(lines) - body_height)
        top = max(0, min(top, max_top))
        visible = lines[top : top + body_height]
        footer = f"{DIM}h/k/↑ up · j/↓ down · Space/PgDn · b/PgUp · g/G · q quit · {top + 1}-{min(top + body_height, len(lines))}/{len(lines)}{RESET}"
        sys.stdout.write("\x1b[?25l\x1b[H\x1b[2J")
        sys.stdout.write("\n".join(visible))
        if visible:
            sys.stdout.write("\n")
        sys.stdout.write(footer[: size.columns])
        sys.stdout.flush()

    try:
        tty.setcbreak(fd)
        while True:
            repaint()
            key = _read_pager_key()
            size = shutil.get_terminal_size((100, 30))
            page = max(1, size.lines - 2)
            if key in {"q", "Q", "\x03"}:
                break
            if key in {"h", "k", "\x1b[A"}:
                top -= 1
            elif key in {"j", "\x1b[B", "\r", "\n"}:
                top += 1
            elif key in {" ", "\x06", "\x1b[6~"}:
                top += page
            elif key in {"b", "\x02", "\x1b[5~"}:
                top -= page
            elif key == "g":
                top = 0
            elif key == "G":
                top = len(lines)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        # Keep the final pager contents visible after quit instead of erasing the
        # answer the user may want to read or copy from terminal scrollback.
        sys.stdout.write("\x1b[?25h\n")
        sys.stdout.flush()
    return True


def page_response(rendered: str) -> bool:
    if os.environ.get("AGC_NO_PAGER"):
        return False
    try:
        if builtin_pager(rendered):
            return True
    except (OSError, termios.error):
        pass
    less = shutil.which("less")
    if not less:
        return False
    env = os.environ.copy()
    env.setdefault("LESS", "-R")
    try:
        subprocess.run([less, "-R"], input=rendered, text=True, env=env, check=False)
    except OSError:
        return False
    return True


def interactive_output(response: str, headless: bool = False) -> None:
    if headless or not sys.stdout.isatty():
        print(response)
        return

    rendered = render_response_ansi(response)
    if page_response(rendered):
        return
    print(rendered, end="")


def conversation_loop(task_name: str, task: dict[str, Any], cfg: dict[str, Any], prompt: str, first_response: str, *, headless: bool = False) -> None:
    messages = [
        {"role": "system", "content": str(task.get("system_prompt", ""))},
        {"role": "user", "content": prompt},
        {"role": "assistant", "content": first_response},
    ]
    response = first_response
    if headless or not sys.stdin.isatty() or not sys.stdout.isatty():
        interactive_output(response, headless=headless)
        return
    while True:
        reply = conversation_pager(response, messages)
        if not reply:
            return
        try:
            user_content = build_cited_reply(reply, response)
        except ValueError as exc:
            print(f"agc cite error: {exc}", file=sys.stderr)
            continue
        messages.append({"role": "user", "content": user_content})
        try:
            response = with_loader(f"Continuing {task_name}…", lambda: call_ai_messages(task, cfg, messages))
        except urllib.error.HTTPError as exc:
            print(f"agc error: {http_error_detail(exc)}", file=sys.stderr)
            return
        except (RuntimeError, ValueError, urllib.error.URLError, KeyError, IndexError, json.JSONDecodeError) as exc:
            print(f"agc error: {exc}", file=sys.stderr)
            return
        messages.append({"role": "assistant", "content": response})
        save_task_run_log(task_name, response, agent=False)


def run_task_cmd(name: str, argv: list[str], headless: bool = False, agent: bool = False, perms: AgentPermissions | None = None, edit_args: bool = False) -> int:
    cfg = load_config()
    if not enforce_ready_or_setup(cfg):
        return 2
    assert cfg is not None
    task = load_task(name)
    if task is None:
        print(f"Unknown task: {name}", file=sys.stderr)
        return 2
    reset_ai_usage()
    task_provider = task.get("provider") or cfg.get("default_provider")
    if not enforce_ready_or_setup(cfg, str(task_provider) if task_provider else None):
        return 2
    if edit_args:
        try:
            argv = collect_editor_arguments(task, argv)
        except (KeyboardInterrupt, EOFError):
            print("\nCancelled.", file=sys.stderr)
            return 130
        except (OSError, ValueError) as exc:
            print(f"agc error: {exc}", file=sys.stderr)
            return 2
    prompt = render_prompt(task.get("user_prompt", ""), argv)
    save_last_prompt(prompt)
    try:
        use_agent = agent or bool(task.get("agent"))
        if use_agent:
            response = with_loader(f"Running agentic task {name}…", lambda: run_agent_loop(task, cfg, prompt, perms or AgentPermissions()))
        else:
            response = with_loader(f"Running {name}…", lambda: call_ai(task, cfg, prompt))
    except urllib.error.HTTPError as exc:
        print(f"agc error: {http_error_detail(exc)}", file=sys.stderr)
        return 1
    except (RuntimeError, ValueError, PermissionError, subprocess.TimeoutExpired, urllib.error.URLError, KeyError, IndexError, json.JSONDecodeError) as exc:
        print(f"agc error: {exc}", file=sys.stderr)
        return 1
    save_task_run_log(name, response, agent=use_agent)
    conversation_loop(name, task, cfg, prompt, response, headless=headless)
    return 0


def tasks_cmd(_args: argparse.Namespace) -> int:
    if not paths().tasks.exists():
        print("No saved tasks yet. Create one with `agc new ./prompt.md name`.")
        return 0
    cfg = load_config() or {}
    print(banner())
    found = False
    for file in sorted(paths().tasks.glob("*.json")):
        try:
            task = json.loads(file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        found = True
        provider = task.get("provider") or cfg.get("default_provider") or "openai"
        model = resolved_model(task, cfg, provider) if provider in PROVIDERS else str(task.get("model") or "unknown-model")
        reasoning = resolved_reasoning_effort(task, cfg, provider) if provider in PROVIDERS else str(task.get("reasoning_effort") or "medium")
        name = str(task.get("name", file.stem))
        labels = []
        if task.get("agent"):
            labels.append("agent")
        routine = task.get("routine")
        if routine:
            labels.append("routine")
        label_text = f" — {', '.join(labels)}" if labels else ""
        print(f"  {GREEN}{name}{RESET} — {provider}/{model} — reasoning {reasoning}{label_text}")
    if not found:
        print("No saved tasks yet. Create one with `agc new ./prompt.md name`.")
    return 0


def history_cmd(args: argparse.Namespace) -> int:
    action = getattr(args, "action", None) or "list"
    name = getattr(args, "name", None)
    run_id = getattr(args, "run_id", None)
    headless = bool(getattr(args, "headless", False))
    if action == "view":
        if not name:
            print("history view requires a task name", file=sys.stderr)
            return 2
        content = load_history_run(name, run_id)
        if content is None:
            if run_id:
                print(f"No history run found for {name}: {run_id}", file=sys.stderr)
            else:
                print(f"No execution history for task: {name}", file=sys.stderr)
            return 2
        interactive_output(content, headless=headless)
        return 0
    if action != "list":
        name = action
    entries = history_entries(name)
    print(banner())
    if not entries:
        if name:
            print(f"No execution history for task: {name}")
        else:
            print("No execution history yet. Run a task first.")
        return 0
    print("Execution history:")
    for task, entry_id, path in entries[:50]:
        stamp = datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        size = path.stat().st_size
        print(f"  {GREEN}{task}{RESET}  {entry_id}  {DIM}{stamp}  {size} bytes{RESET}")
    print(f"\nView one with: agc history view <task> <run-id>")
    return 0


def routine_from_args(name: str, args: argparse.Namespace, existing: dict[str, Any] | None = None) -> dict[str, Any] | None:
    task = load_task(name)
    if task is None:
        print(f"Unknown task: {name}", file=sys.stderr)
        return None
    every = getattr(args, "every", None)
    if not every and existing:
        every = existing.get("every")
    if not every and not getattr(args, "no_interactive", False):
        try:
            every = input("Run how often? (e.g. 15m, 1h, daily): ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nCancelled.", file=sys.stderr)
            raise
    if not every:
        print("routines create/edit requires --every in --no-interactive mode", file=sys.stderr)
        return None
    try:
        routine_interval_seconds(str(every))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return None
    scheduler = getattr(args, "scheduler", None) or (existing or {}).get("scheduler") or detected_scheduler()
    if scheduler == "auto":
        scheduler = detected_scheduler()
    saved_args = list((existing or {}).get("args") or [])
    if getattr(args, "arg", None) is not None:
        saved_args = [str(item) for item in getattr(args, "arg")]
    permissions = dict((existing or {}).get("permissions") or {})
    for key, value in routine_permissions_from_args(args).items():
        if value:
            permissions[key] = True
    if not permissions and task.get("agent"):
        permissions["agent"] = True
    routine: dict[str, Any] = {
        "every": str(every),
        "scheduler": str(scheduler),
        "args": saved_args,
        "permissions": permissions,
        "cwd": str((existing or {}).get("cwd") or Path.cwd()),
        "python": str((existing or {}).get("python") or sys.executable),
        "label": routine_label(name),
        "installed": bool((existing or {}).get("installed", False)),
    }
    return routine


def routines_cmd(args: argparse.Namespace) -> int:
    action = getattr(args, "action", None) or "list"
    if action in {"view", "logs"}:
        name = getattr(args, "name", None)
        if not name:
            print(f"Usage: agc routines {action} <task-name>", file=sys.stderr)
            return 2
        log = load_task_run_log(name)
        artifact_log = routine_artifacts(name)["log"]
        if log is None and artifact_log.exists():
            log = artifact_log.read_text(encoding="utf-8", errors="replace")
        if log is None:
            print(f"No run log found for routine/task: {name}", file=sys.stderr)
            print(f"Run it first with `agc {name}` or check `agc routines` for saved routine names.", file=sys.stderr)
            return 2
        interactive_output(log, headless=getattr(args, "headless", False))
        return 0
    if action == "create":
        name = getattr(args, "name", None)
        if not name:
            print("Usage: agc routines create <task-name> --every 15m", file=sys.stderr)
            return 2
        routine = routine_from_args(name, args)
        if routine is None:
            return 2
        try:
            if getattr(args, "no_install", False):
                write_routine_artifacts(name, routine)
            else:
                install_routine_schedule(name, routine)
                routine["installed"] = routine["scheduler"] != "manual"
        except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
            print(f"Could not install routine: {exc}", file=sys.stderr)
            return 1
        update_routine_task(name, routine)
        print(banner())
        state = "created" if getattr(args, "no_install", False) else "created and started"
        print(f"{GREEN}Routine {state}:{RESET} {name} every {routine['every']} via {routine['scheduler']}")
        print(f"View logs: agc routines view {name}")
        return 0
    if action == "edit":
        name = getattr(args, "name", None)
        if not name:
            print("Usage: agc routines edit <task-name> --every 30m", file=sys.stderr)
            return 2
        task = load_task(name)
        if task is None:
            print(f"Unknown task: {name}", file=sys.stderr)
            return 2
        existing = task.get("routine") if isinstance(task.get("routine"), dict) else None
        if existing is None:
            print(f"Task is not a routine yet: {name}", file=sys.stderr)
            return 2
        routine = routine_from_args(name, args, existing)
        if routine is None:
            return 2
        try:
            if not getattr(args, "no_install", False) and existing.get("installed"):
                stop_routine_schedule(name, existing)
                install_routine_schedule(name, routine)
                routine["installed"] = True
            else:
                write_routine_artifacts(name, routine)
                routine["installed"] = bool(existing.get("installed"))
        except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
            print(f"Could not update routine: {exc}", file=sys.stderr)
            return 1
        update_routine_task(name, routine)
        print(banner())
        print(f"{GREEN}Routine updated:{RESET} {name} every {routine['every']} via {routine['scheduler']}")
        return 0
    if action == "start":
        name = getattr(args, "name", None)
        task = load_task(name) if name else None
        routine = task.get("routine") if task else None
        if not name or not isinstance(routine, dict):
            print(f"No routine found: {name or ''}".strip(), file=sys.stderr)
            return 2
        try:
            if getattr(args, "no_install", False):
                write_routine_artifacts(name, routine)
            else:
                install_routine_schedule(name, routine)
                routine["installed"] = routine.get("scheduler") != "manual"
                update_routine_task(name, routine)
        except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
            print(f"Could not start routine: {exc}", file=sys.stderr)
            return 1
        print(banner())
        print(f"{GREEN}Routine started:{RESET} {name}")
        return 0
    if action == "stop":
        name = getattr(args, "name", None)
        task = load_task(name) if name else None
        routine = task.get("routine") if task else None
        if not name or not isinstance(routine, dict):
            print(f"No routine found: {name or ''}".strip(), file=sys.stderr)
            return 2
        try:
            if not getattr(args, "no_install", False):
                stop_routine_schedule(name, routine)
            routine["installed"] = False
            update_routine_task(name, routine)
        except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
            print(f"Could not stop routine: {exc}", file=sys.stderr)
            return 1
        print(banner())
        print(f"{GREEN}Routine stopped:{RESET} {name}")
        return 0
    if action == "delete":
        name = getattr(args, "name", None)
        task = load_task(name) if name else None
        routine = task.get("routine") if task else None
        if not name or not isinstance(routine, dict):
            print(f"No routine found: {name or ''}".strip(), file=sys.stderr)
            return 2
        if not getattr(args, "yes", False):
            if getattr(args, "no_interactive", False) or not sys.stdin.isatty():
                print(f"Refusing to delete routine {name!r} without --yes in non-interactive mode.", file=sys.stderr)
                return 2
            try:
                answer = input(f"Delete routine schedule for {name!r}? Type the task name to confirm: ").strip()
            except (KeyboardInterrupt, EOFError):
                print("\nCancelled.", file=sys.stderr)
                return 130
            if answer != name:
                print("Delete cancelled.")
                return 0
        try:
            if not getattr(args, "no_install", False):
                stop_routine_schedule(name, routine)
            for artifact in routine_artifacts(name).values():
                try:
                    artifact.unlink()
                except FileNotFoundError:
                    pass
            clear_routine_task(name)
        except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
            print(f"Could not delete routine: {exc}", file=sys.stderr)
            return 1
        print(banner())
        print(f"{GREEN}Routine deleted:{RESET} {name}")
        return 0
    if action == "status":
        name = getattr(args, "name", None)
        if name:
            task = load_task(name)
            routine = task.get("routine") if task else None
            if not isinstance(routine, dict):
                print(f"No routine found: {name}", file=sys.stderr)
                return 2
            print(f"{name}: {'started' if routine.get('installed') else 'stopped'} — every {routine.get('every')} via {routine.get('scheduler')}")
            return 0
        action = "list"
    if action not in {"list", None}:
        print(f"Unknown routines action: {action}", file=sys.stderr)
        return 2
    if not paths().tasks.exists():
        print("No routine tasks yet.")
        return 0
    cfg = load_config() or {}
    print(banner())
    found = False
    for file in sorted(paths().tasks.glob("*.json")):
        try:
            task = json.loads(file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        routine = task.get("routine")
        if not routine:
            continue
        found = True
        if isinstance(routine, dict):
            if routine.get("at"):
                desc = f"{routine.get('every', 'manual')} at {routine.get('at')}"
            else:
                desc = f"{routine.get('every', 'manual')} via {routine.get('scheduler', detected_scheduler())}"
            state = "started" if routine.get("installed") else "stopped"
        else:
            desc = str(routine)
            state = "configured"
        provider = task.get("provider") or cfg.get("default_provider") or "openai"
        model = resolved_model(task, cfg, provider) if provider in PROVIDERS else str(task.get("model") or "unknown-model")
        reasoning = resolved_reasoning_effort(task, cfg, provider) if provider in PROVIDERS else str(task.get("reasoning_effort") or "medium")
        name = str(task.get('name', file.stem))
        agent_label = " — agent" if task.get("agent") else ""
        actions = f" — actions: view|status|start|stop|edit|delete {name}"
        print(f"  {GREEN}{name}{RESET} — {state} — {desc} — {provider}/{model} — reasoning {reasoning}{agent_label}{actions}")
    if not found:
        print("No routine tasks yet.")
    return 0

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agc",
        description="Agentick — turn reusable AI prompts into tiny developer commands.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent(
            """
            examples:
              agc setup
              agc new ./pr-risk.md pr-risk
              agc edit pr-risk
              agc delete pr-risk --yes
              agc tasks
              agc history
              agc history view pr-risk <run-id>
              agc pr-risk ./src/payments/checkout.ts:L80..L180
              agc incident-handoff --edit-args
              agc api-migration ./openapi-v1.json ./openapi-v2.json > migration.md
              agc branch-watch main --agent --allow-write --allow-shell
              agc routines create branch-watch --every 15m --arg main --agent --allow-shell --allow-write
              agc routines view branch-watch
              agc routines stop branch-watch
              agc routines delete branch-watch --yes
              agc release-drafter ./git-log.txt > CHANGELOG-draft.md

            output:
              Interactive terminals open a rich markdown viewer with h/j/k scrolling, R replies, and Ctrl-S save.
              Redirected stdout writes raw model output, so `agc task > file.md` is clean.
            """
        ).strip(),
    )
    parser.add_argument("--no-interactive", action="store_true", help="disable prompts; fail with guidance instead")
    parser.add_argument("--agent", action="store_true", help="run a saved task as an agentic loop with tool calls")
    parser.add_argument("--allow-write", action="store_true", help="allow agentic tasks to write or patch files under the current directory")
    parser.add_argument("--allow-shell", action="store_true", help="allow agentic tasks to run shell commands in the current directory")
    parser.add_argument("--allow-net", action="store_true", help="allow agentic tasks to make outbound HTTP(S) requests")
    parser.add_argument("--allow-commit", action="store_true", help="allow agentic tasks to create git commits")
    sub = parser.add_subparsers(dest="command")

    setup = sub.add_parser("setup", help="configure an AI provider")
    setup.add_argument("--provider", choices=sorted({slug for slug, _label in build_provider_choices()} | set(PROVIDERS) | {"xai"}))
    setup.add_argument("--model")
    setup.add_argument("--reasoning")
    setup.add_argument("--api-key")
    setup.add_argument("--auth", choices=["api_key", "oauth"])
    setup.add_argument("--oauth-token")
    setup.add_argument("--no-interactive", action="store_true")

    new = sub.add_parser("new", help="create a reusable prompt task")
    new.add_argument("prompt_file", nargs="?")
    new.add_argument("name", nargs="?")
    new.add_argument("--provider", choices=sorted(PROVIDERS))
    new.add_argument("--model")
    new.add_argument("--reasoning")
    new.add_argument("--agent", action="store_true", help="save task as an agentic workflow by default")
    new.add_argument("--no-interactive", action="store_true")

    edit = sub.add_parser("edit", help="edit an existing task in $EDITOR or replace it from a prompt file")
    edit.add_argument("name")
    edit.add_argument("prompt_file", nargs="?")
    edit.add_argument("--provider", choices=sorted(PROVIDERS))
    edit.add_argument("--model")
    edit.add_argument("--reasoning")
    edit.add_argument("--agent", action="store_true", help="mark the task as agentic")
    edit.add_argument("--no-agent", action="store_true", help="mark the task as single-shot")
    edit.add_argument("--no-interactive", action="store_true")

    delete = sub.add_parser("delete", aliases=["rm"], help="delete a saved task")
    delete.add_argument("name")
    delete.add_argument("--yes", "-y", action="store_true", help="delete without an interactive confirmation prompt")
    delete.add_argument("--no-interactive", action="store_true")

    tasks = sub.add_parser("tasks", help="list saved tasks")
    tasks.add_argument("--no-interactive", action="store_true")

    history = sub.add_parser("history", help="list or view previous task answers")
    history.add_argument("action", nargs="?", help="list, view, or a task name to filter")
    history.add_argument("name", nargs="?", help="task name for `history view`")
    history.add_argument("run_id", nargs="?", help="run id from `agc history`")
    history.add_argument("--headless", action="store_true", help="print raw markdown instead of opening the viewer")
    history.add_argument("--no-interactive", action="store_true")

    routines = sub.add_parser("routines", help="create, list, start, stop, edit, delete, or view routine tasks")
    routines.add_argument("action", nargs="?", choices=["list", "create", "view", "logs", "status", "start", "stop", "edit", "delete"], default="list")
    routines.add_argument("name", nargs="?")
    routines.add_argument("--every", help="run interval such as 15m, 1h, daily, hourly, or weekly")
    routines.add_argument("--arg", action="append", help="save one argument to pass each time the routine runs; repeatable")
    routines.add_argument("--scheduler", choices=["auto", "launchd", "cron", "manual"], help="scheduler backend; auto uses launchd on macOS and cron on Linux")
    routines.add_argument("--agent", action="store_true", help="run the routine with agentic mode enabled")
    routines.add_argument("--allow-write", action="store_true", help="allow routine agent runs to write files")
    routines.add_argument("--allow-shell", action="store_true", help="allow routine agent runs to run shell commands")
    routines.add_argument("--allow-net", action="store_true", help="allow routine agent runs to make outbound HTTP(S) requests")
    routines.add_argument("--allow-commit", action="store_true", help="allow routine agent runs to create git commits")
    routines.add_argument("--no-install", action="store_true", help="write Agentick routine metadata/artifacts without changing launchd/crontab")
    routines.add_argument("--yes", "-y", action="store_true", help="confirm destructive routine actions non-interactively")
    routines.add_argument("--headless", action="store_true", help="print the run log instead of opening the scrollable viewer")
    routines.add_argument("--no-interactive", action="store_true")
    return parser


def _main_impl(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        cfg = load_config()
        if not enforce_ready_or_setup(cfg):
            return 2
        print(banner())
        print("Run: agc new OR agc <task-name>")
        return 0
    global_flags = {"--no-interactive", "--agent", "--allow-write", "--allow-shell", "--allow-net", "--allow-commit", "--edit-args", "--args-editor"}
    command_token = next((item for item in argv if item not in global_flags), "")
    if command_token and command_token not in {"setup", "new", "edit", "delete", "rm", "tasks", "history", "routines", "-h", "--help"}:
        headless = False
        agent = False
        edit_args = False
        perms = AgentPermissions()
        for flag in ["--headless", "--agent", "--edit-args", "--args-editor", "--allow-write", "--allow-shell", "--allow-net", "--allow-commit", "--no-interactive"]:
            while flag in argv:
                if flag == "--headless":
                    headless = True
                elif flag == "--agent":
                    agent = True
                elif flag in {"--edit-args", "--args-editor"}:
                    edit_args = True
                elif flag == "--allow-write":
                    perms.write = True
                elif flag == "--allow-shell":
                    perms.shell = True
                elif flag == "--allow-net":
                    perms.net = True
                elif flag == "--allow-commit":
                    perms.commit = True
                argv.remove(flag)
        name, rest = argv[0], argv[1:]
        return run_task_cmd(name, rest, headless=headless, agent=agent, perms=perms, edit_args=edit_args)
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "setup":
        return setup_cmd(args)
    if args.command == "new":
        cfg = load_config()
        if not enforce_ready_or_setup(cfg):
            return 2
        return new_cmd(args)
    if args.command == "edit":
        cfg = load_config()
        if not enforce_ready_or_setup(cfg):
            return 2
        return edit_cmd(args)
    if args.command in {"delete", "rm"}:
        cfg = load_config()
        if not enforce_ready_or_setup(cfg):
            return 2
        return delete_cmd(args)
    if args.command == "tasks":
        cfg = load_config()
        if not enforce_ready_or_setup(cfg):
            return 2
        return tasks_cmd(args)
    if args.command == "history":
        cfg = load_config()
        if not enforce_ready_or_setup(cfg):
            return 2
        return history_cmd(args)
    if args.command == "routines":
        cfg = load_config()
        if not enforce_ready_or_setup(cfg):
            return 2
        return routines_cmd(args)
    if args.command is None and argv and argv[0] in {"-h", "--help"}:
        return 0
    if not enforce_ready_or_setup(load_config()):
        return 2
    return 0


def main(argv: list[str] | None = None) -> int:
    try:
        return _main_impl(argv)
    except KeyboardInterrupt:
        print("\nCancelled.", file=sys.stderr)
        return 130
    except EOFError:
        print("\nInput closed.", file=sys.stderr)
        return 130
