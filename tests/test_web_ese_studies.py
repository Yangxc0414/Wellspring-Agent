import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "apps" / "web" / "public" / "ese-studies.json"
STUDY = ROOT / "runtime_data" / "ese-ms-20261118-03"


class EseStudiesSnapshotTest(unittest.TestCase):
    def setUp(self):
        self.payload = json.loads(SNAPSHOT.read_text(encoding="utf-8"))

    def test_schema_and_count(self):
        self.assertEqual("runtime-ese-studies-0.1", self.payload["schema"])
        self.assertEqual(len(self.payload["studies"]), self.payload["count"])

    def test_repository_mining_study_comes_first(self):
        first = self.payload["studies"][0]
        self.assertEqual("ESE-MS-20261118-03", first["study_id"])
        self.assertEqual(3, len(first["repos"]))
        self.assertGreaterEqual(len(first["strata"]), 8)
        self.assertEqual(5, len(first["chain"]))

    def test_numbers_match_result_json(self):
        result = json.loads((STUDY / "result.json").read_text(encoding="utf-8"))
        first = self.payload["studies"][0]
        self.assertAlmostEqual(result["pooled"]["rate"], first["pooled"]["rate"], places=6)
        self.assertAlmostEqual(
            result["pooled"]["difference"], first["pooled"]["difference"], places=6
        )
        self.assertEqual(
            len(result["stratified"]["strata"]), len(first["strata"])
        )

    def test_local_paths_are_not_exported(self):
        text = json.dumps(self.payload, ensure_ascii=False)
        self.assertNotIn("msr-corpus", text)
        self.assertNotIn("runtime_data\\\\msr", text)

    def test_chain_never_claims_a_missing_signature(self):
        first = self.payload["studies"][0]
        by_name = {step["name"]: step for step in first["chain"]}
        signature = by_name["Signature（人签）"]
        exists = (STUDY / "signature" / "signature.json").is_file()
        self.assertEqual(exists, bool(signature["ok"]))
        self.assertEqual(exists, first["state"] == "SIGNED")

    def test_study_without_result_is_not_listed(self):
        ids = {study["study_id"] for study in self.payload["studies"]}
        self.assertNotIn("ESE-PIPE-BENCH-20261118", ids)


if __name__ == "__main__":
    unittest.main()
