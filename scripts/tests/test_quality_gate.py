"""Tests for scripts/quality_gate.py (standard library only: python3 -m unittest)."""

import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import quality_gate as gate  # noqa: E402

DIFF = """\
diff --git a/backend/src/mtgvault/a.py b/backend/src/mtgvault/a.py
--- a/backend/src/mtgvault/a.py
+++ b/backend/src/mtgvault/a.py
@@ -3,0 +4,2 @@ context
+one
+two
@@ -10 +12 @@ other
-old
+new
diff --git a/old.txt b/old.txt
--- a/old.txt
+++ /dev/null
@@ -1,2 +0,0 @@
-gone
-gone
diff --git a/frontend/src/app/x.ts b/frontend/src/app/x.ts
--- /dev/null
+++ b/frontend/src/app/x.ts
@@ -0,0 +1,3 @@
+a
+b
+c
"""

COBERTURA = """<?xml version="1.0"?>
<coverage><sources><source>src</source></sources><packages><package><classes>
<class name="a.py" filename="mtgvault/a.py"><lines>
<line number="4" hits="1"/><line number="5" hits="0"/><line number="12" hits="3"/>
</lines></class></classes></package></packages></coverage>"""

LCOV = """TN:
SF:src/app/x.ts
DA:1,1
DA:2,0
DA:3,2
end_of_record
SF:src/app/y.ts
DA:1,1
end_of_record
"""


class DiffParsingTest(unittest.TestCase):
    def test_added_lines_per_file(self) -> None:
        added = gate.parse_added_lines(DIFF)
        self.assertEqual(added["backend/src/mtgvault/a.py"], {4, 5, 12})
        self.assertEqual(added["frontend/src/app/x.ts"], {1, 2, 3})

    def test_deleted_files_are_ignored(self) -> None:
        self.assertNotIn("old.txt", gate.parse_added_lines(DIFF))
        self.assertNotIn("/dev/null", gate.parse_added_lines(DIFF))


class CoverageParsingTest(unittest.TestCase):
    def test_cobertura_paths_include_prefix_and_source(self) -> None:
        parsed = gate.parse_cobertura(COBERTURA, "backend")
        self.assertEqual(parsed, {"backend/src/mtgvault/a.py": {4: 1, 5: 0, 12: 3}})

    def test_lcov_paths_include_prefix(self) -> None:
        parsed = gate.parse_lcov(LCOV, "frontend")
        self.assertEqual(parsed["frontend/src/app/x.ts"], {1: 1, 2: 0, 3: 2})
        self.assertEqual(parsed["frontend/src/app/y.ts"], {1: 1})


class NewCodeCoverageTest(unittest.TestCase):
    def test_only_added_executable_lines_count(self) -> None:
        added = gate.parse_added_lines(DIFF)
        backend = gate.parse_cobertura(COBERTURA, "backend")
        frontend = gate.parse_lcov(LCOV, "frontend")
        self.assertEqual(gate.new_code_coverage(added, backend), (2, 3))
        self.assertEqual(gate.new_code_coverage(added, frontend), (2, 3))

    def test_untouched_files_are_not_counted(self) -> None:
        self.assertEqual(gate.new_code_coverage({}, gate.parse_lcov(LCOV, "frontend")), (0, 0))

    def test_condition_passes_at_the_threshold(self) -> None:
        self.assertEqual(gate.coverage_condition("X", 4, 5, 80.0).status, gate.PASS)

    def test_condition_fails_below_the_threshold(self) -> None:
        condition = gate.coverage_condition("X", 3, 5, 80.0)
        self.assertEqual(condition.status, gate.FAIL)
        self.assertEqual(condition.actual, "60.0%")

    def test_no_new_executable_lines_is_not_a_failure(self) -> None:
        self.assertEqual(gate.coverage_condition("X", 0, 0, 80.0).status, gate.PASS)


