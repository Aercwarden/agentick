from __future__ import annotations

import shutil
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def clean_agentick_home():
    root = Path(__file__).resolve().parents[1]
    home = root / ".test-agentick-home"
    if home.exists():
        shutil.rmtree(home)
    yield
    if home.exists():
        shutil.rmtree(home)
