"""Smoke tests for project setup (Requirement 1.1, 2.1, 2.3, 2.4)."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.config import Settings, get_settings

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_settings_loads_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://x:y@localhost:5432/z")
    monkeypatch.setenv("SYNC_INTERVAL_MINUTES", "15")
    settings = Settings()
    assert settings.database_url.endswith("/z")
    assert settings.sync_interval_minutes == 15


def test_huawei_configured_property() -> None:
    s = Settings(
        huawei_client_id=None,
        huawei_client_secret=None,
        huawei_redirect_uri=None,
    )
    assert s.huawei_configured is False

    s2 = Settings(
        huawei_client_id="id",
        huawei_client_secret="secret",
        huawei_redirect_uri="https://x/cb",
    )
    assert s2.huawei_configured is True


def test_get_settings_is_cached() -> None:
    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2


def test_required_directories_exist() -> None:
    for rel in ("backend", "frontend", "docs"):
        assert (REPO_ROOT / rel).is_dir(), f"Missing directory: {rel}"


def test_backend_app_subpackages_exist() -> None:
    app_dir = REPO_ROOT / "backend" / "app"
    for sub in ("models", "repositories", "services", "providers", "routers"):
        assert (app_dir / sub).is_dir(), f"Missing backend/app/{sub}"


def test_readme_and_gitignore_exist() -> None:
    assert (REPO_ROOT / "README.md").is_file()
    assert (REPO_ROOT / ".gitignore").is_file()
