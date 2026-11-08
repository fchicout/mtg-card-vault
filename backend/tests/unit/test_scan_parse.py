import pytest

from mtgvault.domain.scan import CollectorInfo, clean_title, parse_collector


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Eliminate", "Eliminate"),
        ("  Lightning   Bolt \n", "Lightning Bolt"),
        ("Jaya's Firenado", "Jaya's Firenado"),
        ("Jaya\u2019s Firenado", "Jaya's Firenado"),
        ("|Abandon the Post", "Abandon the Post"),
        ("Black Lotus 3 @", "Black Lotus"),
        ("Fire // Ice", "Fire Ice"),  # the slashes are noise; the lookup is fuzzy
        ("Cataclysmic Gearhulk 4 W W", "Cataclysmic Gearhulk"),
        ("Æther Vial", "Aether Vial"),
        ("Sol Ring,", "Sol Ring"),
        ("Dismember~~", "Dismember"),
    ],
)
def test_titles_are_cleaned(raw: str, expected: str) -> None:
    assert clean_title(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", "12 34", "@#$%^&", "ab", "x" * 80, "1 2 3 4 5 6 a"])
def test_unreadable_titles_are_none_never_a_guess(raw: str) -> None:
    assert clean_title(raw) is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("097/274 U\nM21 • EN", CollectorInfo("97", "274", "m21")),
        ("127/277 C MID * EN", CollectorInfo("127", "277", "mid")),
        ("0123 R", CollectorInfo("123", None, None)),
        ("O97/274", CollectorInfo("97", "274", None)),  # O read for 0
        ("l34/281 C\nDMU • EN", CollectorInfo("134", "281", "dmu")),  # l read for 1
        ("MH2 • EN", CollectorInfo(None, None, "mh2")),
        ("", CollectorInfo()),
        ("hello world", CollectorInfo()),
        ("  15/380  \n  NEO  EN  ", CollectorInfo("15", "380", "neo")),
    ],
)
def test_collector_band(raw: str, expected: CollectorInfo) -> None:
    assert parse_collector(raw) == expected


def test_a_lone_two_digit_number_is_not_trusted() -> None:
    assert parse_collector("45").number is None


def test_leading_zeros_are_removed_but_zero_stays() -> None:
    assert parse_collector("000/100").number == "0"
