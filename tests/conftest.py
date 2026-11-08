import pytest


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("PROXION_HOME", str(tmp_path / "home"))
    return tmp_path / "home"
