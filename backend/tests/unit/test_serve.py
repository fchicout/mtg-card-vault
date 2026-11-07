"""FR-OPS-03: the API starts serving only after the migrations succeeded."""

from unittest import mock

import pytest

from mtgvault import serve


@pytest.fixture(autouse=True)
def environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@h/db")


def test_migrations_run_before_the_server_starts() -> None:
    calls: list[str] = []
    with (
        mock.patch.object(
            serve, "upgrade_to_head", side_effect=lambda url: calls.append("migrate")
        ),
        mock.patch.object(serve.uvicorn, "run", side_effect=lambda *a, **k: calls.append("serve")),
        mock.patch.object(serve, "configure_logging"),
    ):
        assert serve.main() == 0
    assert calls == ["migrate", "serve"]


def test_a_failed_migration_means_the_server_never_starts() -> None:
    with (
        mock.patch.object(serve, "upgrade_to_head", side_effect=RuntimeError("bad revision")),
        mock.patch.object(serve.uvicorn, "run") as run,
        mock.patch.object(serve, "configure_logging"),
    ):
        assert serve.main() == 1
    run.assert_not_called()


def test_invalid_configuration_stops_before_any_migration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL")
    with mock.patch.object(serve, "upgrade_to_head") as migrate, pytest.raises(SystemExit):
        serve.main()
    migrate.assert_not_called()


def test_the_server_listens_on_loopback_unless_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BIND_HOST", raising=False)
    with (
        mock.patch.object(serve, "upgrade_to_head"),
        mock.patch.object(serve.uvicorn, "run") as run,
        mock.patch.object(serve, "configure_logging"),
    ):
        serve.main()
    assert run.call_args.kwargs["host"] == "127.0.0.1"
    assert run.call_args.kwargs["port"] == 8000


def test_the_bind_address_is_configurable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BIND_HOST", "10.1.2.3")
    monkeypatch.setenv("BIND_PORT", "9000")
    with (
        mock.patch.object(serve, "upgrade_to_head"),
        mock.patch.object(serve.uvicorn, "run") as run,
        mock.patch.object(serve, "configure_logging"),
    ):
        serve.main()
    assert (run.call_args.kwargs["host"], run.call_args.kwargs["port"]) == ("10.1.2.3", 9000)