class SonarConditionsTest(unittest.TestCase):
    CLEAN = gate.IssueCounts(bugs=0, vulnerabilities=0, blocker_or_critical=0)

    def statuses(self, counts: gate.IssueCounts, hotspots: float | None = 0.0,
                 maintainability: float | None = 1.0) -> dict[str, str]:
        return {c.name: c.status for c in gate.sonar_conditions(counts, hotspots, maintainability)}

    def test_clean_project_passes_everything(self) -> None:
        self.assertEqual(set(self.statuses(self.CLEAN).values()), {gate.PASS})

    def test_each_condition_can_fail_independently(self) -> None:
        cases = {
            "Open bugs (reliability rating A)": self.statuses(gate.IssueCounts(1, 0, 0)),
            "Open vulnerabilities (security rating A)": self.statuses(gate.IssueCounts(0, 2, 0)),
            "Open Blocker/Critical issues": self.statuses(gate.IssueCounts(0, 0, 1)),
            "Security hotspots to review": self.statuses(self.CLEAN, hotspots=3.0),
            "Maintainability rating": self.statuses(self.CLEAN, maintainability=2.0),
        }
        for name, statuses in cases.items():
            with self.subTest(name):
                self.assertEqual(statuses[name], gate.FAIL)

    def test_unreadable_extras_are_skipped_not_passed(self) -> None:
        statuses = self.statuses(self.CLEAN, hotspots=None, maintainability=None)
        self.assertEqual(statuses["Security hotspots to review"], gate.SKIPPED)
        self.assertEqual(statuses["Maintainability rating"], gate.SKIPPED)

    def test_verdict_ignores_skipped_but_not_failures(self) -> None:
        self.assertEqual(gate.verdict(gate.sonar_conditions(self.CLEAN, None, None)), 0)
        self.assertEqual(gate.verdict(gate.sonar_conditions(gate.IssueCounts(0, 0, 4), None, None)), 1)


class SonarClientTest(unittest.TestCase):
    BODY = {"paging": {"total": 9}, "facets": [
        {"property": "types", "values": [{"val": "BUG", "count": 2}, {"val": "CODE_SMELL", "count": 7}]},
        {"property": "severities", "values": [{"val": "BLOCKER", "count": 1}, {"val": "CRITICAL", "count": 2},
                                              {"val": "MAJOR", "count": 6}]},
    ]}

    def test_issue_counts_come_from_the_facets(self) -> None:
        counts = gate.fetch_issue_counts("https://s", "k", "t", lambda url, token: (200, self.BODY))
        self.assertEqual(counts, gate.IssueCounts(bugs=2, vulnerabilities=0, blocker_or_critical=3))

    def test_issue_search_failure_is_raised(self) -> None:
        with self.assertRaises(RuntimeError):
            gate.fetch_issue_counts("https://s", "k", "t", lambda url, token: (403, {"errors": []}))

    def test_optional_number_is_none_when_not_readable(self) -> None:
        self.assertIsNone(gate.fetch_optional_number("u", "t", lambda url, token: (403, {}), lambda b: 1.0))
        self.assertEqual(
            gate.fetch_optional_number("u", "t", lambda url, token: (200, {"v": 5}), lambda b: float(b["v"])), 5.0)

    def test_wait_for_analysis_polls_until_success(self) -> None:
        states = iter(["PENDING", "IN_PROGRESS", "SUCCESS"])
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "report-task.txt"
            report.write_text("projectKey=k\nceTaskUrl=https://s/api/ce/task?id=1\n")
            gate.wait_for_analysis(report, "t", lambda url, token: (200, {"task": {"status": next(states)}}),
                                   sleep=lambda seconds: None)
        self.assertEqual(list(states), [])

    def test_wait_for_analysis_reports_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "report-task.txt"
            report.write_text("ceTaskUrl=https://s/api/ce/task?id=1\n")
            with self.assertRaisesRegex(RuntimeError, "FAILED"):
                gate.wait_for_analysis(
                    report, "t",
                    lambda url, token: (200, {"task": {"status": "FAILED", "errorMessage": "boom"}}),
                    sleep=lambda seconds: None)


