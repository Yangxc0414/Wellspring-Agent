import tempfile
import unittest
from pathlib import Path

from research_agent.adapters.local_document_retriever import LocalDocumentRetriever
from research_agent.adapters.simple_parser import SimpleParser


class LocalDocumentRetrieverTest(unittest.TestCase):
    def test_text_file_is_searchable_and_has_page_section(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "note.md").write_text(
                "# Local note\n\nAlpha passivation improves humidity stability in this local note.",
                encoding="utf-8",
            )
            retriever = LocalDocumentRetriever(root)
            hits = retriever.search("passivation humidity", 5)
            self.assertEqual(len(hits), 1)
            self.assertFalse(hits[0].fixture)
            self.assertTrue(hits[0].full_text)
            document = retriever.full_text(hits[0].source_id)
            self.assertIsNotNone(document)
            self.assertEqual(document["sections"][0]["page"], 1)
            spans = SimpleParser().spans(hits[0], document)
            self.assertTrue(spans)
            self.assertTrue(all(span.page == 1 for span in spans))

    def test_pdf_pages_are_preserved_in_spans(self):
        try:
            import fitz
        except ImportError:
            self.skipTest("PyMuPDF not installed")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "two-pages.pdf"
            document = fitz.open()
            page = document.new_page()
            page.insert_text((72, 72), "Alpha evidence appears on page one.", fontsize=12)
            page = document.new_page()
            page.insert_text((72, 72), "Beta evidence appears on page two.", fontsize=12)
            document.save(str(path))
            document.close()
            retriever = LocalDocumentRetriever(root)
            hits = retriever.search("evidence", 5)
            self.assertEqual(len(hits), 1)
            full = retriever.full_text(hits[0].source_id)
            self.assertEqual(len(full["sections"]), 2)
            spans = SimpleParser().spans(hits[0], full)
            self.assertEqual({span.page for span in spans}, {1, 2})
            self.assertEqual(len(hits[0].source_id), 16)
            self.assertEqual(hits[0].license, "user-provided")

    def test_empty_directory_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(Exception):
                LocalDocumentRetriever(Path(tmp))


if __name__ == "__main__":
    unittest.main()
