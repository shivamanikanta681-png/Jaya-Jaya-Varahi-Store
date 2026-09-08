#!/usr/bin/env python3
"""
Jaya Jaya Varahi Shop - Production-Ready Secure Backend & API Server
--------------------------------------------------------------------
Provides robust REST APIs, server-side admin authentication, authoritative
order pricing & persistence, cryptographic OTP verification, and AI RAG support:
- GET  /api/health         : Server status & health check
- POST /api/send-otp       : Cryptographically secure 6-digit OTP with rate limiting
- POST /api/verify-otp     : Validates OTP against server cache
- POST /api/reset-password : Resets user authentication
- POST /api/admin/login    : Server-authorized owner/admin authentication
- POST /api/admin/settings : Saves discounts & announcements (Admin protected)
- POST /api/admin/categories: Saves categories (Admin protected)
- POST /api/admin/products : Adds, updates or deletes products in Supabase (Admin protected)
- POST /api/orders         : Authoritative server-validated order persistence
- POST /api/chat/rag       : RAG customer support & product recommendations
"""

import http.server
import socketserver
import json
import os
import sys
import re
import hashlib
import secrets

# Ensure resilient UTF-8 output on Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
import time
import smtplib
import ssl
import urllib.parse
from email.message import EmailMessage
from pathlib import Path
from typing import Dict, Any, Tuple, Optional
from rag_engine import get_rag_pipeline, OrderRetriever

PORT = 8000
DIRECTORY = Path(__file__).resolve().parent

# Simple .env file loader
def load_env():
    env_path = DIRECTORY / ".env"
    env_vars = {}
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env_vars[k.strip()] = v.strip().strip('"').strip("'")
    return env_vars

ENV = load_env()

# Environment settings
APP_ENV = os.environ.get("APP_ENV", ENV.get("APP_ENV", "development")).strip().lower()
PORT = int(os.environ.get("PORT", ENV.get("PORT", 8000)))

# CORS Origin Allowlist Configuration
ALLOWED_ORIGIN_CONFIG = os.environ.get("ALLOWED_ORIGIN", ENV.get("ALLOWED_ORIGIN", "")).strip()
ALLOWED_ORIGINS = [o.strip() for o in ALLOWED_ORIGIN_CONFIG.split(",") if o.strip() and o.strip() != "*"]
if not ALLOWED_ORIGINS:
    if APP_ENV == "production":
        ALLOWED_ORIGINS = ["https://jaya-jaya-varahi-shop.web.app", "https://jayajayavarahi.com"]
    else:
        ALLOWED_ORIGINS = ["http://localhost:8000", "http://127.0.0.1:8000", "http://localhost:3000", "http://localhost:5173"]

def get_cors_origin(req_origin: Optional[str]) -> str:
    if not req_origin:
        return ALLOWED_ORIGINS[0]
    clean_origin = req_origin.strip().rstrip("/")
    for allowed in ALLOWED_ORIGINS:
        if clean_origin == allowed.rstrip("/"):
            return clean_origin
    if APP_ENV != "production" and ("localhost" in clean_origin or "127.0.0.1" in clean_origin):
        return clean_origin
    return ALLOWED_ORIGINS[0]

# Admin credentials (Must be set across all operational environments; 'varahi123' strictly forbidden)
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", ENV.get("ADMIN_PASSWORD", "")).strip()
if not ADMIN_PASSWORD or ADMIN_PASSWORD == "varahi123":
    if os.environ.get("TEST_MODE") == "1":
        ADMIN_PASSWORD = "test_admin_secure_pw_123"
    else:
        raise RuntimeError(
            "FATAL: A secure, non-default ADMIN_PASSWORD must be configured in your .env file or environment. "
            "Default 'varahi123' is rejected in all operational modes."
        )

# SMTP credentials
SMTP_EMAIL = os.environ.get("SMTP_EMAIL", ENV.get("SMTP_EMAIL", "")).strip()
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", ENV.get("SMTP_PASSWORD", "")).strip()
SMTP_SENDER_NAME = os.environ.get("SMTP_SENDER_NAME", ENV.get("SMTP_SENDER_NAME", "Jaya Jaya Varahi Shop")).strip()

# Gemini AI settings
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", ENV.get("GEMINI_API_KEY", "")).strip()
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", ENV.get("GEMINI_MODEL", "gemini-2.5-flash")).strip()

STORE_CONTEXT = """
You are 'Varahi AI', the official AI customer support assistant for 'Jaya Jaya Varahi Shop & Gifts' located in Boduppal / Peerzadiguda, Hyderabad.
Store Information:
- Phone / WhatsApp: +91 75693 04410
- Email: jayajayavarahi@gmail.com
- Timings: Mon-Sun 10:00 AM to 9:00 PM IST
- Address: CH7W+8RQ, P&T Colony, Peerzadiguda, Boduppal, Hyderabad, Telangana - 500092
- Hyderabad Delivery: 1 to 3 hours same-day delivery via Rapido Bike and Uber Connect.
- Outside Hyderabad: Express courier (DTDC, Blue Dart) in 2 to 4 business days.
- Catalog Highlights: Handcrafted wooden racing cars, educational STEM robots, plush teddy bears, pure brass peacock oil diyas, wooden jewellery boxes, jute return gift bags, tri-ply stainless steel cookware, and non-stick granite pans.
- Policies: Free immediate replacement or full refund if damaged during transit. Easy cancellation before parcel dispatch.
- Keep answers polite, concise, formatted with clear emojis and bullet points. Offer WhatsApp contact (+91 75693 04410) when helpful.
"""

# Ephemeral Caches
OTP_CACHE: Dict[str, Dict[str, Any]] = {}
OTP_RATE_LIMITS: Dict[str, list] = {}  # key -> [timestamps]
ADMIN_SESSIONS: Dict[str, float] = {}  # token -> expires_at

# ── Cryptographic Hashing Helpers ──
def hash_otp(identifier: str, otp: str) -> str:
    """Computes a SHA-256 digest of normalized identifier (phone or email) and OTP."""
    return hashlib.sha256(f"{identifier.lower().strip()}:{otp.strip()}".encode("utf-8")).hexdigest()

def hash_password(password: str) -> str:
    """Computes salted PBKDF2-HMAC-SHA256 password hash."""
    salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000)
    return f"{salt}${h.hex()}"

def verify_password(stored: str, provided: str) -> bool:
    """Safely verifies a provided password against stored salted hash."""
    try:
        salt, h = stored.split("$", 1)
        expected = hashlib.pbkdf2_hmac("sha256", provided.encode("utf-8"), salt.encode("utf-8"), 100_000).hex()
        return secrets.compare_digest(h, expected)
    except Exception:
        return False

