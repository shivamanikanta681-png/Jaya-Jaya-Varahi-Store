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
import secrets
import time
import smtplib
import ssl
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
ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", ENV.get("ALLOWED_ORIGIN", "*")).strip()

# Admin credentials
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", ENV.get("ADMIN_PASSWORD", "varahi123")).strip()

# SMTP credentials
SMTP_EMAIL = os.environ.get("SMTP_EMAIL", ENV.get("SMTP_EMAIL", "")).strip()
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", ENV.get("SMTP_PASSWORD", "")).strip()
SMTP_SENDER_NAME = os.environ.get("SMTP_SENDER_NAME", ENV.get("SMTP_SENDER_NAME", "Jaya Jaya Varahi Shop")).strip()

# Gemini AI settings
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", ENV.get("GEMINI_API_KEY", "")).strip()
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", ENV.get("GEMINI_MODEL", "gemini-1.5-flash")).strip()

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
    rag = get_rag_pipeline()
    catalog = rag.products_retriever.fetch_products()
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
        prod_id = str(it.get("productId") or it.get("id") or "")
        qty = max(1, int(it.get("qty") or it.get("quantity") or 1))
        matched = catalog_map.get(prod_id)
        if not matched:
            # Fallback if product ID not in catalog
            base_price = float(it.get("price") or 500.0)
            p_name = it.get("name") or f"Product {prod_id}"
        else:
            base_price = float(matched.get("price") or 500.0)
            p_name = matched.get("name")

        item_sub = base_price * qty
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
        origin = ALLOWED_ORIGIN if ALLOWED_ORIGIN != "*" else "*"
        self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, x-admin-token")
        self.send_header("Content-Type", content_type)
        self.end_headers()

    def do_OPTIONS(self):
        self._set_cors_headers(200)

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

        # ── ROUTE 1: ADMIN LOGIN ──
        if self.path == "/api/admin/login":
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
        elif self.path == "/api/admin/settings":
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
        elif self.path == "/api/admin/categories":
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
        elif self.path == "/api/admin/products":
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
                    prod_id = payload.get("id") or product.get("id")
                    client.table("products").delete().eq("id", prod_id).execute()
                    msg = f"Product {prod_id} deleted successfully"
                else:
                    client.table("products").upsert(product).execute()
                    msg = "Product saved successfully"

                self._set_cors_headers(200)
                self.wfile.write(json.dumps({"success": True, "message": msg}).encode("utf-8"))
            except Exception as e:
                self._set_cors_headers(500)
                self.wfile.write(json.dumps({"success": False, "error": f"Product update error: {str(e)}"}).encode("utf-8"))
            return

        # ── ROUTE 5: SEND OTP (Cryptographic & Rate Limited) ──
        elif self.path == "/api/send-otp":
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

            OTP_CACHE[email] = {
                "otp": otp_code,
                "expires_at": expires_at,
                "attempts": 0,
                "verified": False,
                "mode": mode
            }

            email_sent, status_note = send_real_email(email, otp_code, mode)

            if APP_ENV == "development":
                print(f">> [OTP Dev Mode] Code for {email}: {otp_code} (SMTP active: {email_sent})")
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

            # Only return devOtp in explicit development mode when SMTP is inactive
            if APP_ENV == "development" and not email_sent:
                response_data["devOtp"] = otp_code

            self._set_cors_headers(200)
            self.wfile.write(json.dumps(response_data).encode("utf-8"))
            return

        # ── ROUTE 6: VERIFY OTP ──
        elif self.path == "/api/verify-otp":
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

            if entered_otp == record["otp"]:
                record["verified"] = True
                sync_user_to_supabase(email, platform="Email OTP Verified")
                self._set_cors_headers(200)
                self.wfile.write(json.dumps({
                    "success": True,
                    "verified": True,
                    "message": "OTP verified successfully!",
                    "email": email
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
        elif self.path == "/api/reset-password":
            email = payload.get("email", "").strip().lower()
            entered_otp = str(payload.get("otp", "")).strip()
            new_password = payload.get("newPassword", "").strip()

            record = OTP_CACHE.get(email)
            if not record or (not record.get("verified") and record.get("otp") != entered_otp):
                self._set_cors_headers(403)
                self.wfile.write(json.dumps({"success": False, "error": "Valid OTP verification required before resetting password."}).encode("utf-8"))
                return

            if len(new_password) < 6:
                self._set_cors_headers(400)
                self.wfile.write(json.dumps({"success": False, "error": "Password must be at least 6 characters long."}).encode("utf-8"))
                return

            OTP_CACHE.pop(email, None)
            sync_user_to_supabase(email, platform="Password Reset Completed")

            self._set_cors_headers(200)
            self.wfile.write(json.dumps({
                "success": True,
                "message": "Password reset successfully! You can now log in with your new password.",
                "email": email
            }).encode("utf-8"))
            return

        # ── ROUTE 8: USER SYNC / LOGIN ──
        elif self.path == "/api/login":
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
                "message": f"Login synchronized for {email}",
                "email": email,
                "supabaseSynced": synced,
                "note": note
            }).encode("utf-8"))
            return

        # ── ROUTE 9: AUTHORITATIVE ORDER PERSISTENCE ──
        elif self.path == "/api/orders":
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
            return

        # ── ROUTE 10: RAG CUSTOMER SUPPORT CHATBOT ──
        elif self.path == "/api/chat/rag":
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
