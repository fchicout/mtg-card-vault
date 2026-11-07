"""Tests for scripts/check_i18n_sync.py (standard library only: python3 -m unittest)."""

import io
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_i18n_sync as sync  # noqa: E402

TEMPLATE = """<?xml version="1.0" encoding="UTF-8" ?>
<xliff version="2.0" xmlns="urn:oasis:names:tc:xliff:document:2.0" srcLang="en">
  <file id="ngi18n" original="ng.template">
{units}
  </file>
</xliff>
"""


def unit(identifier: str, text: str, line: int = 1) -> str:
    return (f'    <unit id="{identifier}"><notes><note category="location">src/app/x.html:{line}</note></notes>'
            f"<segment><source>{text}</source></segment></unit>")


class Case(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)

    def write(self, name: str, *units: str) -> Path:
        path = self.dir / name
        path.write_text(TEMPLATE.format(units="\n".join(units)), encoding="utf-8")
        return path

    def run_main(self, *args: str) -> tuple[int, str]:
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            return sync.main(["x", *args]), out.getvalue()


class ComparisonTest(Case):
    def test_moved_lines_are_not_a_difference(self) -> None:
        a = self.write("a.xlf", unit("one", "Hello", line=3), unit("two", "World", line=9))
        b = self.write("b.xlf", unit("one", "Hello", line=30), unit("two", "World", line=91))
        self.assertEqual(self.run_main(str(a), str(b)), (0, "i18n messages are current.\n"))

    def test_added_removed_and_changed_messages_are_named(self) -> None:
        committed = self.write("a.xlf", unit("keep", "Same"), unit("gone", "Old"), unit("edit", "Before"))
        fresh = self.write("b.xlf", unit("keep", "Same"), unit("new", "Fresh"), unit("edit", "After"))
        status, output = self.run_main(str(committed), str(fresh))
        self.assertEqual(status, 1)
        self.assertIn("missing from the committed file: new", output)
        self.assertIn("no longer used (still committed): gone", output)
        self.assertIn("text changed: edit", output)
        self.assertIn("3 i18n message difference(s)", output)

    def test_whitespace_is_not_a_difference_but_inline_placeholders_are_compared(self) -> None:
        a = self.write("a.xlf", unit("p", 'Hello <ph id="0" equiv="NAME"/>  there'))
        b = self.write("b.xlf", unit("p", 'Hello\n  <ph id="0" equiv="NAME"/> there'))
        c = self.write("c.xlf", unit("p", 'Hello <ph id="0" equiv="OTHER"/> there'))
        self.assertEqual(self.run_main(str(a), str(b))[0], 0)
        self.assertEqual(self.run_main(str(a), str(c))[0], 1)

    def test_a_unit_without_source_is_an_error(self) -> None:
        bad = self.dir / "bad.xlf"
        bad.write_text(TEMPLATE.format(units='<unit id="x"><segment></segment></unit>'), encoding="utf-8")
        good = self.write("good.xlf", unit("x", "Hi"))
        self.assertEqual(self.run_main(str(bad), str(good))[0], 2)

    def test_usage_and_missing_or_broken_files_exit_two(self) -> None:
        good = self.write("good.xlf", unit("x", "Hi"))
        self.assertEqual(self.run_main()[0], 2)
        self.assertEqual(self.run_main(str(good), str(self.dir / "missing.xlf"))[0], 2)
        broken = self.dir / "broken.xlf"
        broken.write_text("<not-xml", encoding="utf-8")
        self.assertEqual(self.run_main(str(good), str(broken))[0], 2)

    def test_the_committed_messages_file_is_valid_xliff(self) -> None:
        committed = Path(__file__).resolve().parents[2] / "frontend" / "src" / "locale" / "messages.xlf"
        self.assertGreater(len(sync.messages(committed)), 30)


if __name__ == "__main__":
    unittest.main()
