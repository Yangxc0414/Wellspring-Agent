"""A verdict without a code fingerprint is a status, and a status is what got us here.

Each case below mirrors something that actually happened this session: an interrupted background
run whose log has no summary line, a chained command whose exit code came from the last `grep`
rather than from the suite, and a green verdict quietly outlived by the next edit.
"""

import unittest

from research_agent.verdicts import (
    parse_unittest_output,
    verdict_record,
    verdict_status,
)

GREEN = (
    "...................................................................\n"
    "----------------------------------------------------------------------\n"
    "Ran 1207 tests in 352.457s\n"
    "\n"
    "OK\n"
)
RED = (
    "Ran 1207 tests in 352.457s\n"
    "\n"
    "FAILED (failures=1)\n"
)
INTERRUPTED = "............\nResourceWarning: Enable tracemalloc to get the object allocation traceback\n"


class ParseTest(unittest.TestCase):
    def test_a_green_run_is_read_from_the_summary_not_the_exit_code(self):
        parsed = parse_unittest_output(GREEN)
        self.assertTrue(parsed["found"])
        self.assertEqual(parsed["tests_run"], 1207)
        self.assertEqual(parsed["seconds"], 352.457)
        self.assertTrue(parsed["ok"])

    def test_a_failed_suite_never_reads_as_success(self):
        parsed = parse_unittest_output(RED)
        self.assertTrue(parsed["found"])
        self.assertFalse(parsed["ok"])
        self.assertTrue(parsed["failures_reported"])

    def test_an_interrupted_run_is_missing_rather_than_passed(self):
        # the real shape: dots and warnings, no Ran line, and a notification saying exit code 0
        parsed = parse_unittest_output(INTERRUPTED)
        self.assertFalse(parsed["found"])
        self.assertFalse(parsed["ok"])
        self.assertIn("did not finish", parsed["why"])

    def test_empty_output_is_not_a_verdict(self):
        self.assertFalse(parse_unittest_output("")["found"])

    def test_an_unreadable_summary_is_not_defaulted_into_a_green_zero(self):
        # the regression: indexing the split by hand read "in" as the duration, float() raised,
        # the except swallowed it, and the record said 1207 tests / 0.0s / OK
        parsed = parse_unittest_output("Ran 1207 tests in about a while\n\nOK\n")
        self.assertFalse(parsed["found"])
        self.assertEqual(parsed["tests_run"], 0)
        self.assertFalse(parsed["ok"])
        self.assertIn("unreadable", parsed["why"])

    def test_a_singular_summary_still_parses(self):
        parsed = parse_unittest_output("Ran 1 test in 0.123s\n\nOK\n")
        self.assertTrue(parsed["found"])
        self.assertEqual((parsed["tests_run"], parsed["seconds"]), (1, 0.123))


class StatusTest(unittest.TestCase):
    def setUp(self):
        self.record = verdict_record(
            fingerprint="abc111", tests_run=1207, seconds=352.4, ok=True,
            finished_at="2026-11-05T05:00:00+00:00", source="scripts/record_test_verdict.py",
            summary="Ran 1207 tests in 352.457s / OK",
        )

    def test_a_record_covers_only_the_fingerprint_it_names(self):
        self.assertTrue(verdict_status(self.record, "abc111")["covers_current_source"])
        self.assertEqual(verdict_status(self.record, "abc111")["state"], "current")
        stale = verdict_status(self.record, "def999")
        self.assertEqual(stale["state"], "stale")
        self.assertFalse(stale["covers_current_source"])

    def test_a_red_record_against_current_code_is_reported_as_failed_not_stale(self):
        red = dict(self.record, ok=False)
        self.assertEqual(verdict_status(red, "abc111")["state"], "failed")
        self.assertFalse(verdict_status(red, "abc111")["covers_current_source"])

    def test_an_interrupted_record_covers_nothing_even_for_the_same_fingerprint(self):
        cut = dict(self.record, truncated=True)
        status = verdict_status(cut, "abc111")
        self.assertEqual(status["state"], "truncated")
        self.assertFalse(status["covers_current_source"])

    def test_no_record_says_so_instead_of_defaulting_to_green(self):
        status = verdict_status(None, "abc111")
        self.assertEqual(status["state"], "absent")
        self.assertIn("no full-suite verdict", status["detail"])

    def test_the_record_keeps_the_runners_own_line(self):
        self.assertEqual(self.record["summary_line"], "Ran 1207 tests in 352.457s / OK")
        self.assertIn("1207 test(s)", self.record["base"])


if __name__ == "__main__":
    unittest.main()
