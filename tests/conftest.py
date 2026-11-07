import pytest

from safehome import config


@pytest.fixture(autouse=True)
def offline_and_isolated(tmp_path, monkeypatch):
    """Every test uses its own database and the keyword reader, never the real API."""
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "")
    monkeypatch.setattr(config, "DEMO_MODE", False)
