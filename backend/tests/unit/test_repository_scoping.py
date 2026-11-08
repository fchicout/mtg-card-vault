"""No vault repository method can run without a user id (FR-VLT-07, US-011)."""

import ast
import inspect
import textwrap

from mtgvault.adapters.db import vault_repository
from mtgvault.adapters.db.vault_repository import SqlAlchemyVaultRepository
from mtgvault.application.ports import VaultRepository


def public_methods(cls: type) -> list[tuple[str, list[str]]]:
    found = []
    for name, member in inspect.getmembers(cls, inspect.isfunction):
        if not name.startswith("_"):
            found.append((name, list(inspect.signature(member).parameters)[1:]))
    return found


def test_every_public_method_of_the_port_takes_the_user_id_first() -> None:
    methods = public_methods(VaultRepository)
    assert methods, "the port lost its methods"
    for name, parameters in methods:
        assert parameters[:1] == ["user_id"], f"{name} must take user_id first"


def test_every_public_method_of_the_adapter_takes_the_user_id_first() -> None:
    for name, parameters in public_methods(SqlAlchemyVaultRepository):
        assert parameters[:1] == ["user_id"], f"{name} must take user_id first"


def test_every_statement_that_touches_entries_filters_by_the_user() -> None:
    """Each select/update/delete on the entries table in the adapter mentions ``user_id``."""
    source = textwrap.dedent(inspect.getsource(vault_repository))
    tree = ast.parse(source)
    offenders = []
    for function in ast.walk(tree):
        if not isinstance(function, ast.FunctionDef) or function.name.startswith("__"):
            continue
        text = ast.get_source_segment(source, function) or ""
        touches = any(word in text for word in ("select(", "update(", "delete(", "insert("))
        if touches and "VaultEntryRow" in text and "user_id" not in text:
            offenders.append(function.name)
    assert offenders == []
