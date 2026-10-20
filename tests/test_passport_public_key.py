"""Ed25519 public-key signatures on credit passports, verifiable offline by a lender."""
import copy
import unittest

from scripts import verify_passport as offline
from tideway import ed25519, treasury
from tideway.service import Tideway
from tideway.treasury import Treasury

OWNER = {"id": "nadia", "name": "Nadia Rahman", "role": "owner"}


class Ed25519Vectors(unittest.TestCase):
    def test_rfc8032_test_vector_1(self):
        secret = bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60")
        public = ed25519.public_key(secret)
        self.assertEqual(public.hex(), "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a")
        signature = ed25519.sign(secret, b"")
        self.assertEqual(signature.hex(), "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bac"
                                          "c61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b")
        self.assertTrue(ed25519.verify(public, b"", signature))
        self.assertFalse(ed25519.verify(public, b"\x00", signature))
        self.assertFalse(ed25519.verify(public, b"", signature[:-1] + bytes([signature[-1] ^ 1])))
        self.assertFalse(ed25519.verify(public[:31], b"", signature))


class PassportPublicKey(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tideway = Tideway(":memory:")
        cls.treasury = Treasury(cls.tideway)
        cls.document = cls.treasury.issue_passport("shapla-services", OWNER, "operator:nadia")["passport"]
        cls.public_key = treasury.passport_public_key(cls.tideway.store.key)["public_key"]

    @classmethod
    def tearDownClass(cls):
        cls.tideway.store.close()

    def test_issued_passport_verifies_offline_with_public_key_only(self):
        ok, message = offline.check(self.document, self.public_key)
        self.assertTrue(ok, message)
        self.assertEqual(self.document["public_signature"]["public_key"], self.public_key)

    def test_server_reports_both_signatures_valid(self):
        result = self.treasury.verify_passport("shapla-services", self.document)
        self.assertTrue(result["valid"])
        self.assertTrue(result["public_signature_valid"])

    def test_any_edit_fails_offline_and_on_server(self):
        tampered = copy.deepcopy(self.document)
        tampered["health"]["score"] = 99
        self.assertFalse(offline.check(tampered, self.public_key)[0])
        self.assertEqual(self.treasury.verify_passport("shapla-services", tampered)["reason"], "signature_mismatch")

    def test_attacker_cannot_resign_with_their_own_key(self):
        forged = copy.deepcopy(self.document)
        forged["health"]["score"] = 99
        attacker = bytes(range(32))
        forged["public_signature"] = {**forged["public_signature"], "public_key": ed25519.public_key(attacker).hex(),
                                      "signature": ed25519.sign(attacker, treasury.public_message(forged)).hex()}
        self.assertTrue(offline.check(forged)[0])                       # self-consistent, but...
        self.assertFalse(offline.check(forged, self.public_key)[0])     # ...pinning the issuer key rejects it
        self.assertEqual(self.treasury.verify_passport("shapla-services", forged)["reason"], "signature_mismatch")

    def test_signing_key_is_purpose_bound(self):
        self.assertNotEqual(treasury.passport_signing_secret(self.tideway.store.key), treasury.passport_key(self.tideway.store.key))
        self.assertNotEqual(treasury.passport_signing_secret(self.tideway.store.key), self.tideway.store.key)


if __name__ == "__main__":
    unittest.main()
