"""Tests for scripts/security_exceptions.py (standard library only: python3 -m unittest)."""

import datetime as dt
import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import security_exceptions as sec  # noqa: E402

TODAY = dt.date(2026, 11, 7)


def entry(**overrides: str) -> dict[str, str]:
    base = {"id": "GHSA-aaaa-bbbb-cccc", "tool": "npm-audit", "justification": "Not reachable: dev-only tooling.",
            "owner": "fchicout", "expires": "2026-12-31"}
    return {**base, **overrides}


YAML = """\
# comment
exceptions:
  - id: CVE-2026-0001
    tool: trivy
    justification: "No fixed package yet, code path unreachable."   # trailing comment
    owner: fchicout
    expires: 2026-12-31
  - id: GHSA-aaaa-bbbb-cccc
    tool: npm-audit
    justification: 'Dev-only dependency without network access.'
    owner: fchicout
    expires: 2026-11-30
"""


class ParseTest(unittest.TestCase):
    def test_empty_list(self) -> None:
        self.assertEqual(sec.parse("# nothing\nexceptions: []\n"), [])

    def test_entries_quotes_and_comments(self) -> None:
        parsed = sec.parse(YAML)
        self.assertEqual([e["id"] for e in parsed], ["CVE-2026-0001", "GHSA-aaaa-bbbb-cccc"])
        self.assertEqual(parsed[0]["justification"], "No fixed package yet, code path unreachable.")
        self.assertEqual(parsed[1]["justification"], "Dev-only dependency without network access.")

    def test_a_file_that_ends_after_the_key_has_no_entries(self) -> None:
        self.assertEqual(sec.parse("exceptions:\n"), [])

    def test_errors(self) -> None:
        for text, fragment in (
            ("", "empty"),
            ("something: else\n", "expected 'exceptions:'"),
            ("exceptions:\n  id: x\n", "must start with"),
            ("exceptions:\n  - just text\n", "expected 'key: value'"),
        ):
            with self.assertRaises(sec.ExceptionsError, msg=text) as raised:
                sec.parse(text)
            self.assertIn(fragment, str(raised.exception))


class ValidateTest(unittest.TestCase):
    def check(self, *entries: dict[str, str]) -> tuple[list[str], list[dict[str, str]]]:
        return sec.validate(list(entries), TODAY)

    def test_valid_entry_is_active(self) -> None:
        errors, active = self.check(entry())
        self.assertEqual((errors, len(active)), ([], 1))

    def test_expiring_today_is_still_valid_and_yesterday_is_not(self) -> None:
        self.assertEqual(self.check(entry(expires="2026-11-07"))[0], [])
        errors, active = self.check(entry(expires="2026-11-06"))
        self.assertIn("EXPIRED on 2026-11-06", errors[0])
        self.assertEqual(active, [])

    def test_too_far_in_the_future(self) -> None:
        errors, _ = self.check(entry(expires="2027-06-01"))
        self.assertIn("more than 90 days", errors[0])
        self.assertEqual(self.check(entry(expires="2027-02-05"))[0], [])

    def test_each_invalid_shape_is_reported(self) -> None:
        cases = {
            "missing": {k: v for k, v in entry().items() if k != "owner"},
            "unknown field": entry(extra="x"),
            "tool must be": entry(tool="snyk"),
            "unexpected characters": entry(id="bad id!"),
            "too short": entry(justification="because"),
            "YYYY-MM-DD": entry(expires="31/12/2026"),
        }
        for fragment, bad in cases.items():
            errors, active = self.check(bad)
            self.assertTrue(errors and fragment in errors[0], f"{fragment}: {errors}")
            self.assertEqual(active, [])

    def test_duplicate_for_the_same_tool(self) -> None:
        errors, active = self.check(entry(), entry())
        self.assertIn("listed twice", errors[0])
        self.assertEqual(len(active), 1)

    def test_same_id_for_two_tools_is_fine(self) -> None:
        self.assertEqual(self.check(entry(), entry(tool="trivy"))[0], [])

    def test_active_ids_per_tool(self) -> None:
        _, active = self.check(entry(id="B-2"), entry(id="A-1"), entry(id="C-3", tool="trivy"))
        self.assertEqual(sec.active_ids(active, "npm-audit"), ["A-1", "B-2"])
        self.assertEqual(sec.active_ids(active, "trivy"), ["C-3"])
        self.assertEqual(sec.active_ids(active, "pip-audit"), [])


