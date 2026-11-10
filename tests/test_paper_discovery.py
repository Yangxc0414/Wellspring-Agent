import json
import unittest

from research_agent.adapters.paper_discovery import (
    DEFAULT_SOURCES,
    HF_DAILY_URL,
    SORT_BY_SOURCE,
    _hf_rows,
    canonical_arxiv_id,
    discover_papers,
)

DAILY = [
    {"paper": {"id": "2401.00001", "title": "Shared candidate", "upvotes": 12},
     "publishedAt": "2026-01-02T00:00:00.000Z"},
    {"paper": {"id": "2401.00002", "title": "Daily only", "upvotes": 3},
     "submittedOnDailyAt": "2026-01-02"},
]
TRENDING = [
    {"paper": {"id": "2401.00003", "title": "Trending only", "upvotes": 99},
     "publishedAt": "2026-01-01"},
    {"paper": {"id": "2401.00001v2", "title": "Shared candidate", "upvotes": 20}},
]


class _FakeArxiv:
    def __init__(self, rows=None, error=None):
        self.rows = rows
        self.error = error
        self.calls = []

    def search(self, query, max_results=4):
        self.calls.append((query, max_results))
        if self.error:
            raise self.error
        return self.rows if self.rows is not None else [
            {"arxiv_id": "2401.00001v1", "title": "Shared candidate",
             "url": "https://arxiv.org/abs/2401.00001",
             "pdf_url": "https://arxiv.org/pdf/2401.00001",
             "published": "2026-01-01T00:00:00Z"},
        ]


def _transport(request):
    url = request.full_url
    if not url.startswith(HF_DAILY_URL):
        raise AssertionError("unexpected host: " + url)
    payload = TRENDING if "sort=trending" in url else DAILY
    return json.dumps(payload).encode("utf-8")


class CanonTest(unittest.TestCase):
    def test_arxiv_id_forms_normalise_to_one_key(self):
        values = [
            "arXiv:2311.12983v2", "https://arxiv.org/abs/2311.12983v2",
            "2311.12983v3", "https://arxiv.org/pdf/2311.12983v1.pdf",
        ]
        self.assertEqual({canonical_arxiv_id(v) for v in values}, {"2311.12983"})

    def test_old_style_id_is_preserved(self):
        self.assertEqual(canonical_arxiv_id("hep-th/9901001v3"), "hep-th/9901001")


class HfParseTest(unittest.TestCase):
    def test_documented_list_shape_is_parsed(self):
        rows = _hf_rows(json.dumps(DAILY).encode("utf-8"))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["paper_id"], "2401.00001")
        self.assertEqual(rows[0]["title"], "Shared candidate")

    def test_bad_json_and_wrong_shape_raise_instead_of_silent_empty(self):
        with self.assertRaises(ValueError):
            _hf_rows(b"not json")
        with self.assertRaises(ValueError):
            _hf_rows(b'{"papers": []}')

    def test_the_two_hf_signals_share_one_endpoint(self):
        self.assertEqual(len(SORT_BY_SOURCE), 2)
        self.assertEqual(SORT_BY_SOURCE["hf_daily"], "publishedAt")
        self.assertEqual(SORT_BY_SOURCE["hf_trending"], "trending")
        self.assertEqual(len(DEFAULT_SOURCES), 3)


class NetworkGateTest(unittest.TestCase):
    def test_network_off_returns_blocked_not_an_empty_success(self):
        calls = []
        report = discover_papers(
            "agent reliability", allow_network=False,
            transport=lambda request: calls.append(request) or b"[]",
        )
        self.assertEqual(report.status, "blocked")
        self.assertFalse(report.network_used)
        self.assertEqual(report.candidates, [])
        self.assertTrue(report.errors)
        self.assertEqual(calls, [], "no request may be made without opt-in")
        self.assertIn("network disabled", report.to_dict()["errors"][0])


class DiscoveryTest(unittest.TestCase):
    def test_three_sources_are_collected_and_deduplicated(self):
        report = discover_papers(
            "agent reliability", allow_network=True,
            transport=_transport, arxiv_client=_FakeArxiv(),
        )
        self.assertEqual(report.status, "ok")
        self.assertTrue(report.network_used)
        self.assertEqual(report.by_source, {"arxiv": 1, "hf_daily": 2, "hf_trending": 2})
        self.assertGreaterEqual(report.duplicates_removed, 2)
        ids = [row["paper_id"] for row in report.candidates]
        self.assertEqual(len(ids), len(set(ids)))
        shared = next(row for row in report.candidates if row["paper_id"] == "2401.00001")
        self.assertIn("arxiv", shared["sources"])
        self.assertIn("hf_daily", shared["sources"])

    def test_every_row_is_a_clue_and_never_evidence(self):
        report = discover_papers(
            "agent", allow_network=True, transport=_transport,
            arxiv_client=_FakeArxiv(),
        )
        for row in report.candidates:
            self.assertTrue(row["clue_only"])
            self.assertFalse(row["span_eligible"])
            self.assertNotIn("abstract", row)
            self.assertNotIn("spans", row)
            self.assertNotIn("full_text", row)
        payload = report.to_dict()
        self.assertIn("clue-only", payload["boundary"])
        self.assertTrue(any("--source local" in cmd for cmd in report.next_commands))
        json.dumps(payload)

    def test_one_source_failing_does_not_erase_the_others(self):
        broken = _FakeArxiv(error=RuntimeError("arxiv unavailable"))
        calls = []

        def selective(request):
            calls.append(request.full_url)
            if "sort=trending" in request.full_url:
                raise OSError("trending endpoint down")
            return json.dumps(DAILY).encode("utf-8")

        report = discover_papers(
            "agent", allow_network=True, transport=selective, arxiv_client=broken,
        )
        self.assertEqual(report.by_source["hf_daily"], 2)
        self.assertEqual(report.by_source["hf_trending"], 0)
        self.assertTrue(report.candidates)
        self.assertGreaterEqual(len(report.errors), 2)
        self.assertEqual(report.status, "ok")

    def test_unknown_source_is_reported_not_guessed(self):
        report = discover_papers(
            "agent", sources=["bogus"], allow_network=True,
            transport=_transport, arxiv_client=_FakeArxiv(),
        )
        self.assertEqual(report.status, "empty")
        self.assertTrue(any("unknown source" in error for error in report.errors))

    def test_hf_only_mode_skips_arxiv_and_still_gives_the_local_parse_command(self):
        report = discover_papers(
            "", sources=["hf_daily", "hf_trending"], allow_network=True,
            transport=_transport, arxiv_client=_FakeArxiv(),
        )
        self.assertTrue(report.candidates)
        self.assertNotIn("arxiv", report.by_source)
        self.assertEqual(len(report.errors), 0)
        self.assertEqual(len(report.next_commands), 1)
        self.assertIn("--source local", report.next_commands[0])


if __name__ == "__main__":
    unittest.main()
