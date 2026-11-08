"""Tests for scripts/check_commit_policy.py (standard library only: python3 -m unittest)."""

import io
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_commit_policy as policy  # noqa: E402


class MessageTest(unittest.TestCase):
    def test_well_formed_headers_pass(self) -> None:
        for header in (
            "feat(vault): add entry endpoint [US-005, FR-VLT-01]",
            "fix(api): reject empty names [FR-API-02]",
            "docs: update the charter",
            "chore(repo)!: drop the old layout",
            "spike(ui): try the datagrid",
            "build(deps): bump httpx from 0.28 to 0.29",
        ):
            self.assertEqual(policy.check_message(header), ([], []), header)

    def test_not_conventional(self) -> None:
        errors, _ = policy.check_message("updated some stuff")
        self.assertIn("not a Conventional Commit", errors[0])

    def test_unknown_type_scope_and_period(self) -> None:
        self.assertTrue(policy.check_message("wip(vault): thing")[0])
        errors, _ = policy.check_message("docs(nonsense): thing")
        self.assertIn("unknown scope 'nonsense'", errors[0])
        errors, _ = policy.check_message("docs: ends with a period.")
        self.assertIn("period", errors[0])

    def test_header_length_ignores_the_trailing_id_list(self) -> None:
        subject = "x" * 80
        self.assertEqual(policy.check_message(f"docs: {subject} [US-001, FR-VLT-01, NFR-DOC-01, UC-02]")[0], [])
        errors, _ = policy.check_message("docs: " + "x" * 100)
        self.assertIn("limit is 100", errors[0])

    def test_feat_and_fix_need_an_id(self) -> None:
        errors, warnings = policy.check_message("feat(vault): add the thing")
        self.assertEqual(errors, [])
        self.assertIn("references no story", warnings[0])
        errors, warnings = policy.check_message("fix(vault): repair the thing", require_ids="error")
        self.assertEqual(warnings, [])
        self.assertIn("references no story", errors[0])
        self.assertEqual(policy.check_message("docs: no id needed"), ([], []))

    def test_an_id_in_the_body_counts(self) -> None:
        self.assertEqual(policy.check_message("feat(vault): add the thing\n\nImplements US-005"), ([], []))

    def test_exempt_messages(self) -> None:
        for header in ("Merge pull request #1 from x/y", 'Revert "feat: x"', "fixup! feat: x", "squash! y"):
            self.assertEqual(policy.check_message(header), ([], []), header)

    def test_empty_message(self) -> None:
        self.assertEqual(policy.check_message("  \n")[0], ["empty commit message"])


class BranchAndTagTest(unittest.TestCase):
    def test_valid_branches(self) -> None:
        for branch in ("develop", "main", "feature/db-foundation", "feature/a.b_c", "release/1.0.0",
                       "hotfix/0.4.1", "dependabot/npm_and_yarn/x"):
            self.assertEqual(policy.check_branch(branch), [], branch)

    def test_invalid_branches(self) -> None:
        for branch in ("fix/thing", "feature/", "feature/Upper", "release/1.0", "release/01.0.0",
                       "hotfix/v1.0.0", "my-branch", "spike/x"):
            self.assertTrue(policy.check_branch(branch), branch)

    def test_release_version_must_be_newer_than_the_latest_tag(self) -> None:
        self.assertEqual(policy.check_branch("release/0.2.0", "v0.1.0"), [])
        self.assertIn("not newer", policy.check_branch("release/0.1.0", "v0.1.0")[0])
        self.assertIn("not newer", policy.check_branch("hotfix/0.0.9", "v0.1.0")[0])
        self.assertEqual(policy.check_branch("feature/x", "v9.9.9"), [])

    def test_tags(self) -> None:
        for tag in ("v0.1.0", "v1.2.3", "v1.0.0-rc.1", "v1.0.0-alpha", "v1.0.0+build.5", "v10.20.30"):
            self.assertEqual(policy.check_tag(tag), [], tag)
        for tag in ("1.0.0", "v1.0", "v01.0.0", "release-1", "v1.0.0-", "v1.0.0.0"):
            self.assertTrue(policy.check_tag(tag), tag)


class GitTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo = Path(self._tmp.name)
        previous = Path.cwd()
        os.chdir(self.repo)
        self.addCleanup(os.chdir, previous)
        self.git("init", "-q")

    def git(self, *args: str) -> None:
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *args],  # noqa: S603, S607
                       cwd=self.repo, check=True, capture_output=True)

    def commit(self, message: str) -> None:
        self.git("commit", "-q", "--allow-empty", "-m", message)

    def run_main(self, *args: str) -> tuple[int, str]:
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            status = policy.main(["check_commit_policy.py", *args])
        return status, out.getvalue()

    def test_range_checks_every_commit_and_skips_merges(self) -> None:
        self.commit("chore: root")
        self.git("tag", "base")
        self.commit("feat(vault): ok [US-005]")
        self.commit("bad message")
        status, output = self.run_main("--range", "base..HEAD")
        self.assertEqual(status, 1)
        self.assertIn("not a Conventional Commit", output)
        self.assertIn("Checked 2 commit message(s)", output)

    def test_clean_range_exits_zero_and_warnings_do_not_fail(self) -> None:
        self.commit("chore: root")
        self.git("tag", "base")
        self.commit("feat(vault): no id here")
        status, output = self.run_main("--range", "base..HEAD")
        self.assertEqual(status, 0)
        self.assertIn("WARNING", output)
        status, _ = self.run_main("--range", "base..HEAD", "--require-ids", "error")
        self.assertEqual(status, 1)

    def test_message_file_is_checked(self) -> None:
        path = self.repo / "MSG"
        path.write_text("docs: fine\n", encoding="utf-8")
        self.assertEqual(self.run_main("--message-file", str(path))[0], 0)
        path.write_text("nope\n", encoding="utf-8")
        self.assertEqual(self.run_main("--message-file", str(path))[0], 1)

    def test_latest_version_tag_ignores_prereleases_and_foreign_tags(self) -> None:
        self.commit("chore: root")
        self.assertIsNone(policy.latest_version_tag())
        for tag in ("v0.1.0", "v0.2.0", "v0.10.0", "v1.0.0-rc.1", "nightly"):
            self.git("tag", tag)
        self.assertEqual(policy.latest_version_tag(), "v0.10.0")
        status, output = self.run_main("--branch", "release/0.9.0")
        self.assertEqual(status, 1)
        self.assertIn("not newer", output)
        self.assertEqual(self.run_main("--branch", "release/0.11.0")[0], 0)

    def test_tag_option(self) -> None:
        self.assertEqual(self.run_main("--tag", "v1.0.0-rc.1")[0], 0)
        self.assertEqual(self.run_main("--tag", "1.0")[0], 1)

    def test_git_errors_exit_two(self) -> None:
        status, _ = self.run_main("--range", "no-such..revision")
        self.assertEqual(status, 2)

    def test_nothing_to_check_is_a_usage_error(self) -> None:
        with self.assertRaises(SystemExit) as raised, redirect_stderr(io.StringIO()):
            policy.main(["check_commit_policy.py"])
        self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
