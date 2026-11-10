import tempfile
import unittest
from pathlib import Path

from research_agent.signers import SignerError, SignerStore


class SignerStoreTest(unittest.TestCase):
    def test_create_sign_verify_and_mask_secret(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "signers.json"
            store = SignerStore(path)
            signer = store.create("PI")
            snapshot = store.snapshot()
            self.assertEqual(snapshot["count"], 1)
            self.assertNotIn("secret_hex", str(snapshot))
            payload = {"report_id": "CLR-1", "submission": False}
            signed = store.sign(signer["signer_id"], payload)
            self.assertEqual(signed["signature_scheme"], "hmac-sha256-local")
            self.assertTrue(store.verify(
                signed["signer_id"],
                signed["signer_key_id"],
                payload,
                signed["signature_hmac"],
            ))
            self.assertFalse(store.verify(
                signed["signer_id"],
                signed["signer_key_id"],
                {"report_id": "CLR-2", "submission": False},
                signed["signature_hmac"],
            ))

    def test_unknown_signer_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SignerStore(Path(tmp) / "signers.json")
            with self.assertRaises(SignerError):
                store.sign("SIGNER-missing", {"a": 1})


if __name__ == "__main__":
    unittest.main()