class DuplicationTest(unittest.TestCase):
    @staticmethod
    def fake_jscpd(directory: Path, percentage: float) -> Path:
        script = directory / "jscpd"
        script.write_text(
            "#!/usr/bin/env python3\nimport json, sys, pathlib\n"
            "out = pathlib.Path(sys.argv[sys.argv.index('--output') + 1])\n"
            f"(out / 'jscpd-report.json').write_text(json.dumps({{'statistics': {{'total': {{'percentage': {percentage}}}}}}}))\n")
        script.chmod(0o755)
        return script

    def test_threshold_is_inclusive(self) -> None:
        self.assertEqual(gate.duplication_condition(3.0).status, gate.PASS)
        self.assertEqual(gate.duplication_condition(3.1).status, gate.FAIL)

    def test_percentage_is_read_from_the_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(gate.measure_duplication(["src"], self.fake_jscpd(Path(tmp), 4.2)), 4.2)


class CliTest(unittest.TestCase):
    def run_cli(self, argv: list[str], env: dict[str, str] | None = None) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, env or {}, clear=True), redirect_stdout(out), redirect_stderr(err):
            code = gate.main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_sonar_without_configuration_is_skipped_visibly(self) -> None:
        code, out, _ = self.run_cli(["sonar", "--project", "p"])
        self.assertEqual(code, 0)
        self.assertIn("SKIPPED", out)

    def test_sonar_without_configuration_fails_when_required(self) -> None:
        code, _, _ = self.run_cli(["sonar", "--project", "p", "--require"])
        self.assertEqual(code, 2)

    def sonar_run(self, issues_body: dict) -> tuple[int, str]:
        def fake_get(url: str, token: str) -> tuple[int, dict]:
            return (200, issues_body) if "/api/issues/search" in url else (403, {})

        with mock.patch.object(gate, "sonar_get", fake_get):
            code, out, _ = self.run_cli(["sonar", "--project", "p"],
                                        {"SONAR_TOKEN": "t", "SONAR_HOST_URL": "https://s"})
        return code, out

    def test_sonar_gate_passes_on_a_clean_project_even_if_extras_are_unreadable(self) -> None:
        code, out = self.sonar_run({"paging": {"total": 0}, "facets": []})
        self.assertEqual(code, 0, out)
        self.assertIn("SKIPPED", out)

    def test_sonar_gate_fails_on_an_open_vulnerability(self) -> None:
        body = {"paging": {"total": 1}, "facets": [
            {"property": "types", "values": [{"val": "VULNERABILITY", "count": 1}]}]}
        code, out = self.sonar_run(body)
        self.assertEqual(code, 1, out)

    def test_duplication_command_needs_jscpd(self) -> None:
        code, _, err = self.run_cli(["duplication", "--jscpd", "/nope/jscpd"])
        self.assertEqual(code, 2)
        self.assertIn("jscpd not found", err)

    def test_coverage_reports_missing_input(self) -> None:
        code, _, err = self.run_cli(["coverage", "--base", "", "--backend", "/nope.xml"])
        self.assertEqual(code, 2)
        self.assertIn("not found", err)

    def test_coverage_end_to_end_pass_and_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            backend, frontend = Path(tmp) / "c.xml", Path(tmp) / "l.info"
            backend.write_text(COBERTURA)
            frontend.write_text(LCOV)
            added = {"backend/src/mtgvault/a.py": {4, 12}, "frontend/src/app/x.ts": {1, 3}}
            with mock.patch.object(gate, "added_lines_since", return_value=added):
                code, out, _ = self.run_cli(["coverage", "--backend", str(backend), "--frontend", str(frontend)])
                self.assertEqual(code, 0, out)
            added = {"backend/src/mtgvault/a.py": {5}, "frontend/src/app/x.ts": {2}}
            with mock.patch.object(gate, "added_lines_since", return_value=added):
                code, out, _ = self.run_cli(["coverage", "--backend", str(backend), "--frontend", str(frontend)])
                self.assertEqual(code, 1, out)
                self.assertIn("FAIL", out)


if __name__ == "__main__":
    unittest.main()