REPORT = {
    "vulnerabilities": {
        "left-pad": {"severity": "high", "fixAvailable": True,
                     "via": [{"url": "https://github.com/advisories/GHSA-aaaa-bbbb-cccc", "severity": "high"}]},
        "wrapper": {"severity": "high", "fixAvailable": False, "via": ["left-pad"]},
        "mild": {"severity": "low", "via": [{"url": "https://github.com/advisories/GHSA-low"}]},
        "loop-a": {"severity": "high", "via": ["loop-b"]},
        "loop-b": {"severity": "high", "via": ["loop-a"]},
        "bare": {"severity": "critical", "via": []},
        "ghost": {"severity": "high", "via": ["not-in-report"]},
    }
}


class AuditTest(unittest.TestCase):
    def test_blocking_without_exceptions(self) -> None:
        self.assertEqual(sec.blocking_vulnerabilities(REPORT, "high", set()), ["bare", "left-pad", "wrapper"])

    def test_threshold_filters_by_severity(self) -> None:
        self.assertIn("mild", sec.blocking_vulnerabilities(REPORT, "low", set()))
        self.assertNotIn("mild", sec.blocking_vulnerabilities(REPORT, "high", set()))
        self.assertEqual(sec.blocking_vulnerabilities(REPORT, "critical", set()), ["bare"])

    def test_an_exception_excuses_the_advisory_and_what_depends_on_it(self) -> None:
        blocking = sec.blocking_vulnerabilities(REPORT, "high", {"GHSA-aaaa-bbbb-cccc"})
        self.assertEqual(blocking, ["bare"])

    def test_cycles_and_unknown_packages_do_not_block_by_themselves(self) -> None:
        blocking = sec.blocking_vulnerabilities(REPORT, "high", {"GHSA-aaaa-bbbb-cccc"})
        self.assertNotIn("loop-a", blocking)
        self.assertNotIn("ghost", blocking)

    def test_advisory_id_from_url(self) -> None:
        self.assertEqual(sec.advisory_id("https://github.com/advisories/GHSA-x-y-z/"), "GHSA-x-y-z")
        self.assertEqual(sec.advisory_id(""), "")

    def test_run_npm_audit_parses_and_fails_closed(self) -> None:
        def fake(stdout: str, code: int = 1) -> mock.Mock:
            return mock.Mock(return_value=subprocess.CompletedProcess([], code, stdout=stdout, stderr="boom"))

        with mock.patch.object(sec.subprocess, "run", fake(json.dumps(REPORT))) as run:
            self.assertEqual(sec.run_npm_audit("frontend", "dev"), REPORT)
            self.assertIn("--omit", run.call_args.args[0])
        for bad in ("not json", json.dumps({"error": {"summary": "needs a lockfile"}}), json.dumps({"metadata": {}}), "[]"):
            with mock.patch.object(sec.subprocess, "run", fake(bad)), self.assertRaises(RuntimeError):
                sec.run_npm_audit("frontend", None)


class CommandLineTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.file = Path(self._tmp.name) / "exceptions.yaml"

    def write(self, text: str) -> None:
        self.file.write_text(text, encoding="utf-8")

    def run_main(self, *args: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            status = sec.main(["x", *args, "--file", str(self.file), "--today", TODAY.isoformat()])
        return status, out.getvalue(), err.getvalue()

    def test_check_lists_active_exceptions(self) -> None:
        self.write(YAML)
        status, out, _ = self.run_main("check")
        self.assertEqual(status, 0)
        self.assertIn("2 active", out)
        self.assertIn("trivy: CVE-2026-0001 until 2026-12-31", out)

    def test_an_expired_exception_fails_every_command(self) -> None:
        self.write(YAML.replace("2026-11-30", "2026-10-01"))
        for command in (["check"], ["ids", "--tool", "trivy"], ["npm-audit"]):
            status, out, _ = self.run_main(*command)
            self.assertEqual(status, 1, command)
            self.assertIn("EXPIRED", out)

    def test_ids_as_lines_and_as_flags(self) -> None:
        self.write(YAML)
        self.assertEqual(self.run_main("ids", "--tool", "trivy")[1].strip(), "CVE-2026-0001")
        status, out, _ = self.run_main("ids", "--tool", "pip-audit", "--flag=--ignore-vuln")
        self.assertEqual((status, out.strip()), (0, ""))
        self.write(YAML.replace("tool: npm-audit", "tool: pip-audit"))
        self.assertEqual(self.run_main("ids", "--tool", "pip-audit", "--flag=--ignore-vuln")[1].strip(),
                         "--ignore-vuln GHSA-aaaa-bbbb-cccc")

    def test_ids_requires_a_tool(self) -> None:
        self.write("exceptions: []\n")
        with self.assertRaises(SystemExit), redirect_stderr(io.StringIO()):
            self.run_main("ids")

    def test_bad_or_missing_file_exits_two(self) -> None:
        self.write("nonsense\n")
        self.assertEqual(self.run_main("check")[0], 2)
        self.file.unlink()
        self.assertEqual(self.run_main("check")[0], 2)

    def test_seeded_vulnerability_fails_then_a_timeboxed_exception_passes_until_it_expires(self) -> None:
        self.write("exceptions: []\n")
        with mock.patch.object(sec, "run_npm_audit", return_value=REPORT):
            status, out, _ = self.run_main("npm-audit", "--level", "high")
            self.assertEqual(status, 1)
            self.assertIn("BLOCKING: left-pad", out)

            self.write("""exceptions:
  - id: GHSA-aaaa-bbbb-cccc
    tool: npm-audit
    justification: Dev-only dependency, fix scheduled for the next sprint.
    owner: fchicout
    expires: 2026-12-01
  - id: bare-is-not-covered
    tool: npm-audit
    justification: Dev-only dependency, fix scheduled for the next sprint.
    owner: fchicout
    expires: 2026-12-01
""")
            status, out, _ = self.run_main("npm-audit", "--level", "critical")
            self.assertEqual(status, 1)  # 'bare' has no advisory to except
            status, out, _ = self.run_main("npm-audit", "--level", "high")
            self.assertEqual(status, 1)
            self.assertIn("BLOCKING: bare", out)
            self.assertNotIn("BLOCKING: left-pad", out)

    def test_exception_passes_when_it_covers_everything_and_fails_after_expiry(self) -> None:
        report = {"vulnerabilities": {"left-pad": REPORT["vulnerabilities"]["left-pad"]}}
        text = """exceptions:
  - id: GHSA-aaaa-bbbb-cccc
    tool: npm-audit
    justification: Dev-only dependency, fix scheduled for the next sprint.
    owner: fchicout
    expires: 2026-12-01
"""
        self.write(text)
        with mock.patch.object(sec, "run_npm_audit", return_value=report):
            status, out, _ = self.run_main("npm-audit")
            self.assertEqual(status, 0)
            self.assertIn("1 exception(s) applied", out)
            self.write(text.replace("2026-12-01", "2026-11-01"))
            self.assertEqual(self.run_main("npm-audit")[0], 1)

    def test_npm_audit_tool_error_exits_two(self) -> None:
        self.write("exceptions: []\n")
        with mock.patch.object(sec, "run_npm_audit", side_effect=RuntimeError("no lockfile")):
            status, _, err = self.run_main("npm-audit")
        self.assertEqual(status, 2)
        self.assertIn("no lockfile", err)

    def test_the_committed_exceptions_file_is_valid_today(self) -> None:
        errors, _ = sec.load(sec.DEFAULT_FILE, dt.date.today())
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
