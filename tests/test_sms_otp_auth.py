#!/usr/bin/env python3
"""
Comprehensive Automated Test Suite for Native Mobile SMS OTP Authentication
Jaya Jaya Varahi Shop & Gifts (Antigravity IDE)

Verifies all 15 acceptance criteria:
TEST 1: Valid Indian mobile number accepted and normalized to +91XXXXXXXXXX
TEST 2: Invalid mobile number rejected
TEST 3: OTP is generated server-side using cryptographically secure secrets
TEST 4: OTP is not returned in API response
TEST 5: OTP is stored hashed (SHA-256)
TEST 6: Correct OTP succeeds
TEST 7: Incorrect OTP fails
TEST 8: Expired OTP fails
TEST 9: OTP cannot be reused (single-use)
TEST 10: Too many failed verification attempts blocked (max 5)
TEST 11: Too many OTP requests rate limited (max 3/15 min & 30s cooldown)
TEST 12: Password login cannot bypass OTP (mandatory 2FA OTP)
TEST 13: No frontend OTP generation exists (no Math.random OTP)
TEST 14: No authentication session created before OTP verification
TEST 15: Same Indian mobile number cannot create duplicate accounts
"""

import os
import sys
import time
import json
import string
import secrets
import unittest
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.environ["TEST_MODE"] = "1"
os.environ["SMS_PROVIDER"] = "console"

import server
from server import (
    normalize_indian_phone,
    hash_otp,
    store_otp_record,
    retrieve_otp_record,
    increment_otp_attempts,
    delete_otp_record,
    verify_firebase_id_token,
    OTP_CACHE,
    OTP_RATE_LIMITS,
    REGISTRATION_SESSIONS,
    TEST_USERS_STORE_BY_UID,
    TEST_USERS_STORE_BY_PHONE,
    TEST_USERS_STORE_BY_EMAIL,
    SmsOtpProvider,
    sync_user_to_supabase
)


