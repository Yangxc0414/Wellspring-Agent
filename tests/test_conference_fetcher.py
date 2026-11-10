import json
import tempfile
import unittest
from pathlib import Path

from research_agent.adapters.arxiv_fetcher import ArxivFetcher
from research_agent.adapters.conference_fetcher import (
    ConferenceFetchError,
    fetch_top_conference_corpus,
)

ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2501.00001v1</id>
    <published>2025-01-01T00:00:00Z</published>
    <title>Self-Improving Language Agents with Verified Trajectories</title>
    <summary>We study agents, failure trajectories, tool use and memory for self-improvement.</summary>
    <author><name>Alice Example</name></author>
    <arxiv:comment>Accepted to ICLR 2025</arxiv:comment>
    <link title="pdf" href="https://arxiv.org/pdf/2501.00001v1"/>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2501.00002v1</id>
    <published>2025-01-02T00:00:00Z</published>
    <title>Workshop Agents for Tool Use</title>
    <summary>An agent paper with tool use and memory.</summary>
    <author><name>Bob Example</name></author>
    <arxiv:comment>Accepted at ICLR 2025 Workshop on Agents</arxiv:comment>
    <link title="pdf" href="https://arxiv.org/pdf/2501.00002v1"/>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2501.00003v1</id>
    <published>2025-01-03T00:00:00Z</published>
    <title>Robust Noise Attenuation for Transformer Outputs</title>
    <summary>We study agents and memory in a noisy setting.</summary>
    <author><name>Carol Example</name></author>
    <arxiv:comment>Published at ICML 2025</arxiv:comment>
    <link title="pdf" href="https://arxiv.org/pdf/2501.00003v1"/>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2501.00004v1</id>
    <published>2025-01-04T00:00:00Z</published>
    <title>Multi-Agent Language Model Planning for Research Automation</title>
    <summary>We study multi-agent language model planning, scientific discovery and tool use.</summary>
    <author><name>Dave Example</name></author>
    <arxiv:comment>Accepted by ICML 2025</arxiv:comment>
    <link title="pdf" href="https://arxiv.org/pdf/2501.00004v1"/>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2501.00005v1</id>
    <published>2025-01-05T00:00:00Z</published>
    <title>Agent Memory for Long-Horizon Tasks</title>
    <summary>We study agent memory and self-improvement.</summary>
    <author><name>Eve Example</name></author>
    <arxiv:comment>NeurIPS 2024 manuscript style (preprint)</arxiv:comment>
    <link title="pdf" href="https://arxiv.org/pdf/2501.00005v1"/>
  </entry>
</feed>
"""


class FakeTransport:
    def __call__(self, request):
        if "export.arxiv.org/api/query" in request.full_url:
            return ATOM.encode("utf-8")
        if "/pdf/" in request.full_url:
            return b"%PDF-1.5\nfake-pdf-body\n"
        raise RuntimeError("unexpected URL: " + request.full_url)


class ConferenceFetcherTest(unittest.TestCase):
    def test_filters_workshops_non_agent_titles_and_preprints(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "inputs"
            manifest = fetch_top_conference_corpus(
                target,
                venues=["ICLR", "ICML"],
                years=[2025],
                topic="LLM agents research automation",
                max_papers=4,
                max_per_venue=2,
                allow_network=True,
                fetcher=ArxivFetcher(min_interval=0, transport=FakeTransport()),
            )
            self.assertEqual(manifest["downloaded_count"], 2)
            ids = {item["arxiv_id"] for item in manifest["downloaded"]}
            self.assertEqual(ids, {"2501.00001v1", "2501.00004v1"})
            venues = {item["venue"] for item in manifest["downloaded"]}
            self.assertEqual(venues, {"ICLR 2025", "ICML 2025"})
            meta = json.loads(
                (target / "iclr-2025" / "arxiv-2501.00001v1.meta.json").read_text(encoding="utf-8")
            )
            self.assertEqual(meta["venue"], "ICLR 2025")
            self.assertEqual(meta["corpus"], "topconf")
            self.assertIn("Accepted to ICLR 2025", meta["venue_claim"])
            self.assertTrue((target / "conference-corpus.json").is_file())
            self.assertTrue((target / "conference-corpus.md").is_file())
            skipped = json.dumps(manifest["skipped"], ensure_ascii=False)
            self.assertIn("workshop", skipped.lower())
            self.assertIn("title has no agent", skipped)
            self.assertIn("acceptance", skipped)

    def test_network_requires_explicit_permission(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ConferenceFetchError):
                fetch_top_conference_corpus(
                    Path(tmp),
                    venues=["ICLR"],
                    years=[2025],
                    topic="agents",
                    allow_network=False,
                )

    def test_unknown_venue_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ConferenceFetchError):
                fetch_top_conference_corpus(
                    Path(tmp),
                    venues=["NotAConference"],
                    years=[2025],
                    topic="agents",
                    allow_network=True,
                )


if __name__ == "__main__":
    unittest.main()
