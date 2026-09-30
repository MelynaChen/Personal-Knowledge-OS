"""Configuration path tests use only synthetic credentials and a temporary env file."""
from pathlib import Path

import pytest
from sqlalchemy.engine import make_url

from app.config.settings import ENV_FILE, PROJECT_ROOT, Settings, get_settings


@pytest.fixture
def isolated_env(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("NOTION_TOKEN=test-file-token\nNOTION_PARENT_PAGE_ID=test-parent\n", encoding="utf-8")
    monkeypatch.setitem(Settings.model_config, "env_file", env_file)
    monkeypatch.delenv("NOTION_TOKEN", raising=False)
    monkeypatch.delenv("NOTION_PARENT_PAGE_ID", raising=False)
    get_settings.cache_clear()
    yield tmp_path
    get_settings.cache_clear()


def test_project_env_path_is_absolute():
    assert ENV_FILE == PROJECT_ROOT / ".env"
    assert ENV_FILE.is_absolute()


def test_settings_loads_same_env_from_project_and_other_cwd(isolated_env, monkeypatch):
    monkeypatch.chdir(PROJECT_ROOT)
    root = get_settings()
    get_settings.cache_clear()
    other_dir = isolated_env / "other-working-directory"
    other_dir.mkdir()
    monkeypatch.chdir(other_dir)
    elsewhere = get_settings()
    assert root.notion_token == elsewhere.notion_token == "test-file-token"
    assert root.notion_parent_page_id == elsewhere.notion_parent_page_id == "test-parent"
    expected_database = PROJECT_ROOT / "data" / "app.db"
    assert Path(make_url(root.database_url).database) == expected_database
    assert root.database_url == elsewhere.database_url


def test_os_environment_overrides_env_file(isolated_env, monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "test-os-token")
    get_settings.cache_clear()
    assert get_settings().notion_token == "test-os-token"
