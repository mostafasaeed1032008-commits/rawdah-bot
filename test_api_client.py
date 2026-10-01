# -*- coding: utf-8 -*-
"""
test_api_client.py
==================
Unit tests for NusukApiClient, nusuk_crypto, and hybrid engine execution.
"""

import unittest
import nusuk_crypto
from nusuk_api_client import NusukApiClient, NusukServiceId
from nusuk_engine import NusukEngine, BotState


class TestNusukDirectApi(unittest.TestCase):
    def test_crypto_pack_unpack(self):
        """Verifies that arbitrary payload packed with append_key matches CryptoJS decrypt logic."""
        test_payload = {
            "UserID": 998877,
            "PhoneNo": "966500000000",
            "Token": "sample_jwt_token_123"
        }
        key = nusuk_crypto.generate_random_string(16)
        import json
        ct = nusuk_crypto.encrypt_with_key(key, json.dumps(test_payload))
        packed = nusuk_crypto.append_key_for_encrypted_data(key, ct)
        
        recovered = nusuk_crypto.get_object_from_string(packed)
        self.assertIsNotNone(recovered)
        self.assertEqual(recovered["UserID"], test_payload["UserID"])
        self.assertEqual(recovered["Token"], test_payload["Token"])

    def test_bearer_token_signing(self):
        """Verifies dynamic Bearer token generation with targetUrl and timestamp."""
        token = "test_token_abc"
        target = "timeslots/available"
        signed = nusuk_crypto.generate_bearer_token(token, target)
        
        unpacked = nusuk_crypto.get_object_from_string(signed)
        self.assertIsNotNone(unpacked)
        self.assertEqual(unpacked.get("token"), token)
        self.assertEqual(unpacked.get("targetUrl"), target)
        self.assertIn("timestamp", unpacked)

    def test_nationalities_lookup_and_exact_match(self):
        """Tests live retrieval of nationalities and exact match for Egypt (ID 20)."""
        client = NusukApiClient()
        nats = client.get_nationalities()
        self.assertGreater(len(nats), 50)
        
        egypt_id = client.find_nationality_id("مصر")
        self.assertEqual(egypt_id, 20)

        sa_id = client.find_nationality_id("Saudi Arabia")
        self.assertIsNotNone(sa_id)

    def test_engine_api_mode(self):
        """Tests that NusukEngine initializes cleanly in API mode without requiring ADB emulator."""
        engine = NusukEngine()
        self.assertEqual(engine.engine_mode, "api")
        self.assertEqual(engine.state, BotState.READY)
        status = engine.get_status_dict()
        self.assertEqual(status["engine_mode"], "api")
        self.assertIn("passengers", status)


if __name__ == "__main__":
    unittest.main()
