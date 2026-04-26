"""Shared test fixtures."""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from storyteller.config import Settings


@pytest.fixture
def settings() -> Settings:
    return Settings()


@pytest.fixture
def tmp_project(tmp_path: Path, settings: Settings) -> Path:
    """Create a temporary project directory."""
    settings.projects.root = str(tmp_path)
    project_dir = tmp_path / "test-project"
    project_dir.mkdir()
    (project_dir / "chapters").mkdir()
    return project_dir


@pytest.fixture
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
