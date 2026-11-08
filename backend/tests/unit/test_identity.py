import logging

import pytest

from mtgvault.domain.identity import MAX_DISPLAY_NAME, Principal, principal_from_claims


def test_full_claims() -> None:
    principal = principal_from_claims(
        {"sub": "u1", "name": "Ada Lovelace", "email": "Ada@Example.org", "groups": ["x"]}
    )
    assert principal == Principal("u1", "Ada Lovelace", "ada@example.org")


def test_minimal_claims_never_fail() -> None:
    assert principal_from_claims({"sub": "u1"}) == Principal("u1", None, None)


def test_username_is_the_fallback_for_the_name() -> None:
    assert principal_from_claims({"sub": "u1", "preferred_username": "ada"}).display_name == "ada"
    named = principal_from_claims({"sub": "u1", "name": "Ada", "preferred_username": "ada"})
    assert named.display_name == "Ada"


@pytest.mark.parametrize("name", [None, 5, ["a"], "", "   ", "\x00\x01"])
def test_unusable_names_are_ignored(name: object) -> None:
    assert principal_from_claims({"sub": "u1", "name": name}).display_name is None


def test_names_are_cleaned_and_bounded() -> None:
    cleaned = principal_from_claims({"sub": "u1", "name": "  Ada\n\tLove\x00lace  "}).display_name
    assert cleaned == "Ada Love lace"
    long = principal_from_claims({"sub": "u1", "name": "x" * 500}).display_name
    assert long is not None
    assert len(long) == MAX_DISPLAY_NAME


@pytest.mark.parametrize(
    "email", ["nope", "a@b", "@x.org", 7, None, "a b@c.org", "x" * 300 + "@a.org"]
)
def test_invalid_emails_are_dropped(email: object) -> None:
    assert principal_from_claims({"sub": "u1", "email": email}).email is None


@pytest.mark.parametrize("sub", [None, "", "  ", 5])
def test_a_subject_is_mandatory(sub: object) -> None:
    with pytest.raises(ValueError, match="subject"):
        principal_from_claims({"sub": sub})


def test_the_email_never_shows_in_repr_or_logs(caplog: pytest.LogCaptureFixture) -> None:
    principal = principal_from_claims({"sub": "u1", "email": "ada@example.org"})
    with caplog.at_level(logging.DEBUG):
        logging.getLogger("t").info("principal %r", principal)
    assert "ada@example.org" not in repr(principal)
    assert "ada@example.org" not in caplog.text