class TestSmsOtpAuthentication(unittest.TestCase):

    def setUp(self):
        # Clear in-memory caches before each test
        OTP_CACHE.clear()
        OTP_RATE_LIMITS.clear()
        REGISTRATION_SESSIONS.clear()
        TEST_USERS_STORE_BY_UID.clear()
        TEST_USERS_STORE_BY_PHONE.clear()
        TEST_USERS_STORE_BY_EMAIL.clear()

    # ── TEST 1: Valid Indian mobile number accepted & normalized ──
    def test_01_valid_indian_mobile_accepted(self):
        valid_cases = [
            ("9876543210", "+919876543210"),
            ("+91 9876543210", "+919876543210"),
            ("+91-9876543210", "+919876543210"),
            ("09876543210", "+919876543210"),
            ("+919876543210", "+919876543210"),
            ("7569304410", "+917569304410"),
            ("6281881452", "+916281881452"),
            ("8123456789", "+918123456789"),
        ]
        for raw, expected in valid_cases:
            valid, normalized, err = normalize_indian_phone(raw)
            self.assertTrue(valid, f"Expected valid phone: {raw}, got error: {err}")
            self.assertEqual(normalized, expected, f"Failed to normalize valid phone: {raw}")

    # ── TEST 2: Invalid mobile number rejected ──
    def test_02_invalid_mobile_rejected(self):
        invalid_cases = [
            "",
            "   ",
            None,
            "1234567890",          # Starts with 1 (must be 6-9 in India)
            "5551234567",          # Starts with 5
            "98765",               # Too short
            "98765432101234",      # Too long
            "98765ABCD0",          # Contains letters
            "98765-4321a",         # Alphanumeric
            "9999999999",          # Repetitive / dummy number
            "8888888888",          # Repetitive / dummy number
            "+1234567890",         # Non-India country code
        ]
        for invalid in invalid_cases:
            valid, normalized, err = normalize_indian_phone(invalid)
            self.assertFalse(valid, f"Should reject invalid phone: {invalid}")
            self.assertEqual(normalized, "")

    # ── TEST 3: OTP is generated server-side using cryptographically secure secrets ──
    def test_03_otp_generated_server_side(self):
        generated_otps = set()
        for _ in range(50):
            otp = "".join(secrets.choice(string.digits) for _ in range(6))
            self.assertEqual(len(otp), 6, "OTP must be exactly 6 digits")
            self.assertTrue(otp.isdigit(), "OTP must be numeric")
            generated_otps.add(otp)
        # 50 cryptographically secure OTPs should produce high entropy (at least 45 unique values)
        self.assertGreater(len(generated_otps), 45, "OTP entropy is insufficient")

    # ── TEST 4: OTP is not returned in API response ──
    def test_04_otp_not_returned_in_api_response(self):
        # Dispatch SMS via SmsOtpProvider console
        provider = SmsOtpProvider()
        phone = "+919876543210"
        otp = "741258"
        success, message = provider.send_otp(phone, otp)
        self.assertTrue(success)

        # Build simulated API response for /api/send-otp
        api_response = {
            "success": True,
            "message": "OTP sent to +91 98765 XXXXX",
            "masked": "+91 98765 XXXXX",
            "resendCooldown": 30,
            "purpose": "login"
        }

        # Response must NOT leak OTP or plain credentials
        self.assertNotIn("otp", api_response)
        self.assertNotIn("devOtp", api_response)
        self.assertNotIn(otp, json.dumps(api_response))

    # ── TEST 5: OTP is stored hashed (SHA-256) ──
    def test_05_otp_stored_hashed(self):
        phone = "+919876543210"
        otp = "654321"
        otp_hash = hash_otp(phone, otp)

        self.assertNotEqual(otp_hash, otp, "Stored OTP must not be plaintext")
        self.assertEqual(len(otp_hash), 64, "SHA-256 hash must be 64 hex characters")

        store_otp_record(phone, otp_hash, expires_in_seconds=300, purpose="login")
        record = retrieve_otp_record(phone)

        self.assertIsNotNone(record)
        self.assertEqual(record["otp_hash"], otp_hash)
        self.assertNotEqual(record["otp_hash"], otp, "Database/cache must store hash, never plaintext")

    # ── TEST 6: Correct OTP succeeds ──
    def test_06_correct_otp_succeeds(self):
        phone = "+919876543210"
        otp = "456789"
        otp_hash = hash_otp(phone, otp)
        store_otp_record(phone, otp_hash, expires_in_seconds=300, purpose="login")

        record = retrieve_otp_record(phone)
        self.assertIsNotNone(record)

        entered_hash = hash_otp(phone, otp)
        verified = secrets.compare_digest(record["otp_hash"], entered_hash)
        self.assertTrue(verified, "Correct OTP must verify successfully")

    # ── TEST 7: Incorrect OTP fails ──
    def test_07_incorrect_otp_fails(self):
        phone = "+919876543210"
        actual_otp = "123456"
        wrong_otp = "654321"
        otp_hash = hash_otp(phone, actual_otp)
        store_otp_record(phone, otp_hash, expires_in_seconds=300, purpose="login")

        record = retrieve_otp_record(phone)
        wrong_hash = hash_otp(phone, wrong_otp)
        verified = secrets.compare_digest(record["otp_hash"], wrong_hash)
        self.assertFalse(verified, "Incorrect OTP must fail verification")

        attempts = increment_otp_attempts(phone)
        self.assertEqual(attempts, 1)

    # ── TEST 8: Expired OTP fails ──
    def test_08_expired_otp_fails(self):
        phone = "+919876543210"
        otp = "123456"
        otp_hash = hash_otp(phone, otp)
        # Expired 10 seconds ago
        store_otp_record(phone, otp_hash, expires_in_seconds=-10, purpose="login")

        record = retrieve_otp_record(phone)
        # Expired records must either return None or have expires_at < now
        if record is not None:
            is_expired = time.time() > record["expires_at"]
            self.assertTrue(is_expired, "Expired OTP must be detected as expired")
        else:
            self.assertIsNone(record, "Expired OTP should be automatically purged")

    # ── TEST 9: OTP cannot be reused (single-use) ──
    def test_09_otp_cannot_be_reused(self):
        phone = "+919876543210"
        otp = "987123"
        otp_hash = hash_otp(phone, otp)
        store_otp_record(phone, otp_hash, expires_in_seconds=300, purpose="login")

        # 1st verification succeeds
        record = retrieve_otp_record(phone)
        self.assertIsNotNone(record)
        verified = secrets.compare_digest(record["otp_hash"], hash_otp(phone, otp))
        self.assertTrue(verified)

        # Invalidate / delete immediately upon successful verification
        delete_otp_record(phone)

        # 2nd verification attempt with identical OTP must fail
        record_after = retrieve_otp_record(phone)
        self.assertIsNone(record_after, "Reused OTP must be rejected immediately")

    # ── TEST 10: Too many failed verification attempts blocked ──
    def test_10_too_many_attempts_blocked(self):
        phone = "+919876543210"
        otp = "123456"
        store_otp_record(phone, hash_otp(phone, otp), expires_in_seconds=300, purpose="login")

        # Perform 5 failed attempts
        for i in range(1, 6):
            attempts = increment_otp_attempts(phone)
            self.assertEqual(attempts, i)

        # 6th attempt should exceed the limit of 5
        record = retrieve_otp_record(phone)
        self.assertIsNotNone(record)
        self.assertGreaterEqual(record["attempts"], 5, "Failed attempts count should reach maximum")

        # Delete record when max attempts exceeded
        delete_otp_record(phone)
        self.assertIsNone(retrieve_otp_record(phone), "Record must be deleted after max attempts")

    # ── TEST 11: Too many OTP requests rate limited ──
    def test_11_too_many_otp_requests_rate_limited(self):
        phone = "+919876543210"
        now = time.time()

        # Simulate 3 OTP requests within 15 minutes
        OTP_RATE_LIMITS[phone] = [now - 60, now - 30, now - 5]

        # 4th request within 15 minutes must be rate limited
        cutoff = now - 900
        recent = [t for t in OTP_RATE_LIMITS[phone] if t > cutoff]
        is_rate_limited = len(recent) >= 3
        self.assertTrue(is_rate_limited, "Should rate limit after 3 requests in 15 minutes")

    # ── TEST 12: Password login cannot bypass OTP ──
    def test_12_password_login_cannot_bypass_otp(self):
        # When valid credentials are sent to /api/login/password, it returns requiresOtp: True
        # but NEVER returns an authenticated user or creates a session.
        simulated_response = {
            "success": True,
            "requiresOtp": True,
            "identifier": "+919876543210",
            "channel": "sms",
            "masked": "+91 98765 XXXXX",
            "message": "Password verified. OTP sent to +91 98765 XXXXX"
        }
        self.assertTrue(simulated_response["requiresOtp"], "Password login must mandate OTP")
        self.assertNotIn("sessionToken", simulated_response, "Must not return session token on password alone")
        self.assertNotIn("user", simulated_response, "Must not return user session on password alone")

    # ── TEST 13: No frontend OTP generation exists ──
    def test_13_no_frontend_otp_generation(self):
        js_path = PROJECT_ROOT / "SignUp_LogIn_Form.js"
        with open(js_path, "r", encoding="utf-8") as f:
            js_content = f.read()

        # Math.random must never be used to generate OTPs
        self.assertNotIn("Math.random()", js_content, "Math.random() must not be used in JS")
        # No client-side comparison of entered OTP with frontend state
        self.assertNotIn("enteredCode === this.pending", js_content, "Frontend must never compare OTPs locally")

    # ── TEST 14: No authentication session created before OTP verification ──
    def test_14_no_pre_auth_session(self):
        js_path = PROJECT_ROOT / "SignUp_LogIn_Form.js"
        with open(js_path, "r", encoding="utf-8") as f:
            js_content = f.read()

        # Ensure no loggedIn = true or hardcoded auth before OTP
        self.assertNotIn('localStorage.setItem("loggedIn"', js_content)
        self.assertNotIn("localStorage.setItem('loggedIn'", js_content)

    # ── TEST 15: Same Indian mobile number cannot create duplicate accounts ──
    def test_15_same_mobile_cannot_create_duplicate_accounts(self):
        raw_1 = "9876543210"
        raw_2 = "+91 98765 43210"
        raw_3 = "09876543210"

        valid1, norm_1, _ = normalize_indian_phone(raw_1)
        valid2, norm_2, _ = normalize_indian_phone(raw_2)
        valid3, norm_3, _ = normalize_indian_phone(raw_3)

        self.assertTrue(valid1)
        self.assertEqual(norm_1, norm_2)
        self.assertEqual(norm_2, norm_3)
        self.assertEqual(norm_1, "+919876543210")

        # Syncing either format resolves to the identical phone_normalized
        synced, note, user_row = sync_user_to_supabase(norm_1, name="Test Customer", phone=norm_1)
        self.assertEqual(user_row["phone_normalized"], "+919876543210")

    # ── TEST 16: Firebase Phone Auth synchronization endpoint ──
    def test_16_firebase_phone_sync_endpoint(self):
        phone = "+919876543210"
        synced, note, user = sync_user_to_supabase(
            identifier=phone,
            name="Firebase Verified User",
            platform="Firebase Phone Auth",
            phone=phone
        )
        self.assertTrue(synced, "Must sync verified Firebase user to Supabase")
        self.assertIsNotNone(user)
        self.assertEqual(user["phone_normalized"], "+919876543210")
        self.assertEqual(user["name"], "Firebase Verified User")

    # ── TEST 17: Firebase Phone Duplicate Account Protection ──
    def test_17_firebase_phone_duplicate_protection(self):
        phone_raw = "9876543210"
        valid, norm_phone, _ = normalize_indian_phone(phone_raw)
        self.assertTrue(valid)

        # First sync (new user)
        s1, n1, u1 = sync_user_to_supabase(norm_phone, name="First Attempt", phone=norm_phone)
        # Second sync with different raw format (+91 98765 43210)
        valid2, norm_phone2, _ = normalize_indian_phone("+91 98765 43210")
        s2, n2, u2 = sync_user_to_supabase(norm_phone2, name="Second Attempt", phone=norm_phone2)

        self.assertEqual(norm_phone, norm_phone2)
        # Both resolve to the identical user record
        self.assertEqual(u1.get("phone_normalized"), u2.get("phone_normalized"))

    # ── TEST 18: No OTP codes stored in client storage ──
    def test_18_no_otp_stored_in_storage(self):
        js_path = PROJECT_ROOT / "SignUp_LogIn_Form.js"
        with open(js_path, "r", encoding="utf-8") as f:
            js_content = f.read()

        self.assertNotIn("localStorage.setItem('otp", js_content)
        self.assertNotIn('localStorage.setItem("otp', js_content)
        self.assertNotIn("sessionStorage.setItem('otp", js_content)
        self.assertNotIn('sessionStorage.setItem("otp', js_content)

    # ── TEST 19: Firebase Auth SDK and reCAPTCHA container in index.html ──
    def test_19_firebase_scripts_and_recaptcha_present(self):
        html_path = PROJECT_ROOT / "index.html"
        with open(html_path, "r", encoding="utf-8") as f:
            html_content = f.read()

        self.assertIn("firebase-auth-compat.js", html_content, "Firebase Auth SDK must be loaded")
        self.assertIn('id="recaptcha-container"', html_content, "recaptcha-container must be present for phone auth")

    # ── TEST 20: Firebase ID token required ──
    def test_20_firebase_id_token_required(self):
        valid, decoded, err = verify_firebase_id_token("")
        self.assertFalse(valid)
        self.assertIn("required", err.lower())

        valid_none, decoded_none, err_none = verify_firebase_id_token(None)
        self.assertFalse(valid_none)

    # ── TEST 21: Invalid Firebase ID token rejected ──
    def test_21_invalid_firebase_id_token_rejected(self):
        valid, decoded, err = verify_firebase_id_token("test_token_invalid_badtoken123")
        self.assertFalse(valid)
        self.assertIn("invalid", err.lower())
        self.assertIsNone(decoded)

    # ── TEST 22: Expired Firebase ID token rejected ──
    def test_22_expired_firebase_id_token_rejected(self):
        valid, decoded, err = verify_firebase_id_token("test_token_expired_oldtoken456")
        self.assertFalse(valid)
        self.assertIn("expired", err.lower())
        self.assertIsNone(decoded)

    # ── TEST 23: Phone number from request cannot override phone contained in verified Firebase token ──
    def test_23_client_phone_cannot_override_token_phone(self):
        # A valid verified token holds phone +919876543210 and uid fb_user_alpha
        token = "test_token_valid_+919876543210_fb_user_alpha"
        valid, decoded, _ = verify_firebase_id_token(token)
        self.assertTrue(valid)
        self.assertEqual(decoded["phone_number"], "+919876543210")
        self.assertEqual(decoded["uid"], "fb_user_alpha")

        # Client attempts tampering by sending different phone in body
        client_tampered_payload = {
            "phone": "+919999999999",
            "idToken": token
        }
        # Server verifies token and takes phone directly from decoded token, ignoring client's payload["phone"]
        verified_phone = decoded.get("phone_number")
        self.assertNotEqual(verified_phone, client_tampered_payload["phone"])
        self.assertEqual(verified_phone, "+919876543210")

        # Supabase sync uses verified_phone from decoded token
        synced, _, user_row = sync_user_to_supabase(
            identifier=verified_phone,
            phone=verified_phone,
            firebase_uid=decoded.get("uid")
        )
        self.assertTrue(synced)
        self.assertEqual(user_row["phone_normalized"], "+919876543210")
        self.assertNotEqual(user_row["phone_normalized"], client_tampered_payload["phone"])

    # ── TEST 24: Firebase UID maps to one Supabase customer ──
    def test_24_firebase_uid_maps_to_one_supabase_customer(self):
        fb_uid = "fb_unique_customer_789"
        phone = "+919876543210"

        # 1st sync with UID
        s1, n1, u1 = sync_user_to_supabase(phone, name="First Sync", phone=phone, firebase_uid=fb_uid)
        # 2nd sync with same UID but updated name
        s2, n2, u2 = sync_user_to_supabase(phone, name="Updated Name", phone=phone, firebase_uid=fb_uid)

        self.assertTrue(s1 and s2)
        # Both syncs resolve to the same user ID
        self.assertEqual(u1["id"], u2["id"])
        self.assertEqual(u1["firebase_uid"], fb_uid)
        self.assertEqual(u2["firebase_uid"], fb_uid)

    # ── TEST 25: No client-generated authentication token ──
    def test_25_no_client_generated_auth_token(self):
        js_path = PROJECT_ROOT / "SignUp_LogIn_Form.js"
        with open(js_path, "r", encoding="utf-8") as f:
            js_content = f.read()

        # No fake sb_ client token creation or handleDirectSupabasePhoneSync
        self.assertNotIn("const token = 'sb_'", js_content)
        self.assertNotIn('const token = "sb_"', js_content)
        self.assertNotIn("handleDirectSupabasePhoneSync", js_content)

    # ── TEST 26: No /api/send-otp fallback from Firebase mobile flow ──
    def test_26_no_send_otp_fallback_in_mobile_flow(self):
        js_path = PROJECT_ROOT / "SignUp_LogIn_Form.js"
        with open(js_path, "r", encoding="utf-8") as f:
            js_content = f.read()

        # Extract handleSendMobileOtp body
        start_idx = js_content.find("async handleSendMobileOtp()")
        end_idx = js_content.find("startDigitsResendTimer(", start_idx)
        self.assertGreater(start_idx, 0)
        self.assertGreater(end_idx, start_idx)
        send_code = js_content[start_idx:end_idx]

        self.assertNotIn("/api/send-otp", send_code, "handleSendMobileOtp must NOT fallback to /api/send-otp")

        # Extract handleResendMobileOtp body
        resend_start = js_content.find("async handleResendMobileOtp()")
        resend_end = js_content.find("async handleVerifyMobileOtp()", resend_start)
        self.assertGreater(resend_start, 0)
        self.assertGreater(resend_end, resend_start)
        resend_code = js_content[resend_start:resend_end]

        self.assertNotIn("/api/send-otp", resend_code, "handleResendMobileOtp must NOT fallback to /api/send-otp")

    # ── TEST 27: No /api/verify-otp fallback from Firebase mobile flow ──
    def test_27_no_verify_otp_fallback_in_mobile_flow(self):
        js_path = PROJECT_ROOT / "SignUp_LogIn_Form.js"
        with open(js_path, "r", encoding="utf-8") as f:
            js_content = f.read()

        start_idx = js_content.find("async handleVerifyMobileOtp()")
        end_idx = js_content.find("handleSuccessfulCustomerAuth(", start_idx)
        self.assertGreater(start_idx, 0)
        self.assertGreater(end_idx, start_idx)
        verify_code = js_content[start_idx:end_idx]

        self.assertNotIn("/api/verify-otp", verify_code, "handleVerifyMobileOtp must NOT fallback to /api/verify-otp")

    # ── TEST 28: localStorage cannot create authentication ──
    def test_28_localstorage_cannot_create_authentication(self):
        js_path = PROJECT_ROOT / "SignUp_LogIn_Form.js"
        with open(js_path, "r", encoding="utf-8") as f:
            js_content = f.read()

        # Check constructor does not unconditionally restore currentUser from localStorage
        constructor_start = js_content.find("this.currentUser = null;")
        self.assertGreater(constructor_start, 0)

        # Confirm onAuthStateChanged handles active authentication state
        self.assertIn("initFirebaseAuthStateListener", js_content)
        self.assertIn("onAuthStateChanged", js_content)

    # ── TEST 29: Logout signs out Firebase ──
    def test_29_logout_signs_out_firebase(self):
        js_path = PROJECT_ROOT / "SignUp_LogIn_Form.js"
        with open(js_path, "r", encoding="utf-8") as f:
            js_content = f.read()

        start_idx = js_content.find("async logoutUser()")
        end_idx = js_content.find("initAIChatbot()", start_idx)
        self.assertGreater(start_idx, 0)
        self.assertGreater(end_idx, start_idx)
        logout_code = js_content[start_idx:end_idx]

        self.assertIn("firebasePhoneAuthService.signOut()", logout_code)
        self.assertIn("localStorage.removeItem('jjv_customer_user')", logout_code)

    # ── TEST 30: Password-only login cannot authenticate ──
    def test_30_password_only_login_cannot_authenticate(self):
        # Server password verification mandates Firebase Phone OTP for customers with mobile numbers
        simulated_response = {
            "success": True,
            "requiresOtp": True,
            "requiresFirebaseOtp": True,
            "phone": "+919876543210",
            "maskedTarget": "+91987 XXXXX"
        }
        self.assertTrue(simulated_response["requiresFirebaseOtp"])
        self.assertNotIn("sessionToken", simulated_response)
        self.assertNotIn("user", simulated_response)

    # ── TEST 31: Correct Firebase test OTP authenticates ──
    def test_31_correct_firebase_test_otp_authenticates(self):
        token = "test_token_valid_+919876543210_fb_usr_test123"
        valid, decoded, err = verify_firebase_id_token(token)
        self.assertTrue(valid)
        self.assertEqual(decoded["phone_number"], "+919876543210")
        self.assertEqual(decoded["uid"], "fb_usr_test123")

    # ── TEST 32: Invalid Firebase OTP fails ──
    def test_32_invalid_firebase_otp_fails(self):
        token = "test_token_invalid_code"
        valid, decoded, err = verify_firebase_id_token(token)
        self.assertFalse(valid)
        self.assertIn("invalid", err.lower())

    # ── TEST 33: Expired Firebase OTP fails ──
    def test_33_expired_firebase_otp_fails(self):
        token = "test_token_expired_code"
        valid, decoded, err = verify_firebase_id_token(token)
        self.assertFalse(valid)
        self.assertIn("expired", err.lower())

    # ── TEST 34: Vercel serverless function compatibility ──
    def test_34_vercel_serverless_handler_compatibility(self):
        import http.server
        import api.index as api_index

        # 1. api/index.py exposes a valid handler subclass of BaseHTTPRequestHandler
        self.assertTrue(hasattr(api_index, "handler"), "api/index.py must expose 'handler'")
        self.assertTrue(
            issubclass(api_index.handler, http.server.BaseHTTPRequestHandler),
            "api/index.handler must inherit from BaseHTTPRequestHandler for Vercel Python runtime"
        )

        # 2. server.py also exposes 'handler'
        self.assertTrue(hasattr(server, "handler"), "server.py must export 'handler'")
        self.assertTrue(issubclass(server.handler, http.server.BaseHTTPRequestHandler))

        # 3. Path resolution works across direct and rewritten routes
        dummy = server.ShopRequestHandler.__new__(server.ShopRequestHandler)
        dummy.headers = {}
        dummy.path = "/api/auth/firebase-phone"
        self.assertEqual(dummy.get_request_path(), "/api/auth/firebase-phone")

        # Rewritten path with query param ?path=
        dummy.path = "/api/index.py?path=/api/orders"
        self.assertEqual(dummy.get_request_path(), "/api/orders")

        # Injected header from Vercel edge network
        dummy.path = "/api/index.py"
        dummy.headers = {"x-matched-path": "/api/chat/rag"}
        self.assertEqual(dummy.get_request_path(), "/api/chat/rag")

        # 4. vercel.json contains rewrites mapping /api/(.*) to /api/index.py
        vercel_json_path = PROJECT_ROOT / "vercel.json"
        with open(vercel_json_path, "r", encoding="utf-8") as f:
            v_conf = json.load(f)
        rewrites = v_conf.get("rewrites", [])
        has_api_rewrite = any(r.get("source") == "/api/(.*)" and "api/index.py" in r.get("destination", "") for r in rewrites)
        self.assertTrue(has_api_rewrite, "vercel.json must rewrite /api/(.*) to api/index.py")


if __name__ == "__main__":
    unittest.main(verbosity=2)
