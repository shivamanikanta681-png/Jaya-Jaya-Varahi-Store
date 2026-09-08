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
import re
import hashlib
import secrets
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
def hash_otp(email: str, otp: str) -> str:
    """Computes a SHA-256 digest of normalized email and OTP."""
    return hashlib.sha256(f"{email.lower().strip()}:{otp.strip()}".encode("utf-8")).hexdigest()

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

def sync_user_to_supabase(email: str, name: Optional[str] = None, platform: str = "Website Account") -> Tuple[bool, str]:
    """Inserts or updates user in Supabase 'users' table using service client."""
    try:
        from supabase_client import get_supabase
        client = get_supabase(admin=True)
        # Check if user already exists
        existing = client.table("users").select("id, email").eq("email", email).execute()
        if existing.data and len(existing.data) > 0:
            user_id = existing.data[0].get("id")
            client.table("users").update({
                "last_login": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "platform": platform
            }).eq("id", user_id).execute()
            return True, f"User already exists in Supabase (id: {user_id})"

        res = client.table("users").insert({
            "email": email,
            "name": name or email.split("@")[0].capitalize(),
            "platform": platform
        }).execute()
        return True, "Successfully inserted into Supabase 'users' table"
    except Exception as e:
        return False, str(e)

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

        # ── ROUTE 5: SEND OTP (Cryptographic, Hashed & Rate Limited) ──
        elif req_path == "/api/send-otp":
            email = payload.get("email", "").strip().lower()
            mode = payload.get("mode", "reset")
            client_ip = self.client_address[0] if self.client_address else "unknown"

            if not email or "@" not in email:
                self._set_cors_headers(400)
                self.wfile.write(json.dumps({"success": False, "error": "A valid email address is required"}).encode("utf-8"))
                return

            # Rate limiting checks
            rate_limited, rate_msg = is_rate_limited(f"email:{email}", max_requests=3, window_seconds=600, cooldown_seconds=60)
            if rate_limited:
                self._set_cors_headers(429)
                self.wfile.write(json.dumps({"success": False, "error": rate_msg}).encode("utf-8"))
                return

            ip_limited, ip_msg = is_rate_limited(f"ip:{client_ip}", max_requests=10, window_seconds=600, cooldown_seconds=5)
            if ip_limited:
                self._set_cors_headers(429)
                self.wfile.write(json.dumps({"success": False, "error": "Too many requests from this network. Please try again later."}).encode("utf-8"))
                return

            # Cryptographically secure 6-digit random code
            otp_code = f"{secrets.randbelow(900000) + 100000:06d}"
            expires_at = time.time() + 300  # 5 minutes expiry

            # Store only hashed OTP in cache for cryptographic security
            OTP_CACHE[email] = {
                "otp_hash": hash_otp(email, otp_code),
                "expires_at": expires_at,
                "attempts": 0,
                "verified": False,
                "mode": mode
            }

            email_sent, status_note = send_real_email(email, otp_code, mode)

            if APP_ENV == "development":
                print(f">> [OTP Dev Mode] Verification code generated for {email} (SMTP active: {email_sent})")
            else:
                print(f">> [OTP] Verification request processed for {email} (SMTP active: {email_sent})")

            # In production, if SMTP is configured and fails, return service unavailable
            if APP_ENV == "production" and not email_sent:
                self._set_cors_headers(503)
                self.wfile.write(json.dumps({"success": False, "error": "Email delivery service temporarily unavailable"}).encode("utf-8"))
                return

            response_data = {
                "success": True,
                "message": f"Verification code sent to {email}",
                "email": email,
                "expiresIn": 300,
                "hasSmtpConfigured": email_sent
            }

            # In dev mode without SMTP, deliver code for testing
            if APP_ENV == "development" and not email_sent:
                response_data["devOtp"] = otp_code

            self._set_cors_headers(200)
            self.wfile.write(json.dumps(response_data).encode("utf-8"))
            return

        # ── ROUTE 6: VERIFY OTP ──
        elif req_path == "/api/verify-otp":
            email = payload.get("email", "").strip().lower()
            entered_otp = str(payload.get("otp", "")).strip()

            record = OTP_CACHE.get(email)
            if not record:
                self._set_cors_headers(404)
                self.wfile.write(json.dumps({"success": False, "error": "No pending OTP request found for this email."}).encode("utf-8"))
                return

            if time.time() > record["expires_at"]:
                del OTP_CACHE[email]
                self._set_cors_headers(400)
                self.wfile.write(json.dumps({"success": False, "error": "OTP has expired. Please request a fresh code."}).encode("utf-8"))
                return

            if record["attempts"] >= 5:
                del OTP_CACHE[email]
                self._set_cors_headers(429)
                self.wfile.write(json.dumps({"success": False, "error": "Too many failed attempts. Please request a new code."}).encode("utf-8"))
                return

            # Compare SHA-256 hash of entered OTP
            if hash_otp(email, entered_otp) == record["otp_hash"]:
                record["verified"] = True
                verification_token = secrets.token_hex(24)
                record["verify_token"] = verification_token
                sync_user_to_supabase(email, platform="Email OTP Verified")
                self._set_cors_headers(200)
                self.wfile.write(json.dumps({
                    "success": True,
                    "verified": True,
                    "message": "OTP verified successfully!",
                    "email": email,
                    "token": verification_token
                }).encode("utf-8"))
                return
            else:
                record["attempts"] += 1
                remaining = 5 - record["attempts"]
                self._set_cors_headers(400)
                self.wfile.write(json.dumps({
                    "success": False,
                    "error": f"Invalid verification code. {remaining} attempt(s) remaining."
                }).encode("utf-8"))
                return

        # ── ROUTE 7: RESET PASSWORD ──
        elif req_path == "/api/reset-password":
            email = payload.get("email", "").strip().lower()
            entered_otp = str(payload.get("otp", "")).strip()
            new_password = payload.get("newPassword", "").strip()

            record = OTP_CACHE.get(email)
            otp_valid = record and (record.get("verified") or (entered_otp and record.get("otp_hash") == hash_otp(email, entered_otp)))
            if not otp_valid:
                self._set_cors_headers(403)
                self.wfile.write(json.dumps({"success": False, "error": "Valid OTP verification required before resetting password."}).encode("utf-8"))
                return

            if len(new_password) < 6:
                self._set_cors_headers(400)
                self.wfile.write(json.dumps({"success": False, "error": "Password must be at least 6 characters long."}).encode("utf-8"))
                return

            OTP_CACHE.pop(email, None)
            pwd_hash = hash_password(new_password)
            updated_db = False
            try:
                from supabase_client import get_supabase
                client = get_supabase(admin=True)
                res = client.table("users").update({"password_hash": pwd_hash, "platform": "Password Reset"}).eq("email", email).execute()
                if res.data and len(res.data) > 0:
                    updated_db = True
                else:
                    client.table("users").insert({
                        "email": email,
                        "name": email.split("@")[0].capitalize(),
                        "password_hash": pwd_hash,
                        "platform": "Password Reset"
                    }).execute()
                    updated_db = True
            except Exception as db_err:
                print(f"[Password Reset] DB update note: {db_err}")

            self._set_cors_headers(200)
            self.wfile.write(json.dumps({
                "success": True,
                "message": "Password reset successfully! You can now log in with your new password.",
                "email": email,
                "persisted": updated_db
            }).encode("utf-8"))
            return

        # ── ROUTE 8: PASSWORD AUTHENTICATION ──
        elif req_path == "/api/login/password":
            email = payload.get("email", "").strip().lower()
            password = payload.get("password", "").strip()

            if not email or not password:
                self._set_cors_headers(400)
                self.wfile.write(json.dumps({"success": False, "error": "Email and password are required"}).encode("utf-8"))
                return

            try:
                from supabase_client import get_supabase
                client = get_supabase(admin=True)
                res = client.table("users").select("id, email, name, password_hash").eq("email", email).maybe_single().execute()
                user_row = res.data if res else None

                if not user_row or not user_row.get("password_hash"):
                    self._set_cors_headers(401)
                    self.wfile.write(json.dumps({"success": False, "error": "Invalid email or password. Use Email OTP to log in or reset your password."}).encode("utf-8"))
                    return

                if not verify_password(user_row["password_hash"], password):
                    self._set_cors_headers(401)
                    self.wfile.write(json.dumps({"success": False, "error": "Invalid email or password"}).encode("utf-8"))
                    return

                session_token = secrets.token_hex(24)
                client.table("users").update({"last_login": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}).eq("id", user_row["id"]).execute()

                self._set_cors_headers(200)
                self.wfile.write(json.dumps({
                    "success": True,
                    "message": "Authentication successful",
                    "user": {
                        "id": user_row.get("id"),
                        "email": user_row.get("email"),
                        "name": user_row.get("name")
                    },
                    "token": session_token
                }).encode("utf-8"))
                return
            except Exception as e:
                self._set_cors_headers(500)
                self.wfile.write(json.dumps({"success": False, "error": f"Authentication error: {str(e)}"}).encode("utf-8"))
                return

        # ── ROUTE 9: USER PROFILE SYNC (Profile Data Only, Not Authentication) ──
        elif req_path in ("/api/users/sync", "/api/login"):
            email = payload.get("email", "").strip().lower()
            name = payload.get("name", "").strip()
            platform = payload.get("platform", "Website Account")

            if not email:
                self._set_cors_headers(400)
                self.wfile.write(json.dumps({"success": False, "error": "Email is required"}).encode("utf-8"))
                return

            synced, note = sync_user_to_supabase(email, name, platform)
            self._set_cors_headers(200)
            self.wfile.write(json.dumps({
                "success": True,
                "message": f"Profile synchronized for {email}",
                "email": email,
                "supabaseSynced": synced,
                "note": note
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
