#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PREFIX="${AGENTICK_INSTALL_PREFIX:-$HOME/.agentick/venv}"
PYTHON_BIN="${PYTHON:-python3}"
DRY_RUN=0
UPDATE_SHELL_PROFILE=1

neon() { printf '\033[95m\033[1m%s\033[0m\n' "$*"; }
cyan() { printf '\033[96m%s\033[0m\n' "$*"; }
warn() { printf '\033[93m%s\033[0m\n' "$*"; }
err() { printf '\033[91m%s\033[0m\n' "$*" >&2; }

usage() {
  cat <<EOF
Agentick installer

Installs the local Agentick checkout into an isolated Python virtualenv,
updates your shell profile so agc is on PATH for future terminals, and prints
the next command to configure your AI provider.

Usage:
  bash scripts/install.sh [options]

Options:
  --prefix PATH       Install virtualenv here (default: ~/.agentick/venv)
  --python PATH       Python executable to use (default: python3 or \$PYTHON)
  --dry-run           Print actions without creating files
  --no-shell-profile  Do not update ~/.zshrc, ~/.bashrc, or shell profile PATH
  -h, --help          Show this help

After install:
  agc setup

Note:
  A script cannot modify the PATH of the already-running parent shell. The
  installer updates your shell profile so new terminals can run agc directly.
  If you need agc in the current terminal immediately, run:
    source ~/.zshrc   # or source your printed profile file
  agc setup

Examples:
  bash scripts/install.sh
  bash scripts/install.sh --prefix ~/.local/share/agentick/venv
  bash scripts/install.sh --dry-run --python python3.12
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --prefix)
      [[ $# -ge 2 ]] || { err "--prefix requires a path"; exit 2; }
      PREFIX="$2"
      shift 2
      ;;
    --python)
      [[ $# -ge 2 ]] || { err "--python requires an executable"; exit 2; }
      PYTHON_BIN="$2"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --no-shell-profile)
      UPDATE_SHELL_PROFILE=0
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      err "Unknown option: $1"
      usage >&2
      exit 2
      ;;
  esac
done

if [[ "$PREFIX" == ~* ]]; then
  PREFIX="${PREFIX/#\~/$HOME}"
fi
PREFIX="$(python3 -c 'import os,sys; print(os.path.abspath(os.path.expanduser(sys.argv[1])))' "$PREFIX")"
BIN_DIR="$PREFIX/bin"
AGC_BIN="$BIN_DIR/agc"

run() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    printf '  %s\n' "$*"
  else
    "$@"
  fi
}

neon "▰ Agentick installer"
cyan "Project: $PROJECT_ROOT"
cyan "Prefix:  $PREFIX"
cyan "Python:  $PYTHON_BIN"

if [[ "$DRY_RUN" -eq 1 ]]; then
  warn "DRY RUN — no files will be created."
fi

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1 && [[ ! -x "$PYTHON_BIN" ]]; then
  err "Python executable not found: $PYTHON_BIN"
  exit 2
fi

run "$PYTHON_BIN" -m venv "$PREFIX"
run "$BIN_DIR/python" -m pip install --upgrade pip
run "$BIN_DIR/python" -m pip install -e "$PROJECT_ROOT"

detect_profile() {
  local shell_name
  shell_name="$(basename "${SHELL:-}")"
  case "$shell_name" in
    zsh) printf '%s\n' "$HOME/.zshrc" ;;
    bash) printf '%s\n' "$HOME/.bashrc" ;;
    fish) printf '%s\n' "$HOME/.config/fish/config.fish" ;;
    *)
      if [[ -n "${ZSH_VERSION:-}" ]]; then
        printf '%s\n' "$HOME/.zshrc"
      elif [[ -n "${BASH_VERSION:-}" ]]; then
        printf '%s\n' "$HOME/.bashrc"
      else
        printf '%s\n' "$HOME/.profile"
      fi
      ;;
  esac
}

update_shell_profile() {
  local profile path_line marker
  profile="$(detect_profile)"
  path_line="export PATH=\"$BIN_DIR:\$PATH\""
  marker="# Agentick CLI"
  if [[ "$UPDATE_SHELL_PROFILE" -eq 0 ]]; then
    printf 'Skipping shell profile update (--no-shell-profile).\n'
    return 0
  fi
  if [[ "$DRY_RUN" -eq 1 ]]; then
    printf '  update shell profile %s with: %s\n' "$profile" "$path_line"
    return 0
  fi
  mkdir -p "$(dirname "$profile")"
  touch "$profile"
  if grep -Fq "$path_line" "$profile"; then
    printf 'Shell profile already configured: %s\n' "$profile"
    return 0
  fi
  {
    printf '\n%s\n' "$marker"
    printf '%s\n' "$path_line"
  } >> "$profile"
  printf 'Added Agentick to shell profile: %s\n' "$profile"
}

update_shell_profile

if [[ "$DRY_RUN" -eq 0 ]]; then
  if [[ ! -x "$AGC_BIN" ]]; then
    err "Install completed but agc was not found at $AGC_BIN"
    exit 1
  fi
  "$AGC_BIN" --help >/dev/null
fi

printf '\n'
neon "Agentick installed."
printf 'agc is installed at: %s\n' "$AGC_BIN"
if [[ "$UPDATE_SHELL_PROFILE" -eq 1 ]]; then
  printf 'Shell profile was configured for future terminals.\n'
  printf 'For this already-open terminal, run: source %s\n' "$(detect_profile)"
fi
printf '\nThen configure your provider:\n'
printf '  agc setup\n'
printf '\nQuick smoke test without API calls:\n'
printf "  AGC_MOCK_RESPONSE='hello' agc <task-name> --headless\n"
