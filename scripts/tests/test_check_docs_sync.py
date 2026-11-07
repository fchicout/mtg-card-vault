"""Tests for scripts/check_docs_sync.py (standard library only: python3 -m unittest).

Every negative case starts from a temporary copy of the real documentation set and breaks exactly
one thing, so the tests also prove the real set is in sync.
"""

import io
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_docs_sync as sync  # noqa: E402

REAL_DOCS = Path(__file__).resolve().parents[2] / "docs"


class DocsCase(unittest.TestCase):
    """A scratch copy of ``docs/`` that a test can break."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.docs = Path(self._tmp.name) / "docs"
        shutil.copytree(REAL_DOCS, self.docs)

    def edit(self, name: str, old: str, new: str, count: int = 1) -> None:
        path = self.docs / name
        text = path.read_text(encoding="utf-8")
        self.assertIn(old, text, f"fixture drift: {old!r} not found in {name}")
        path.write_text(text.replace(old, new, count), encoding="utf-8")

    def check(self) -> tuple[int, list[str]]:
        checker = sync.Checker(self.docs)
        out = io.StringIO()
        with redirect_stdout(out):
            status = checker.run()
        return status, checker.errors

    def assert_violation(self, fragment: str) -> None:
        status, errors = self.check()
        self.assertEqual(status, 1)
        self.assertTrue(any(fragment in e for e in errors), f"{fragment!r} not in {errors}")


class RealDocumentationTest(DocsCase):
    def test_the_real_documentation_set_is_in_sync(self) -> None:
        status, errors = self.check()
        self.assertEqual((status, errors), (0, []))


class StructureTest(DocsCase):
    def test_missing_document_is_reported(self) -> None:
        (self.docs / "04-use-cases.md").unlink()
        self.assert_violation("missing document")

    def test_missing_version_line(self) -> None:
        self.edit("05-architecture.md", "**Docs set version:**", "**Docs version:**")
        self.assert_violation("missing '**Docs set version:**'")

    def test_version_drift_between_documents(self) -> None:
        self.edit("05-architecture.md", "**Docs set version:** ", "**Docs set version:** 9.")
        self.assert_violation("docs set version differs")

    def test_newest_changelog_must_match_the_version(self) -> None:
        readme = (self.docs / "README.md").read_text(encoding="utf-8")
        self.assertIn("| 0.", readme)
        self.edit("README.md", "## 6. Changelog", "## 6. Changelog\n\n| 99.0.0 | x | y |", 1)
        self.assert_violation("newest changelog version differs")

    def test_changelog_without_rows(self) -> None:
        text = (self.docs / "README.md").read_text(encoding="utf-8")
        (self.docs / "README.md").write_text(re.sub(r"^\|\s*\d+\.\d+\.\d+\s*\|.*$", "", text, flags=re.M))
        self.assert_violation("changelog has no version row")


class DefinitionTest(DocsCase):
    def test_dangling_reference(self) -> None:
        self.edit("05-architecture.md", "# 5.", "FR-ZZZ-99 # 5.")
        self.assert_violation("reference to undefined ID FR-ZZZ-99")

    def test_duplicate_heading_definition(self) -> None:
        self.edit("02-user-stories.md", "### US-005 — Add a card to my vault",
                  "### US-005 — Add a card to my vault\n\n### US-005 — again")
        self.assert_violation("US-005 is defined 2 times as a heading")

    def test_duplicate_table_row(self) -> None:
        self.edit("01-project-charter.md", "| OQ-02 |", "| OQ-01 | duplicate | M0 | Open |\n| OQ-02 |")
        self.assert_violation("OQ-01 is defined 2 times as a row")


class TraceabilityTest(DocsCase):
    def test_dropped_story_link_between_srs_and_matrix(self) -> None:
        self.edit("06-traceability-matrix.md", "| FR-VLT-01 | US-005 |", "| FR-VLT-01 | US-006 |")
        self.assert_violation("requirement FR-VLT-01")

    def test_requirement_without_story(self) -> None:
        self.edit("03-requirements-specification.md", "| Must | US-005 |", "| Must | - |")
        status, errors = self.check()
        self.assertEqual(status, 1)
        self.assertTrue(any("traces to no user story" in e for e in errors))

    def test_story_dropping_a_requirement(self) -> None:
        self.edit("02-user-stories.md", "- **Requirements:** FR-VLT-01", "- **Requirements:** FR-VLT-02")
        self.assert_violation("story US-005")

    def test_story_without_requirements(self) -> None:
        text = (self.docs / "02-user-stories.md").read_text(encoding="utf-8")
        start, end = text.index("### US-005"), text.index("### US-006")
        block = re.sub(r"^- \*\*Requirements:\*\*.*$", "- **Requirements:** none", text[start:end], flags=re.M)
        (self.docs / "02-user-stories.md").write_text(text[:start] + block + text[end:], encoding="utf-8")
        self.assert_violation("US-005: lists no requirements in 02")

    def test_story_metadata_mismatch_with_the_matrix(self) -> None:
        self.edit("06-traceability-matrix.md", "| US-005 | EP-02 | 0.4.0 | Must |", "| US-005 | EP-02 | 0.4.0 | Should |")
        self.assert_violation("US-005: Priority")

    def test_story_release_must_be_a_milestone(self) -> None:
        self.edit("02-user-stories.md", "- **Release:** 0.4.0", "- **Release:** 7.7.7")
        self.edit("06-traceability-matrix.md", "| US-005 | EP-02 | 0.4.0 |", "| US-005 | EP-02 | 7.7.7 |")
        self.assert_violation("not a milestone in 01")

    def test_use_case_without_requirements(self) -> None:
        text = (self.docs / "04-use-cases.md").read_text(encoding="utf-8")
        start = text.index("### UC-03")
        block_end = text.index("### UC-04")
        block = text[start:block_end].replace("- **Requirements:**", "- **Needs:**")
        (self.docs / "04-use-cases.md").write_text(text[:start] + block + text[block_end:], encoding="utf-8")
        self.assert_violation("UC-03: lists no requirements in 04")

    def test_requirement_missing_from_the_matrix(self) -> None:
        text = (self.docs / "06-traceability-matrix.md").read_text(encoding="utf-8")
        kept = "\n".join(line for line in text.splitlines() if not line.startswith("| FR-VLT-01 |"))
        (self.docs / "06-traceability-matrix.md").write_text(kept, encoding="utf-8")
        self.assert_violation("FR-VLT-01: missing from the traceability matrix")

    def test_matrix_row_needs_components_and_tests(self) -> None:
        self.edit("06-traceability-matrix.md", "| API-VAULT, ADP-DB, FE-VAULT | U, I, C |", "|  |  |")
        self.assert_violation("matrix row needs components and tests")


class ObjectiveAndAdrTest(DocsCase):
    def test_adr_without_requirements(self) -> None:
        self.edit("06-traceability-matrix.md", "| ADR-014 | NFR-DOC-01 |", "| ADR-014 | - |")
        self.assert_violation("ADR-014: not mapped to requirements")

    def test_objective_without_requirements(self) -> None:
        text = (self.docs / "06-traceability-matrix.md").read_text(encoding="utf-8")
        (self.docs / "06-traceability-matrix.md").write_text(re.sub(r"^\| BO-05 \|.*$", "| BO-05 | - |", text, flags=re.M))
        self.assert_violation("BO-05: no requirements in the matrix")


class ReferenceScanTest(unittest.TestCase):
    KNOWN = {"US-001", "FR-VLT-01", "NFR-DOC-01"}

    def test_known_ids_pass_and_unknown_ids_are_named(self) -> None:
        messages = sync.unknown_references(
            self.KNOWN, {"commit a": "feat [US-001, FR-VLT-01]", "commit b": "fix [US-999, NFR-ZZZ-01]"}
        )
        self.assertEqual(messages, ["commit b: references unknown ID NFR-ZZZ-01",
                                    "commit b: references unknown ID US-999"])

    def test_text_without_ids_is_fine(self) -> None:
        self.assertEqual(sync.unknown_references(self.KNOWN, {"x": "plain message, issue #12"}), [])

    def test_code_markers_are_found_and_skipped_directories_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.py").write_text("x = 1\n# Implements: US-001, US-404\n", encoding="utf-8")
            (root / "b.txt").write_text("Implements: US-777\n", encoding="utf-8")
            (root / "node_modules").mkdir()
            (root / "node_modules" / "c.ts").write_text("// Implements: US-888\n", encoding="utf-8")
            markers = sync.code_markers([root])
        self.assertEqual(list(markers.values()), [" US-001, US-404"])
        self.assertTrue(next(iter(markers)).endswith("a.py:2"))

    def test_commit_messages_come_from_git(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            def git(*args: str) -> None:
                subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *args],  # noqa: S603, S607
                               cwd=tmp, check=True, capture_output=True)

            git("init", "-q")
            git("commit", "-q", "--allow-empty", "-m", "feat: first [US-001]")
            git("commit", "-q", "--allow-empty", "-m", "feat: second [US-404]\n\nbody FR-VLT-01")
            messages = sync.commit_messages("HEAD", Path(tmp))
        self.assertEqual(len(messages), 2)
        self.assertTrue(any("US-404" in text and "FR-VLT-01" in text for text in messages.values()))


class CommandLineTest(DocsCase):
    def run_main(self, *args: str) -> tuple[int, str]:
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            status = sync.main(["check_docs_sync.py", str(self.docs), *args])
        return status, out.getvalue()

    def test_in_sync_exits_zero(self) -> None:
        status, output = self.run_main()
        self.assertEqual(status, 0)
        self.assertIn("in sync", output)

    def test_violation_exits_one(self) -> None:
        self.edit("05-architecture.md", "**Docs set version:** ", "**Docs set version:** 9.")
        status, output = self.run_main()
        self.assertEqual(status, 1)
        self.assertIn("violation(s)", output)

    def test_unknown_marker_warns_but_passes_unless_strict(self) -> None:
        code = Path(self._tmp.name) / "code"
        code.mkdir()
        (code / "m.py").write_text("# Implements: US-404\n", encoding="utf-8")
        status, output = self.run_main("--code", str(code))
        self.assertEqual(status, 0)
        self.assertIn("WARNING", output)
        status, output = self.run_main("--code", str(code), "--strict-refs")
        self.assertEqual(status, 1)
        self.assertIn("ERROR: ", output)

    def test_known_marker_is_clean(self) -> None:
        code = Path(self._tmp.name) / "code"
        code.mkdir()
        (code / "m.py").write_text("# Implements: US-005\n", encoding="utf-8")
        status, output = self.run_main("--code", str(code), "--strict-refs")
        self.assertEqual(status, 0)
        self.assertIn("0 unknown reference(s)", output)

    def test_a_bad_commit_range_exits_two(self) -> None:
        status, output = self.run_main("--commits", "no-such-revision..also-missing")
        self.assertEqual(status, 2)
        self.assertIn("cannot read commits", output)

    def test_reference_scan_is_skipped_when_the_docs_are_broken(self) -> None:
        (self.docs / "04-use-cases.md").unlink()
        status, _ = self.run_main("--commits", "HEAD")
        self.assertEqual(status, 1)


if __name__ == "__main__":
    unittest.main()
