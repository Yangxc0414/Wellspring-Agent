import tempfile
import unittest
from pathlib import Path

from research_agent.adapters.arxiv_fetcher import ArxivFetchError, ArxivFetcher

ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2401.00001v1</id>
    <published>2024-01-01T00:00:00Z</published>
    <title>Test Agent Paper</title>
    <summary>This paper studies self-improving agents and failure trajectories.</summary>
    <author><name>Alice Example</name></author>
    <link title="pdf" href="https://arxiv.org/pdf/2401.00001v1"/>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2401.00002v1</id>
    <published>2024-02-02T00:00:00Z</published>
    <title>Second Agent Paper</title>
    <summary>Context memory for agents.</summary>
    <author><name>Bob Example</name></author>
    <link title="pdf" href="https://arxiv.org/pdf/2401.00002v1"/>
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


class ArxivFetcherTest(unittest.TestCase):
    def test_search_and_download_writes_pdf_meta_and_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "inputs"
            fetcher = ArxivFetcher(min_interval=0, transport=FakeTransport())
            manifest = fetcher.fetch(
                query="self-improving agent",
                target_dir=target,
                max_results=2,
                allow_network=True,
            )
            self.assertEqual(manifest["found"], 2)
            self.assertEqual(len(manifest["downloaded"]), 2)
            self.assertTrue((target / "arxiv-sources.json").is_file())
            self.assertTrue((target / "arxiv-sources.md").is_file())
            pdfs = sorted(target.glob("*.pdf"))
            self.assertEqual(len(pdfs), 2)
            meta = sorted(target.glob("*.meta.json"))
            self.assertEqual(len(meta), 2)
            self.assertEqual(meta[0].read_text(encoding="utf-8").count("Test Agent Paper"), 1)
            self.assertIn("This paper studies", (target / "arxiv-sources.md").read_text(encoding="utf-8"))
            self.assertEqual(len(manifest["downloaded"][0]["sha256"]), 64)

    def test_network_requires_explicit_permission(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ArxivFetchError):
                ArxivFetcher(min_interval=0, transport=FakeTransport()).fetch(
                    query="agent",
                    target_dir=Path(tmp),
                    allow_network=False,
                )


if __name__ == "__main__":
    unittest.main()
