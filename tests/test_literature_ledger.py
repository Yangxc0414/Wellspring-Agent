import unittest

from research_agent.literature_ledger import build_source_ledger


def literature_fixture():
    return {
        "run_id": "LIT-TEST",
        "fixture_mode": False,
        "coverage": {"score": 0.5, "gaps": [{"code": "thin_full_text"}]},
        "brief": {
            "saturation": "partial",
            "facets": [{"facet": "core"}],
        },
        "hits": [
            {
                "source_id": "SRC-1",
                "title": "Passivation study",
                "year": 2024,
                "venue": "Journal of Test",
                "doi": "10.1000/a",
                "full_text": True,
                "url": "https://doi.org/10.1000/a",
                "fixture": False,
            },
            {
                "source_id": "SRC-2",
                "title": "Passivation study duplicate",
                "year": 2024,
                "venue": "Journal of Test",
                "doi": "https://doi.org/10.1000/a",
                "full_text": True,
                "url": "https://doi.org/10.1000/a",
                "fixture": False,
            },
            {
                "source_id": "SRC-3",
                "title": "Abstract only work",
                "year": 2025,
                "venue": "arXiv",
                "doi": "10.48550/arxiv.2501.00001",
                "full_text": False,
                "url": "https://arxiv.org/abs/2501.00001",
                "fixture": False,
            },
            {
                "source_id": "SRC-4",
                "title": "Old incomplete record",
                "year": 2010,
                "venue": "",
                "doi": "",
                "full_text": True,
                "url": "",
                "fixture": False,
            },
        ],
        "spans": [
            {"span_id": "SPAN-1", "source_id": "SRC-1", "text": "T80 improved."},
            {"span_id": "SPAN-2", "source_id": "SRC-2", "text": "T80 improved again."},
            {"span_id": "SPAN-3", "source_id": "SRC-4", "text": "Legacy result."},
        ],
    }


class LiteratureLedgerTest(unittest.TestCase):
    def test_screening_counts_and_recency(self):
        ledger = build_source_ledger(
            literature_fixture(),
            "钝化层 湿热稳定性",
            ["local"],
            current_year=2026,
        )
        self.assertEqual(ledger["status"], "ready")
        self.assertEqual(ledger["counts"]["found"], 4)
        self.assertEqual(ledger["counts"]["included_full_text"], 2)
        self.assertEqual(ledger["counts"]["abstract_only"], 1)
        self.assertEqual(ledger["counts"]["duplicates"], 1)
        self.assertEqual(ledger["counts"]["metadata_incomplete"], 1)
        self.assertEqual(ledger["counts"]["with_locatable_span"], 3)
        self.assertEqual(ledger["counts"]["preprints"], 1)
        self.assertEqual(ledger["metadata"]["recent_5y"], 3)
        self.assertAlmostEqual(ledger["metadata"]["doi_coverage"], 0.75)
        self.assertEqual(ledger["screening_flow"]["duplicates_removed"], 1)
        self.assertEqual(ledger["peer_reviewed"]["verified"], 0)
        self.assertEqual(ledger["peer_reviewed"]["unknown"], 4)
        self.assertTrue(any("duplicate" in item for item in ledger["warnings"]))
        self.assertTrue(any("abstract-only" in item for item in ledger["warnings"]))
        self.assertTrue(any("incomplete metadata" in item for item in ledger["warnings"]))
        first = ledger["sources"][0]
        self.assertEqual(len(first["metadata_sha256"]), 64)
        self.assertEqual(first["peer_reviewed"], "unknown")
        duplicate = ledger["sources"][1]
        self.assertEqual(duplicate["screening"], "duplicate")
        self.assertEqual(duplicate["duplicate_of"], "SRC-1")

    def test_no_full_text_is_insufficient(self):
        payload = literature_fixture()
        for hit in payload["hits"]:
            hit["full_text"] = False
        payload["spans"] = []
        ledger = build_source_ledger(payload, "topic", ["openalex"], current_year=2026)
        self.assertEqual(ledger["status"], "insufficient")
        self.assertTrue(any("full-text" in item for item in ledger["warnings"]))
        self.assertEqual(ledger["boundary"].split(";")[0], "source screening and metadata audit only")


if __name__ == "__main__":
    unittest.main()
