import json
import tempfile
import unittest
from pathlib import Path

from research_agent.bibliography import BibliographyAgent, BibliographyError


class BibliographyTest(unittest.TestCase):
    def test_fixture_metadata_verifies(self):
        root = Path(__file__).resolve().parents[1]
        source = root / "modules" / "literature" / "fixtures" / "bibliography.json"
        with tempfile.TemporaryDirectory() as tmp:
            result = BibliographyAgent().verify(source, Path(tmp))
            card = result["bibliography"]
            self.assertEqual(card["status"], "verified_datacite_snapshot")
            self.assertEqual(card["entry_count"], 4)
            self.assertEqual(len(card["card_sha256"]), 64)
            self.assertTrue(all(entry["doi"].startswith("10.48550/") for entry in card["entries"]))
            data = json.loads(source.read_text(encoding="utf-8"))
            data["entries"][1]["doi"] = data["entries"][0]["doi"]
            bad = Path(tmp) / "bad.json"
            bad.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaises(BibliographyError):
                BibliographyAgent().verify(bad, Path(tmp) / "bad")


if __name__ == "__main__":
    unittest.main()