# ── Indian Mobile Number Validation & Normalization ──
def normalize_indian_phone(phone_raw: str) -> Tuple[bool, str, str]:
    """
    Validates and normalizes Indian mobile phone numbers.
    Returns: (is_valid, normalized_e164, error_message)
    Accepts: '9876543210', '+91 9876543210', '09876543210', '+91-98765-43210', etc.
    Normalizes to standard E.164 format: '+919876543210'
    Rejects non-digits, wrong length, repetitive dummy numbers, and non-Indian starting digits (<6).
    """
    if not phone_raw or not isinstance(phone_raw, str):
        return False, "", "Mobile number is required"
    cleaned = re.sub(r"[\s\-\(\)]+", "", phone_raw.strip())
    if not re.match(r"^\+?[0-9]+$", cleaned):
        return False, "", "Mobile number must contain digits only"

    if cleaned.startswith("+91"):
        digits = cleaned[3:]
    elif cleaned.startswith("91") and len(cleaned) == 12:
        digits = cleaned[2:]
    elif cleaned.startswith("0") and len(cleaned) == 11:
        digits = cleaned[1:]
    elif len(cleaned) == 10:
        digits = cleaned
    else:
        return False, "", "Please enter a valid 10-digit Indian mobile number"

    if len(digits) != 10 or not digits.isdigit():
        return False, "", "Indian mobile number must be exactly 10 digits"
    if digits[0] not in ("6", "7", "8", "9"):
        return False, "", "Indian mobile number must start with 6, 7, 8, or 9"
    if len(set(digits)) == 1:
        return False, "", "Please enter a valid personal mobile number"

    return True, f"+91{digits}", ""

