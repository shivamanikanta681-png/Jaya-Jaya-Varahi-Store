#!/usr/bin/env python3
"""
Automated Test Suite for Jaya Jaya Varahi Shop & Gifts
Verifies Critical Security Fixes, Authoritative Pricing, Input Validation & Hashing
"""

import os
import sys
import unittest
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.environ["TEST_MODE"] = "1"

import server
from server import (
    calculate_authoritative_order,
    validate_admin_product,
    hash_otp,
    hash_password,
    verify_password,
    get_cors_origin
)
from rag_engine import get_rag_pipeline

class TestSecurityAndPricing(unittest.TestCase):

    def setUp(self):
        self.rag = get_rag_pipeline()
        self.valid_product_id = "p1"

    def test_01_reject_unknown_product_id(self):
        """Checkout must reject unknown/fake product IDs with HTTP 400 validation error."""
        order_payload = {
            "customer_name": "Attacker",
            "customer_phone": "9999999999",
            "delivery_address": "Test Address",
            "items": [
                {"productId": "fake_nonexistent_id", "qty": 1, "price": 1.0}
            ]
        }
        valid, result, err = calculate_authoritative_order(order_payload)
        self.assertFalse(valid, "Should reject unknown product ID")
        self.assertIn("Invalid product ID", err)

    def test_02_reject_invalid_quantities(self):
        """Checkout must reject negative, zero, non-integer, and out-of-range quantities."""
        test_cases = [
            0,
            -1,
            "abc",
            101,  # exceeds max 100
            None
        ]
        for invalid_qty in test_cases:
            order_payload = {
                "customer_name": "Test User",
                "customer_phone": "9876543210",
                "delivery_address": "Boduppal, Hyderabad",
                "items": [
                    {"productId": self.valid_product_id, "qty": invalid_qty}
                ]
            }
            valid, result, err = calculate_authoritative_order(order_payload)
            self.assertFalse(valid, f"Should reject invalid quantity: {invalid_qty}")
            self.assertIn("quantity", err.lower())

    def test_03_authoritative_price_computation(self):
        """Server must use database/authoritative price, ignoring client price tampering."""
        order_payload = {
            "customer_name": "Honest Customer",
            "customer_phone": "9876543210",
            "delivery_address": "Boduppal, Hyderabad",
            "items": [
                {"productId": self.valid_product_id, "qty": 2, "price": 1.0}  # Attacker submits 1.0
            ]
        }
        valid, order, err = calculate_authoritative_order(order_payload)
        self.assertTrue(valid, f"Valid order calculation failed: {err}")
        # Product p1 original price is 450.0. 2 * 450 = 900.0 subtotal
        self.assertEqual(order["subtotal"], 900.0, "Server must enforce authoritative catalog price")
        self.assertGreater(order["total_payable"], 0.0)

    def test_04_password_hashing_and_verification(self):
        """PBKDF2 password hashing and verification must work with cryptographic salts."""
        raw_password = "SuperSecretPassword123!"
        pwd_hash = hash_password(raw_password)
        self.assertIn("$", pwd_hash, "Hash should be in salt$digest format")

        self.assertTrue(verify_password(pwd_hash, raw_password))
        self.assertFalse(verify_password(pwd_hash, "WrongPassword"))

    def test_05_otp_hashing(self):
        """OTP must be hashed with email binding and verify correctly."""
        email = "customer@example.com"
        otp = "654321"
        h = hash_otp(email, otp)
        self.assertEqual(len(h), 64, "SHA-256 digest should be 64 hex characters")
        self.assertEqual(h, hash_otp("CUSTOMER@EXAMPLE.COM ", " 654321 "))
        self.assertNotEqual(h, hash_otp(email, "000000"))

    def test_06_admin_product_payload_validation(self):
        """Admin product payload validation must reject invalid fields and negative prices."""
        # Negative price
        valid, _, err = validate_admin_product({"id": "p10", "name": "Valid Name", "category": "toys", "price": -50})
        self.assertFalse(valid)
        self.assertIn("non-negative", err)

        # Empty name
        valid, _, err = validate_admin_product({"id": "p10", "name": "", "category": "toys", "price": 100})
        self.assertFalse(valid)
        self.assertIn("name is required", err)

        # Valid product
        valid, clean, err = validate_admin_product({"id": "p10", "name": "Handmade Clay Lamp", "category": "return_gifts", "price": 199.5})
        self.assertTrue(valid)
        self.assertEqual(clean["price"], 199.5)

    def test_07_cors_origin_filtering(self):
        """CORS must not allow arbitrary origins when configured."""
        allowed = get_cors_origin("http://localhost:8000")
        self.assertIn("localhost", allowed)

    def test_08_products_retriever_alias(self):
        """RAGPipeline products_retriever alias must resolve cleanly."""
        self.assertTrue(hasattr(self.rag, "product_retriever"))
        self.assertTrue(hasattr(self.rag, "products_retriever"))
        self.assertIs(self.rag.product_retriever, self.rag.products_retriever)


if __name__ == "__main__":
    unittest.main(verbosity=2)
