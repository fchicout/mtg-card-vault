import pytest

from mtgvault.config import load_settings


def test_valid_environment_is_loaded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@h/db")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    settings = load_settings()
    assert settings.log_level == "DEBUG"


def test_log_level_defaults_to_info(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@h/db")
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    assert load_settings().log_level == "INFO"


def test_invalid_configuration_exits_non_zero_with_a_clear_message(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:hunter2@h/db")
    monkeypatch.setenv("LOG_LEVEL", "LOUD")
    with pytest.raises(SystemExit) as exit_info:
        load_settings()
    assert exit_info.value.code == 2
    message = capsys.readouterr().err
    assert "LOG_LEVEL" in message
    assert "refusing to start" in message
    assert "hunter2" not in message  # configuration values are never echoed


def test_missing_database_url_is_named(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(SystemExit):
        load_settings()
    assert "DATABASE_URL" in capsys.readouterr().err