# ── SMS OTP Provider Abstraction (Fast2SMS, Twilio, MSG91, Console) ──
class SmsOtpProvider:
    """Production abstraction for Indian SMS Gateways."""
    def __init__(self):
        self.provider = os.environ.get("SMS_PROVIDER", ENV.get("SMS_PROVIDER", "console")).strip().lower()
        self.api_key = os.environ.get("SMS_API_KEY", ENV.get("SMS_API_KEY", "")).strip()
        self.sender_id = os.environ.get("SMS_SENDER_ID", ENV.get("SMS_SENDER_ID", "JJVSHP")).strip()
        self.template_id = os.environ.get("SMS_TEMPLATE_ID", ENV.get("SMS_TEMPLATE_ID", "")).strip()

    def send_otp(self, phone: str, otp_code: str, purpose: str = "login") -> Tuple[bool, str]:
        """
        Dispatches 6-digit OTP to Indian mobile number (+91...).
        Never exposes the API key or raw OTP in logs.
        """
        valid, normalized, err = normalize_indian_phone(phone)
        if not valid:
            return False, err

        ten_digit = normalized[-10:]
        message = f"Your Jaya Jaya Varahi Shop verification code is {otp_code}. Valid for 5 minutes. Do not share with anyone."

        if self.provider == "fast2sms" and self.api_key:
            try:
                import urllib.request
                url = "https://www.fast2sms.com/dev/bulkV2"
                payload = json.dumps({
                    "variables_values": otp_code,
                    "route": "otp",
                    "numbers": ten_digit
                }).encode("utf-8")
                req = urllib.request.Request(
                    url,
                    data=payload,
                    headers={
                        "authorization": self.api_key,
                        "Content-Type": "application/json"
                    },
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    resp_data = json.loads(resp.read().decode("utf-8"))
                    if resp_data.get("return") is True or resp_data.get("status_code") in (200, 201):
                        return True, "SMS sent via Fast2SMS"
                    return False, resp_data.get("message", "Failed to dispatch SMS via Fast2SMS")
            except Exception as e:
                return False, f"Fast2SMS error: {str(e)}"

        elif self.provider == "msg91" and self.api_key:
            try:
                import urllib.request
                url = f"https://api.msg91.com/api/v5/otp?template_id={self.template_id}&mobile=91{ten_digit}&authkey={self.api_key}&otp={otp_code}"
                req = urllib.request.Request(url, headers={"Content-Type": "application/json"}, method="POST")
                with urllib.request.urlopen(req, timeout=10) as resp:
                    return True, "SMS sent via MSG91"
            except Exception as e:
                return False, f"MSG91 error: {str(e)}"

        elif self.provider == "twilio" and self.api_key:
            try:
                import urllib.request
                import urllib.parse
                import base64
                account_sid = os.environ.get("TWILIO_ACCOUNT_SID", ENV.get("TWILIO_ACCOUNT_SID", "")).strip()
                from_num = os.environ.get("TWILIO_PHONE_NUMBER", ENV.get("TWILIO_PHONE_NUMBER", "")).strip()
                if account_sid and from_num:
                    url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
                    post_data = urllib.parse.urlencode({
                        "To": normalized,
                        "From": from_num,
                        "Body": message
                    }).encode("utf-8")
                    auth_header = "Basic " + base64.b64encode(f"{account_sid}:{self.api_key}".encode("utf-8")).decode("utf-8")
                    req = urllib.request.Request(url, data=post_data, headers={"Authorization": auth_header}, method="POST")
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        return True, "SMS sent via Twilio"
            except Exception as e:
                return False, f"Twilio error: {str(e)}"

        # Default fallback: console logger (safe masked phone, used in dev / test / when no SMS credentials configured)
        masked_phone = f"{normalized[:6]}XXXX{normalized[-2:]}"
        if APP_ENV == "development" or os.environ.get("TEST_MODE") == "1":
            print(f">> [SmsOtpProvider: Console] Simulated OTP dispatch to {masked_phone} (purpose: {purpose})")
            return True, "Simulated SMS dispatched (Console Provider)"
        else:
            return False, "SMS provider not configured on server"

SMS_PROVIDER_INSTANCE = SmsOtpProvider()

# ── Persistent OTP Storage (Supabase Table 'otps' with In-Memory Fallback for Vercel) ──
def store_otp_record(identifier: str, otp_code: str, purpose: str = "login", user_name: str = "", expires_in_seconds: int = 300) -> Dict[str, Any]:
    """Stores salted SHA-256 OTP record in memory and attempts persistence to Supabase."""
    expires_at = time.time() + expires_in_seconds
    is_already_hash = isinstance(otp_code, str) and len(otp_code) == 64 and all(c in '0123456789abcdefABCDEF' for c in otp_code)
    otp_h = otp_code if is_already_hash else hash_otp(identifier, otp_code)
    record = {
        "otp_hash": otp_h,
        "expires_at": expires_at,
        "attempts": 0,
        "verified": False,
        "purpose": purpose,
        "user_name": user_name
    }
    OTP_CACHE[identifier] = record

    try:
        from supabase_client import get_supabase
        client = get_supabase(admin=True)
        try:
            client.table("otps").delete().eq("identifier", identifier).execute()
        except Exception:
            pass
        client.table("otps").insert({
            "identifier": identifier,
            "otp_hash": otp_h,
            "expires_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(expires_at)),
            "attempts": 0,
            "purpose": purpose,
            "verified": False,
            "user_name": user_name
        }).execute()
    except Exception as e:
        if APP_ENV == "development":
            print(f"[Supabase OTP Persistence Note] {e}")

    return record

def retrieve_otp_record(identifier: str) -> Optional[Dict[str, Any]]:
    """Retrieves OTP record from Supabase 'otps' table or local fallback cache."""
    now = time.time()

    # 1. Check Supabase persistent table first (vital for Vercel serverless lambdas)
    try:
        from supabase_client import get_supabase
        client = get_supabase(admin=True)
        res = client.table("otps").select("*").eq("identifier", identifier).order("created_at", desc=True).limit(1).execute()
        if res and res.data and len(res.data) > 0:
            db_row = res.data[0]
            from datetime import datetime
            exp_str = db_row["expires_at"].replace("Z", "+00:00")
            dt = datetime.fromisoformat(exp_str)
            exp_ts = dt.timestamp()
            if exp_ts < now:
                # Expired - delete from database and return None
                try:
                    client.table("otps").delete().eq("identifier", identifier).execute()
                except Exception:
                    pass
                return None

            return {
                "id": db_row.get("id"),
                "otp_hash": db_row.get("otp_hash"),
                "expires_at": exp_ts,
                "attempts": int(db_row.get("attempts", 0)),
                "verified": bool(db_row.get("verified", False)),
                "purpose": db_row.get("purpose", "login"),
                "user_name": db_row.get("user_name", "")
            }
    except Exception:
        pass

    # 2. Fall back to in-memory OTP_CACHE
    cached = OTP_CACHE.get(identifier)
    if cached:
        if cached.get("expires_at", 0) < now:
            OTP_CACHE.pop(identifier, None)
            return None
        return cached

    return None

def increment_otp_attempts(identifier: str, current_record: Optional[Dict[str, Any]] = None) -> int:
    """Increments failed verification attempts counter and updates storage."""
    if current_record is None:
        current_record = retrieve_otp_record(identifier) or OTP_CACHE.get(identifier)
    if not current_record:
        return 0

    new_attempts = current_record.get("attempts", 0) + 1
    current_record["attempts"] = new_attempts
    if identifier in OTP_CACHE:
        OTP_CACHE[identifier]["attempts"] = new_attempts

    try:
        from supabase_client import get_supabase
        client = get_supabase(admin=True)
        client.table("otps").update({"attempts": new_attempts}).eq("identifier", identifier).execute()
    except Exception:
        pass
    return new_attempts

def delete_otp_record(identifier: str):
    """Consumes and invalidates an OTP record to prevent replay."""
    OTP_CACHE.pop(identifier, None)
    try:
        from supabase_client import get_supabase
        client = get_supabase(admin=True)
        client.table("otps").delete().eq("identifier", identifier).execute()
    except Exception:
        pass

def validate_admin_product(product: Dict[str, Any]) -> Tuple[bool, Dict[str, Any], str]:
    """Validates admin product CRUD payload fields, lengths, and types."""
    if not isinstance(product, dict):
        return False, {}, "Product payload must be an object"
    prod_id = str(product.get("id", "")).strip()
    name = str(product.get("name", "")).strip()
    category = str(product.get("category", "")).strip()
    if not prod_id or len(prod_id) > 64 or not re.match(r"^[a-zA-Z0-9_\-]+$", prod_id):
        return False, {}, "Product ID is required and must be alphanumeric with dashes/underscores (max 64 chars)"
    if not name or len(name) > 200:
        return False, {}, "Product name is required (1 to 200 characters)"
    if not category or len(category) > 64:
        return False, {}, "Product category is required"

    try:
        price = float(product.get("price", 0))
        if price < 0 or price > 1_000_000:
            return False, {}, "Price must be a non-negative number under 1,000,000"
    except (ValueError, TypeError):
        return False, {}, "Price must be a valid numeric value"

    image = str(product.get("image", "images/logo.png")).strip()
    if len(image) > 500:
        return False, {}, "Image path/URL exceeds 500 characters"

    description = str(product.get("description", "")).strip()
    if len(description) > 2000:
        return False, {}, "Description cannot exceed 2000 characters"

    clean_product = {
        "id": prod_id,
        "name": name,
        "category": category,
        "price": round(price, 2),
        "image": image,
        "description": description
    }
    return True, clean_product, ""

def is_rate_limited(key: str, max_requests: int = 3, window_seconds: int = 600, cooldown_seconds: int = 60) -> Tuple[bool, str]:
    """Checks per-key sliding window rate limit and cooldown."""
    now = time.time()
    history = [ts for ts in OTP_RATE_LIMITS.get(key, []) if now - ts < window_seconds]
    OTP_RATE_LIMITS[key] = history

    if history and (now - history[-1] < cooldown_seconds):
        wait_time = int(cooldown_seconds - (now - history[-1]))
        return True, f"Please wait {wait_time}s before requesting another verification code."

    if len(history) >= max_requests:
        return True, f"Too many verification requests. Please try again after {window_seconds // 60} minutes."

    history.append(now)
    OTP_RATE_LIMITS[key] = history
    return False, ""

def is_authenticated_admin(headers) -> bool:
    """Verifies admin token from Authorization header or custom header."""
    auth_header = headers.get("Authorization", "")
    token = ""
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
    else:
        token = headers.get("x-admin-token", "").strip()

    if not token or token not in ADMIN_SESSIONS:
        return False

    if time.time() > ADMIN_SESSIONS[token]:
        del ADMIN_SESSIONS[token]
        return False

    return True

def send_real_email(recipient_email: str, otp_code: str, mode: str = "reset") -> Tuple[bool, str]:
    """Sends real email via Gmail SMTP_SSL."""
    if not SMTP_EMAIL or not SMTP_PASSWORD or "your_email" in SMTP_EMAIL:
        return False, "SMTP not configured on server."

    action_label = "Password Reset Request" if mode == "reset" else "Account Login"
    subject = f"🔑 {otp_code} is your {SMTP_SENDER_NAME} verification code"

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{SMTP_SENDER_NAME} <{SMTP_EMAIL}>"
    msg["To"] = recipient_email

    msg.set_content(f"""Namaste!

Your one-time verification code (OTP) for {SMTP_SENDER_NAME} {action_label} is:

  {otp_code}

This code is valid for 5 minutes. If you did not make this request, please ignore this email.

Warm regards,
Jaya Jaya Varahi Shop & Gifts Team
Boduppal, Hyderabad
""")

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <style>
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f8fafc; margin: 0; padding: 24px; color: #1e293b; }}
        .card {{ max-width: 520px; margin: 0 auto; background: #ffffff; border-radius: 16px; overflow: hidden; box-shadow: 0 10px 25px rgba(0,0,0,0.06); border: 1px solid #e2e8f0; }}
        .header {{ background: linear-gradient(135deg, #b45309, #d97706); padding: 32px 24px; text-align: center; color: #ffffff; }}
        .header h1 {{ margin: 0 0 6px 0; font-size: 22px; font-weight: 700; letter-spacing: 0.5px; }}
        .header p {{ margin: 0; font-size: 13.5px; opacity: 0.92; }}
        .body {{ padding: 32px 28px; text-align: center; }}
        .otp-box {{ display: inline-block; letter-spacing: 8px; font-size: 34px; font-weight: 800; color: #b45309; background: #fef3c7; border: 2px dashed #f59e0b; padding: 14px 28px; border-radius: 12px; margin: 20px 0; }}
        .note {{ font-size: 13px; color: #64748b; line-height: 1.6; margin-top: 16px; }}
        .footer {{ background: #f1f5f9; padding: 16px; font-size: 12px; text-align: center; color: #94a3b8; border-top: 1px solid #e2e8f0; }}
      </style>
    </head>
    <body>
      <div class="card">
        <div class="header">
          <h1>Jaya Jaya Varahi Shop</h1>
          <p>Divine Gifts & Sacred Decor Store</p>
        </div>
        <div class="body">
          <h2 style="font-size: 18px; color: #0f172a; margin-top: 0;">{action_label} Verification</h2>
          <p style="font-size: 14.5px; color: #475569;">Use the one-time password below to complete your verification:</p>
          <div class="otp-box">{otp_code}</div>
          <p class="note">⏳ This code is valid for <strong>5 minutes</strong>.<br>For your security, never share this code with anyone.</p>
        </div>
        <div class="footer">
          Jaya Jaya Varahi Shop • Boduppal, Hyderabad • WhatsApp: +91 75693 04410
        </div>
      </div>
    </body>
    </html>
    """
    msg.add_alternative(html_content, subtype="html")

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
            server.login(SMTP_EMAIL, SMTP_PASSWORD)
            server.send_message(msg)
        return True, "Email sent successfully via Gmail SMTP."
    except Exception as e:
        return False, f"SMTP Error: {str(e)}"

def sync_user_to_supabase(
    identifier: str,
    name: Optional[str] = None,
    platform: str = "Mobile OTP Account",
    phone: Optional[str] = None,
    email: Optional[str] = None
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """
    Inserts or updates user in Supabase 'users' table using service client.
    Supports both Indian mobile numbers (+91...) and email addresses.
    Prevents duplicate accounts for the same normalized phone number.
    """
    try:
        from supabase_client import get_supabase
        client = get_supabase(admin=True)

        is_phone = bool(re.match(r"^\+?[0-9\s\-]+$", identifier) or (phone and not email))
        normalized_phone = None
        clean_email = None

        if is_phone:
            valid_p, norm_p, _ = normalize_indian_phone(phone or identifier)
            if valid_p:
                normalized_phone = norm_p
        elif "@" in identifier:
            clean_email = identifier.strip().lower()

        if email and "@" in email:
            clean_email = email.strip().lower()

        # Check existing by normalized phone or email
        existing_user = None
        if normalized_phone:
            try:
                res = client.table("users").select("*").eq("phone_normalized", normalized_phone).limit(1).execute()
                if res and res.data and len(res.data) > 0:
                    existing_user = res.data[0]
            except Exception:
                pass

        if not existing_user and clean_email:
            try:
                res = client.table("users").select("*").eq("email", clean_email).limit(1).execute()
                if res and res.data and len(res.data) > 0:
                    existing_user = res.data[0]
            except Exception:
                pass

        now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        if existing_user:
            user_id = existing_user.get("id")
            update_data = {
                "last_login": now_iso,
                "platform": platform
            }
            if name and not existing_user.get("name"):
                update_data["name"] = name
            if clean_email and not existing_user.get("email"):
                update_data["email"] = clean_email
            if normalized_phone and not existing_user.get("phone_normalized"):
                update_data["phone_normalized"] = normalized_phone
                update_data["phone"] = normalized_phone

            try:
                client.table("users").update(update_data).eq("id", user_id).execute()
            except Exception:
                pass
            existing_user.update(update_data)
            return True, f"User synced (id: {user_id})", existing_user

        # New user insert
        display_name = name or (normalized_phone[-4:] if normalized_phone else clean_email.split("@")[0].capitalize())
        new_row = {
            "name": display_name,
            "platform": platform,
            "created_at": now_iso,
            "last_login": now_iso
        }
        if normalized_phone:
            new_row["phone_normalized"] = normalized_phone
            new_row["phone"] = normalized_phone
        if clean_email:
            new_row["email"] = clean_email

        ins_res = client.table("users").insert(new_row).execute()
        created_user = ins_res.data[0] if ins_res and ins_res.data else new_row
        return True, "User registered successfully in Supabase", created_user
    except Exception as e:
        if os.environ.get("TEST_MODE") == "1" or APP_ENV == "development":
            fallback_user = {
                "id": f"test_{int(time.time())}",
                "name": name or (normalized_phone[-4:] if normalized_phone else "Customer"),
                "phone_normalized": normalized_phone,
                "phone": normalized_phone,
                "email": clean_email,
                "platform": platform
            }
            return True, f"Dev/Test fallback: {e}", fallback_user
        return False, str(e), None

def calculate_authoritative_order(order_payload: Dict[str, Any]) -> Tuple[bool, Dict[str, Any], str]:
    """
    Server-side authoritative pricing and order structure calculation.
    Fetches official product prices and discounts to prevent client price tampering.
    """
    customer_name = str(order_payload.get("customer_name") or order_payload.get("customerName") or "").strip()
    customer_phone = str(order_payload.get("customer_phone") or order_payload.get("phone") or "").strip()
    delivery_address = str(order_payload.get("delivery_address") or order_payload.get("addressDetails") or "").strip()
    delivery_location = str(order_payload.get("delivery_location") or ("Hyderabad" if order_payload.get("isHyderabad") else "Outside Hyderabad")).strip()
    customer_email = order_payload.get("customer_email") or order_payload.get("email")

    if not customer_name:
        return False, {}, "Customer name is required"
    if not customer_phone or len(customer_phone.replace(" ", "")) < 10:
        return False, {}, "Valid phone number (at least 10 digits) is required"
    if not delivery_address:
        return False, {}, "Delivery address is required"

    items_raw = order_payload.get("items", [])
    if not items_raw or not isinstance(items_raw, list):
        return False, {}, "Order must include at least one item"

    # Fetch catalog from Supabase or fallback to get authoritative prices
    try:
        rag = get_rag_pipeline()
        catalog = rag.product_retriever.fetch_products()
    except Exception as e:
        print(f"[Order Calc Note] Catalog fetch fallback: {e}")
        catalog = []
    catalog_map = {str(p["id"]): p for p in catalog}

    # Fetch current day discount from store settings
    day_discount = 15.0
    try:
        from supabase_client import get_supabase
        s_client = get_supabase(admin=False)
        res = s_client.table("store_settings").select("value").eq("key", "discount_offers").maybe_single().execute()
        if res.data and isinstance(res.data.get("value"), dict):
            day_discount = float(res.data["value"].get("day_discount", 15.0))
    except Exception:
        pass

    calculated_items = []
    subtotal = 0.0
    discount_multiplier = max(0.0, 1.0 - (day_discount / 100.0))

    for it in items_raw:
        if not isinstance(it, dict):
            return False, {}, "Each item in the order must be an object"
        prod_id = str(it.get("productId") or it.get("id") or "").strip()
        if not prod_id:
            return False, {}, "Order item is missing a product ID"

        raw_qty = it.get("qty") if it.get("qty") is not None else it.get("quantity")
        try:
            qty = int(raw_qty)
        except (ValueError, TypeError):
            return False, {}, f"Invalid quantity for item {prod_id}. Must be an integer."

        if qty < 1 or qty > 100:
            return False, {}, f"Invalid quantity ({qty}) for item {prod_id}. Must be between 1 and 100."

        # Strictly verify product ID against authoritative catalog (no client price fallbacks)
        matched = catalog_map.get(prod_id)
        if not matched:
            return False, {}, f"Invalid product ID '{prod_id}'. Product does not exist in store catalog."

        base_price = float(matched.get("price") or 0.0)
        if base_price <= 0:
            return False, {}, f"Authoritative price for item {prod_id} is invalid."
        p_name = matched.get("name") or f"Product {prod_id}"

        item_sub = round(base_price * qty, 2)
        subtotal += item_sub
        calculated_items.append({
            "productId": prod_id,
            "name": p_name,
            "qty": qty,
            "unitPrice": base_price,
            "subtotal": item_sub
        })

    discount_amount = round(subtotal * (day_discount / 100.0), 2)
    total_payable = round(subtotal - discount_amount, 2)

    order_number = order_payload.get("order_number") or order_payload.get("id")
    if not order_number or not str(order_number).startswith("ORD_"):
        order_number = f"ORD_{secrets.randbelow(900000) + 100000}"

    sanitized_order = {
        "order_number": order_number,
        "customer_name": customer_name,
        "customer_phone": customer_phone,
        "customer_email": customer_email,
        "delivery_location": delivery_location,
        "delivery_address": delivery_address,
        "pincode": order_payload.get("pincode"),
        "items": calculated_items,
        "subtotal": round(subtotal, 2),
        "discount_amount": discount_amount,
        "total_payable": total_payable,
        "status": "Pending Dispatch"
    }

    return True, sanitized_order, ""

def sync_order_to_supabase(order_data: Dict[str, Any]) -> Tuple[bool, Any, str]:
    """Inserts verified order record into Supabase 'orders' table."""
    try:
        from supabase_client import get_supabase
        client = get_supabase(admin=True)
        res = client.table("orders").insert(order_data).execute()
        if res.data:
            return True, res.data, "Order stored in Supabase"
        return False, None, "No data returned from database insert"
    except Exception as e:
        return False, None, str(e)

class ShopRequestHandler(http.server.SimpleHTTPRequestHandler):
    """Custom request handler with secure API endpoints and CORS support."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DIRECTORY), **kwargs)

    def handle(self):
        try:
            super().handle()
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            pass

    def end_headers(self):
        if hasattr(self, 'path') and any(self.path.split('?')[0].endswith(ext) for ext in ('.html', '.js', '.css', '.webp')):
            self.send_header("Cache-Control", "no-cache, must-revalidate")
        super().end_headers()

    def _set_cors_headers(self, status: int = 200, content_type: str = "application/json"):
        self.send_response(status)
        req_origin = self.headers.get("Origin")
        allowed_origin = get_cors_origin(req_origin)
        self.send_header("Access-Control-Allow-Origin", allowed_origin)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, x-admin-token")
        self.send_header("Vary", "Origin")
        self.send_header("Content-Type", content_type)
        self.end_headers()

    def do_OPTIONS(self):
        self._set_cors_headers(200)

    def do_DELETE(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        query_params = urllib.parse.parse_qs(parsed_url.query)

        # ── ROUTE: ADMIN PRODUCT DELETE ──
        if path == "/api/admin/products":
            if not is_authenticated_admin(self.headers):
                self._set_cors_headers(403)
                self.wfile.write(json.dumps({"success": False, "error": "Unauthorized: Admin session required"}).encode("utf-8"))
                return

            prod_id = query_params.get("id", [None])[0]
            if not prod_id:
                self._set_cors_headers(400)
                self.wfile.write(json.dumps({"success": False, "error": "Product ID is required"}).encode("utf-8"))
                return

            try:
                from supabase_client import get_supabase
                client = get_supabase(admin=True)
                client.table("products").delete().eq("id", prod_id).execute()
                self._set_cors_headers(200)
                self.wfile.write(json.dumps({"success": True, "message": f"Product {prod_id} deleted successfully"}).encode("utf-8"))
            except Exception as e:
                self._set_cors_headers(500)
                self.wfile.write(json.dumps({"success": False, "error": f"Product delete error: {str(e)}"}).encode("utf-8"))
            return

        self._set_cors_headers(404)
        self.wfile.write(json.dumps({"success": False, "error": "Endpoint not found"}).encode("utf-8"))

    def do_GET(self):
        # ── HEALTH CHECK ENDPOINT ──
        if self.path == "/api/health":
            self._set_cors_headers(200)
            health_status = {
                "success": True,
                "server": "online",
                "environment": APP_ENV,
                "databaseConfigured": bool(os.environ.get("SUPABASE_URL", ENV.get("SUPABASE_URL"))),
                "geminiConfigured": bool(GEMINI_API_KEY),
                "smtpConfigured": bool(SMTP_EMAIL and SMTP_PASSWORD and "your_email" not in SMTP_EMAIL)
            }
            self.wfile.write(json.dumps(health_status).encode("utf-8"))
            return

        # ── RAG KNOWLEDGE BASE ENDPOINT ──
        if self.path == "/api/rag/knowledge":
            rag = get_rag_pipeline()
            self._set_cors_headers(200)
            self.wfile.write(json.dumps({
                "success": True,
                "chunks_count": len(rag.kb.chunks),
                "store_info": rag.kb.store_info,
                "categories": list(set(c.get("category") for c in rag.kb.chunks))
            }).encode("utf-8"))
            return

        return super().do_GET()

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        post_body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"

        try:
            payload = json.loads(post_body) if post_body else {}
        except json.JSONDecodeError:
            self._set_cors_headers(400)
            self.wfile.write(json.dumps({"success": False, "error": "Invalid JSON format"}).encode("utf-8"))
            return

        req_path = self.path.split("?")[0]

        # ── ROUTE 1: ADMIN LOGIN ──
        if req_path == "/api/admin/login":
            entered_password = str(payload.get("password", "")).strip()
            if not entered_password or entered_password != ADMIN_PASSWORD:
                self._set_cors_headers(401)
                self.wfile.write(json.dumps({"success": False, "error": "Invalid owner/admin password"}).encode("utf-8"))
                return

            admin_token = secrets.token_hex(24)
            ADMIN_SESSIONS[admin_token] = time.time() + 86400  # 24 hours validity
            self._set_cors_headers(200)
            self.wfile.write(json.dumps({
                "success": True,
                "message": "Admin authorization granted",
                "token": admin_token,
                "expiresIn": 86400
            }).encode("utf-8"))
            return

        # ── ROUTE 2: ADMIN SAVE STORE SETTINGS ──
        elif req_path == "/api/admin/settings":
            if not is_authenticated_admin(self.headers):
                self._set_cors_headers(403)
                self.wfile.write(json.dumps({"success": False, "error": "Unauthorized: Admin session required"}).encode("utf-8"))
                return

            settings = payload.get("settings", payload)
            try:
                from supabase_client import get_supabase
                client = get_supabase(admin=True)
                client.table("store_settings").upsert({
                    "key": "discount_offers",
                    "value": settings,
                    "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                }).execute()
                self._set_cors_headers(200)
                self.wfile.write(json.dumps({"success": True, "message": "Store settings saved successfully"}).encode("utf-8"))
            except Exception as e:
                self._set_cors_headers(500)
                self.wfile.write(json.dumps({"success": False, "error": f"Failed to save settings: {str(e)}"}).encode("utf-8"))
            return

        # ── ROUTE 3: ADMIN SAVE CATEGORIES ──
        elif req_path == "/api/admin/categories":
            if not is_authenticated_admin(self.headers):
                self._set_cors_headers(403)
                self.wfile.write(json.dumps({"success": False, "error": "Unauthorized: Admin session required"}).encode("utf-8"))
                return

            categories = payload.get("categories", [])
            try:
                from supabase_client import get_supabase
                client = get_supabase(admin=True)
                records = [{
                    "id": c.get("id"),
                    "name": c.get("name"),
                    "icon": c.get("icon", "bx-grid-alt"),
                    "builtin": bool(c.get("builtin", False))
                } for c in categories if c.get("id") and c.get("name")]
                if records:
                    client.table("categories").upsert(records).execute()
                self._set_cors_headers(200)
                self.wfile.write(json.dumps({"success": True, "message": "Categories updated successfully"}).encode("utf-8"))
            except Exception as e:
                self._set_cors_headers(500)
                self.wfile.write(json.dumps({"success": False, "error": f"Failed to save categories: {str(e)}"}).encode("utf-8"))
            return

        # ── ROUTE 4: ADMIN PRODUCTS CRUD ──
        elif req_path == "/api/admin/products":
            if not is_authenticated_admin(self.headers):
                self._set_cors_headers(403)
                self.wfile.write(json.dumps({"success": False, "error": "Unauthorized: Admin session required"}).encode("utf-8"))
                return

            action = payload.get("action", "upsert")
            product = payload.get("product", {})

            try:
                from supabase_client import get_supabase
                client = get_supabase(admin=True)
                if action == "delete":
                    prod_id = str(payload.get("id") or product.get("id") or "").strip()
                    if not prod_id:
                        self._set_cors_headers(400)
                        self.wfile.write(json.dumps({"success": False, "error": "Product ID is required for deletion"}).encode("utf-8"))
                        return
                    client.table("products").delete().eq("id", prod_id).execute()
                    msg = f"Product {prod_id} deleted successfully"
                else:
                    valid, clean_prod, err = validate_admin_product(product)
                    if not valid:
                        self._set_cors_headers(400)
                        self.wfile.write(json.dumps({"success": False, "error": err}).encode("utf-8"))
                        return
                    client.table("products").upsert(clean_prod).execute()
                    msg = "Product saved successfully"

                self._set_cors_headers(200)
                self.wfile.write(json.dumps({"success": True, "message": msg}).encode("utf-8"))
            except Exception as e:
                self._set_cors_headers(500)
                self.wfile.write(json.dumps({"success": False, "error": f"Product update error: {str(e)}"}).encode("utf-8"))
            return

        # ── ROUTE 5: SEND OTP (Mobile SMS & Email, Cryptographically Secure & Rate Limited) ──
        elif req_path == "/api/send-otp":
            phone_raw = payload.get("phone") or payload.get("mobileNumber")
            email_raw = payload.get("email")
            purpose = str(payload.get("purpose") or payload.get("mode") or "login").strip().lower()
            client_ip = self.client_address[0] if self.client_address else "unknown"

            identifier = None
            is_phone = False

            if phone_raw:
                valid_phone, norm_phone, phone_err = normalize_indian_phone(str(phone_raw))
                if not valid_phone:
                    self._set_cors_headers(400)
                    self.wfile.write(json.dumps({"success": False, "error": phone_err}).encode("utf-8"))
                    return
                identifier = norm_phone
                is_phone = True
            elif email_raw and "@" in str(email_raw):
                identifier = str(email_raw).strip().lower()
            else:
                self._set_cors_headers(400)
                self.wfile.write(json.dumps({"success": False, "error": "A valid 10-digit Indian mobile number or email is required"}).encode("utf-8"))
                return

            # Rate limiting checks: Max 3 requests per identifier per 15 minutes, 30s cooldown
            rate_limited, rate_msg = is_rate_limited(f"otp:{identifier}", max_requests=3, window_seconds=900, cooldown_seconds=30)
            if rate_limited:
                self._set_cors_headers(429)
                self.wfile.write(json.dumps({"success": False, "error": rate_msg}).encode("utf-8"))
                return

            ip_limited, ip_msg = is_rate_limited(f"ip:{client_ip}", max_requests=10, window_seconds=600, cooldown_seconds=5)
            if ip_limited:
                self._set_cors_headers(429)
                self.wfile.write(json.dumps({"success": False, "error": "Too many requests from this network. Please try again later."}).encode("utf-8"))
                return

            # Cryptographically secure 6-digit random code (secrets)
            otp_code = f"{secrets.randbelow(900000) + 100000:06d}"

            # Store hashed OTP in Supabase and memory (Never store plaintext)
            store_otp_record(identifier, otp_code, purpose=purpose)

            # Dispatch via SMS provider or SMTP email
            dispatch_success = False
            status_note = ""
            if is_phone:
                dispatch_success, status_note = SMS_PROVIDER_INSTANCE.send_otp(identifier, otp_code, purpose=purpose)
            else:
                dispatch_success, status_note = send_real_email(identifier, otp_code, mode=purpose)

            # In production, if real delivery failed, report service unavailable
            if APP_ENV == "production" and not dispatch_success:
                self._set_cors_headers(503)
                self.wfile.write(json.dumps({"success": False, "error": "Delivery service temporarily unavailable. Please try again later."}).encode("utf-8"))
                return

            # Masked identifier for UI feedback (e.g. +91 98765 XXXXX)
            if is_phone:
                masked_id = f"{identifier[:6]} XXXXX"
                msg = f"OTP sent to {masked_id}"
            else:
                parts = identifier.split("@")
                masked_id = f"{parts[0][:2]}***@{parts[1]}" if len(parts[0]) > 2 else identifier
                msg = f"Verification code sent to {masked_id}"

            # SECURITY: The OTP is NEVER returned in the API response
            self._set_cors_headers(200)
            self.wfile.write(json.dumps({
                "success": True,
                "message": msg,
                "identifier": masked_id,
                "expiresIn": 300,
                "cooldownSeconds": 30
            }).encode("utf-8"))
            return

        # ── ROUTE 6: VERIFY OTP (Mobile SMS & Email Authentication) ──
        elif req_path == "/api/verify-otp":
            phone_raw = payload.get("phone") or payload.get("mobileNumber")
            email_raw = payload.get("email")
            entered_otp = str(payload.get("otp", "")).strip()
            name_raw = str(payload.get("name", "")).strip()

            identifier = None
            is_phone = False
            if phone_raw:
                valid_phone, norm_phone, phone_err = normalize_indian_phone(str(phone_raw))
                if not valid_phone:
                    self._set_cors_headers(400)
                    self.wfile.write(json.dumps({"success": False, "error": phone_err}).encode("utf-8"))
                    return
                identifier = norm_phone
                is_phone = True
            elif email_raw and "@" in str(email_raw):
                identifier = str(email_raw).strip().lower()
            else:
                self._set_cors_headers(400)
                self.wfile.write(json.dumps({"success": False, "error": "Mobile number or email is required"}).encode("utf-8"))
                return

            if not entered_otp or len(entered_otp) != 6 or not entered_otp.isdigit():
                self._set_cors_headers(400)
                self.wfile.write(json.dumps({"success": False, "error": "Please enter a valid 6-digit OTP code."}).encode("utf-8"))
                return

            record = retrieve_otp_record(identifier)
            if not record:
                self._set_cors_headers(404)
                self.wfile.write(json.dumps({"success": False, "error": "No pending OTP request found. Please request a new OTP."}).encode("utf-8"))
                return

            if time.time() > record["expires_at"]:
                delete_otp_record(identifier)
                self._set_cors_headers(400)
                self.wfile.write(json.dumps({"success": False, "error": "OTP expired. Please request a new OTP."}).encode("utf-8"))
                return

            if record["attempts"] >= 5:
                delete_otp_record(identifier)
                self._set_cors_headers(429)
                self.wfile.write(json.dumps({"success": False, "error": "Too many failed attempts. Please request a new code."}).encode("utf-8"))
                return

            # Constant-time comparison of SHA-256 hash
            expected_hash = record["otp_hash"]
            provided_hash = hash_otp(identifier, entered_otp)
            if not secrets.compare_digest(provided_hash, expected_hash):
                new_attempts = increment_otp_attempts(identifier, record)
                remaining = 5 - new_attempts
                self._set_cors_headers(400)
                self.wfile.write(json.dumps({
                    "success": False,
                    "error": f"Invalid OTP. {remaining} attempt(s) remaining." if remaining > 0 else "Too many failed attempts. Please request a new code."
                }).encode("utf-8"))
                return

            # Verification SUCCESS: Consume OTP immediately (prevents replay attack)
            delete_otp_record(identifier)

            # Check existing user in Supabase
            existing_user = None
            try:
                from supabase_client import get_supabase
                client = get_supabase(admin=True)
                if is_phone:
                    res = client.table("users").select("*").eq("phone_normalized", identifier).limit(1).execute()
                    if res and res.data and len(res.data) > 0:
                        existing_user = res.data[0]
                else:
                    res = client.table("users").select("*").eq("email", identifier).limit(1).execute()
                    if res and res.data and len(res.data) > 0:
                        existing_user = res.data[0]
            except Exception as e:
                print(f"[Supabase user lookup note] {e}")

            session_token = secrets.token_hex(32)

            if existing_user:
                # Existing customer: established authenticated session
                try:
                    from supabase_client import get_supabase
                    client = get_supabase(admin=True)
                    client.table("users").update({
                        "last_login": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                    }).eq("id", existing_user["id"]).execute()
                except Exception:
                    pass

                self._set_cors_headers(200)
                self.wfile.write(json.dumps({
                    "success": True,
                    "isNewUser": False,
                    "message": "Login successful",
                    "sessionToken": session_token,
                    "user": {
                        "id": existing_user["id"],
                        "name": existing_user.get("name") or (identifier[-4:] if is_phone else identifier.split("@")[0].capitalize()),
                        "phone": existing_user.get("phone_normalized") or existing_user.get("phone"),
                        "email": existing_user.get("email")
                    }
                }).encode("utf-8"))
                return

            else:
                # New customer: If name was passed with verify, create profile immediately
                if name_raw:
                    synced, note, user_row = sync_user_to_supabase(
                        identifier=identifier,
                        name=name_raw,
                        platform="Mobile OTP Registration" if is_phone else "Email OTP Registration",
                        phone=identifier if is_phone else None,
                        email=identifier if not is_phone else None
                    )
                    user_id = (user_row or {}).get("id") or str(secrets.token_hex(8))

                    self._set_cors_headers(200)
                    self.wfile.write(json.dumps({
                        "success": True,
                        "isNewUser": False,
                        "message": "Account created and logged in successfully!",
                        "sessionToken": session_token,
                        "user": {
                            "id": user_id,
                            "name": name_raw,
                            "phone": identifier if is_phone else None,
                            "email": identifier if not is_phone else None
                        }
                    }).encode("utf-8"))
                    return
                else:
                    # Prompt frontend to complete profile with Name
                    reg_token = secrets.token_hex(24)
                    self._set_cors_headers(200)
                    self.wfile.write(json.dumps({
                        "success": True,
                        "isNewUser": true,
                        "message": "OTP verified successfully. Please provide your name to complete registration.",
                        "token": reg_token,
                        "identifier": identifier,
                        "isPhone": is_phone
                    }).encode("utf-8"))
                    return

        # ── ROUTE 7: COMPLETE REGISTRATION (Set Name for New OTP User) ──
        elif req_path == "/api/register/complete":
            phone_raw = payload.get("phone") or payload.get("identifier")
            email_raw = payload.get("email")
            name = str(payload.get("name", "")).strip()

            if not name:
                self._set_cors_headers(400)
                self.wfile.write(json.dumps({"success": False, "error": "Your name is required to complete registration."}).encode("utf-8"))
                return

            identifier = None
            is_phone = False
            if phone_raw and re.match(r"^\+?[0-9\s\-]+$", str(phone_raw)):
                valid_p, norm_p, p_err = normalize_indian_phone(str(phone_raw))
                if not valid_p:
                    self._set_cors_headers(400)
                    self.wfile.write(json.dumps({"success": False, "error": p_err}).encode("utf-8"))
                    return
                identifier = norm_p
                is_phone = True
            elif email_raw and "@" in str(email_raw):
                identifier = str(email_raw).strip().lower()
            else:
                self._set_cors_headers(400)
                self.wfile.write(json.dumps({"success": False, "error": "Valid phone or email identifier required."}).encode("utf-8"))
                return

            synced, note, user_row = sync_user_to_supabase(
                identifier=identifier,
                name=name,
                platform="Mobile OTP Registration" if is_phone else "Email OTP Registration",
                phone=identifier if is_phone else None,
                email=str(email_raw).strip().lower() if email_raw and "@" in str(email_raw) else (identifier if not is_phone else None)
            )

            session_token = secrets.token_hex(32)
            user_id = (user_row or {}).get("id") or str(secrets.token_hex(8))

            self._set_cors_headers(200)
            self.wfile.write(json.dumps({
                "success": True,
                "message": f"Welcome to Jaya Jaya Varahi Store, {name}!",
                "sessionToken": session_token,
                "user": {
                    "id": user_id,
                    "name": name,
                    "phone": identifier if is_phone else None,
                    "email": (user_row or {}).get("email")
                }
            }).encode("utf-8"))
            return

        # ── ROUTE 8: RESET PASSWORD (Requires Valid OTP) ──
        elif req_path == "/api/reset-password":
            identifier = payload.get("phone") or payload.get("email", "").strip().lower()
            entered_otp = str(payload.get("otp", "")).strip()
            new_password = payload.get("newPassword", "").strip()

            if not identifier:
                self._set_cors_headers(400)
                self.wfile.write(json.dumps({"success": False, "error": "Email or mobile number is required"}).encode("utf-8"))
                return

            if len(new_password) < 6:
                self._set_cors_headers(400)
                self.wfile.write(json.dumps({"success": False, "error": "Password must be at least 6 characters long."}).encode("utf-8"))
                return

            record = retrieve_otp_record(identifier)
            otp_valid = record and (record.get("verified") or (entered_otp and record.get("otp_hash") == hash_otp(identifier, entered_otp)))
            if not otp_valid:
                self._set_cors_headers(403)
                self.wfile.write(json.dumps({"success": False, "error": "Valid OTP verification required before resetting password."}).encode("utf-8"))
                return

            delete_otp_record(identifier)
            pwd_hash = hash_password(new_password)
            updated_db = False
            try:
                from supabase_client import get_supabase
                client = get_supabase(admin=True)
                if "@" in identifier:
                    res = client.table("users").update({"password_hash": pwd_hash, "platform": "Password Reset"}).eq("email", identifier).execute()
                else:
                    _, norm_phone, _ = normalize_indian_phone(identifier)
                    res = client.table("users").update({"password_hash": pwd_hash, "platform": "Password Reset"}).eq("phone_normalized", norm_phone).execute()

                if res.data and len(res.data) > 0:
                    updated_db = True
            except Exception as db_err:
                print(f"[Password Reset] DB update note: {db_err}")

            self._set_cors_headers(200)
            self.wfile.write(json.dumps({
                "success": True,
                "message": "Password reset successfully! You can now log in.",
                "identifier": identifier,
                "persisted": updated_db
            }).encode("utf-8"))
            return

        # ── ROUTE 9: PASSWORD VALIDATION -> MANDATORY OTP DISPATCH (NEVER DIRECT LOGIN) ──
        elif req_path == "/api/login/password":
            identifier = str(payload.get("identifier") or payload.get("email") or payload.get("phone") or "").strip()
            password = payload.get("password", "").strip()

            if not identifier or not password:
                self._set_cors_headers(400)
                self.wfile.write(json.dumps({"success": False, "error": "Mobile/Email and password are required"}).encode("utf-8"))
                return

            try:
                from supabase_client import get_supabase
                client = get_supabase(admin=True)

                user_row = None
                if "@" in identifier:
                    res = client.table("users").select("id, email, phone, phone_normalized, name, password_hash").eq("email", identifier.lower()).maybe_single().execute()
                    user_row = res.data if res else None
                else:
                    valid_p, norm_p, _ = normalize_indian_phone(identifier)
                    if valid_p:
                        res = client.table("users").select("id, email, phone, phone_normalized, name, password_hash").eq("phone_normalized", norm_p).maybe_single().execute()
                        user_row = res.data if res else None

                if not user_row or not user_row.get("password_hash"):
                    self._set_cors_headers(401)
                    self.wfile.write(json.dumps({"success": False, "error": "Invalid credentials. Use Mobile OTP to log in or reset your password."}).encode("utf-8"))
                    return

                if not verify_password(user_row["password_hash"], password):
                    self._set_cors_headers(401)
                    self.wfile.write(json.dumps({"success": False, "error": "Invalid password"}).encode("utf-8"))
                    return

                # CREDENTIALS ARE VALID!
                # STRICT REQUIREMENT: DO NOT LOG IN DIRECTLY. DISPATCH OTP TO REGISTERED MOBILE/EMAIL.
                target_phone = user_row.get("phone_normalized") or user_row.get("phone")
                target_email = user_row.get("email")

                otp_target = target_phone or target_email
                is_phone = bool(target_phone)

                otp_code = f"{secrets.randbelow(900000) + 100000:06d}"
                store_otp_record(otp_target, otp_code, purpose="login_password_step2")

                if is_phone:
                    SMS_PROVIDER_INSTANCE.send_otp(target_phone, otp_code, purpose="login")
                    masked = f"{target_phone[:6]} XXXXX"
                    msg = f"Credentials verified. 6-digit OTP sent to your registered mobile {masked}."
                else:
                    send_real_email(target_email, otp_code, mode="login")
                    parts = target_email.split("@")
                    masked = f"{parts[0][:2]}***@{parts[1]}"
                    msg = f"Credentials verified. 6-digit OTP sent to your registered email {masked}."

                self._set_cors_headers(200)
                self.wfile.write(json.dumps({
                    "success": True,
                    "requiresOtp": True,
                    "phone": target_phone,
                    "email": target_email,
                    "identifier": otp_target,
                    "maskedTarget": masked,
                    "message": msg
                }).encode("utf-8"))
                return
            except Exception as e:
                self._set_cors_headers(500)
                self.wfile.write(json.dumps({"success": False, "error": f"Authentication check error: {str(e)}"}).encode("utf-8"))
                return

        # ── ROUTE 10: USER PROFILE SYNC (Profile Data Only, Not Authentication) ──
        elif req_path in ("/api/users/sync", "/api/login"):
            email = payload.get("email")
            phone = payload.get("phone")
            name = payload.get("name", "").strip()
            platform = payload.get("platform", "Website Account")

            identifier = phone or email
            if not identifier:
                self._set_cors_headers(400)
                self.wfile.write(json.dumps({"success": False, "error": "Phone or email is required"}).encode("utf-8"))
                return

            synced, note, user_row = sync_user_to_supabase(identifier, name=name, platform=platform, phone=phone, email=email)
            self._set_cors_headers(200)
            self.wfile.write(json.dumps({
                "success": True,
                "message": f"Profile synchronized for {identifier}",
                "supabaseSynced": synced,
                "note": note,
                "user": user_row
            }).encode("utf-8"))
            return

        # ── ROUTE 9: AUTHORITATIVE ORDER PERSISTENCE ──
        elif req_path == "/api/orders":
            try:
                order_data = payload.get("order", payload)
                valid, sanitized_order, err_msg = calculate_authoritative_order(order_data)
                if not valid:
                    self._set_cors_headers(400)
                    self.wfile.write(json.dumps({"success": False, "error": err_msg}).encode("utf-8"))
                    return

                synced, result, note = sync_order_to_supabase(sanitized_order)
                if not synced:
                    self._set_cors_headers(500)
                    self.wfile.write(json.dumps({
                        "success": False,
                        "error": "Failed to persist order to database",
                        "detail": note
                    }).encode("utf-8"))
                    return

                self._set_cors_headers(201)
                self.wfile.write(json.dumps({
                    "success": True,
                    "message": "Order validated and stored successfully",
                    "order": sanitized_order,
                    "result": result
                }).encode("utf-8"))
            except Exception as e:
                self._set_cors_headers(500)
                self.wfile.write(json.dumps({"success": False, "error": f"Order processing error: {str(e)}"}).encode("utf-8"))
            return

        # ── ROUTE 10: RAG CUSTOMER SUPPORT CHATBOT ──
        elif req_path == "/api/chat/rag":
            message = payload.get("message", "").strip()
            language = payload.get("language", "en")
            phone = payload.get("customerPhone")
            order_id = payload.get("orderId")
            day_discount = float(payload.get("dayDiscount", 15.0))
            client_orders = payload.get("orders", [])

            try:
                rag = get_rag_pipeline()
                response = rag.answer_query(
                    message=message,
                    language=language,
                    customer_phone=phone,
                    order_id=order_id,
                    day_discount=day_discount,
                    client_orders=client_orders
                )
                self._set_cors_headers(200)
                self.wfile.write(json.dumps(response).encode("utf-8"))
            except Exception as e:
                print(f"[RAG Note] Chatbot pipeline error: {e}")
                self._set_cors_headers(200)
                self.wfile.write(json.dumps({
                    "reply": "Namaste! 🙏 Our AI assistant is currently updating. For immediate help, message us on WhatsApp at +91 75693 04410!",
                    "language": language,
                    "source": "fallback"
                }).encode("utf-8"))
            return

        else:
            self._set_cors_headers(404)
            self.wfile.write(json.dumps({"success": False, "error": "Endpoint not found"}).encode("utf-8"))
            return

def run_server():
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), ShopRequestHandler) as httpd:
        print("=" * 65)
        print(f"🛍️  Jaya Jaya Varahi Shop & Gifts - Production Server")
        print(f"🚀 Running at: http://localhost:{PORT}")
        print(f"🔒 Environment: {APP_ENV.upper()}")
        print(f"🛡️  Admin Auth: Server-authorized (ADMIN_PASSWORD configured)")
        print(f"📧 SMTP Service: {'Active' if SMTP_EMAIL and SMTP_PASSWORD else 'Inactive (Dev OTP display active)'}")
        print(f"🤖 Gemini AI: {'Active' if GEMINI_API_KEY else 'Inactive (Rule-based RAG active)'}")
        print("=" * 65)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nServer shutting down gracefully.")
            httpd.shutdown()

if __name__ == "__main__":
    run_server()
