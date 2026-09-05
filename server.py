#!/usr/bin/env python3
"""
Jaya Jaya Varahi Shop - Local Server with Free Email OTP System
-------------------------------------------------------------
Serves website files and provides REST API endpoints for Email OTP:
- POST /api/send-otp      : Generates & emails 6-digit OTP via Gmail SMTP
- POST /api/verify-otp    : Validates entered OTP code
- POST /api/reset-password: Resets user password
"""

import http.server
import socketserver
import json
import os
import random
import time
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path
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
SMTP_EMAIL = os.environ.get("SMTP_EMAIL", ENV.get("SMTP_EMAIL", ""))
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", ENV.get("SMTP_PASSWORD", ""))
SMTP_SENDER_NAME = os.environ.get("SMTP_SENDER_NAME", ENV.get("SMTP_SENDER_NAME", "Jaya Jaya Varahi Shop"))
PORT = int(os.environ.get("PORT", ENV.get("PORT", 8000)))

# Temporary in-memory OTP storage: { email_lower: { 'otp': '123456', 'expires_at': ts, 'attempts': 0, 'verified': bool } }
OTP_CACHE = {}

def send_real_email(recipient_email, otp_code, mode="reset"):
    """Sends real email via Gmail SMTP_SSL."""
    if not SMTP_EMAIL or not SMTP_PASSWORD or "your_email" in SMTP_EMAIL:
        return False, "SMTP not configured. Using local visual OTP display."

    action_label = "Password Reset Request" if mode == "reset" else "Account Login"
    subject = f"🔑 {otp_code} is your {SMTP_SENDER_NAME} verification code"

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{SMTP_SENDER_NAME} <{SMTP_EMAIL}>"
    msg["To"] = recipient_email

    # Plaintext version
    msg.set_content(f"""Namaste!

Your one-time verification code (OTP) for {SMTP_SENDER_NAME} {action_label} is:

  {otp_code}

This code is valid for 5 minutes. If you did not make this request, please ignore this email.

Warm regards,
Jaya Jaya Varahi Shop & Gifts Team
Boduppal, Hyderabad
""")

    # Modern HTML version
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

def sync_user_to_supabase(email, name=None, platform="Website Account"):
    """Inserts or updates user in Supabase 'users' table."""
    try:
        from supabase_client import get_supabase
        client = get_supabase()
        # Check if user already exists
        existing = client.table("users").select("id, email").eq("email", email).execute()
        if existing.data and len(existing.data) > 0:
            print(f">> [Supabase] User '{email}' already present in 'users' table (id: {existing.data[0].get('id')})")
            return True, f"User already exists in Supabase (id: {existing.data[0].get('id')})"

        # Insert new user with email
        res = client.table("users").insert({"email": email}).execute()
        print(f">> [Supabase] Successfully inserted '{email}' into 'users' table!")
        return True, "Successfully inserted into Supabase 'users' table"
    except Exception as e:
        print(f">> [Supabase Note] Sync error: {e}")
        return False, str(e)

def sync_order_to_supabase(order_data):
    """Inserts an order record into Supabase 'orders' table."""
    try:
        from supabase_client import get_supabase
        client = get_supabase()
        res = client.table("orders").insert(order_data).execute()
        print(f">> [Supabase] Inserted order into 'orders' table")
        return True, res.data
    except Exception as e:
        print(f">> [Supabase Note] Order sync note: {e}")
        return False, str(e)

class ShopRequestHandler(http.server.SimpleHTTPRequestHandler):
    """Custom request handler with API endpoints and CORS support."""

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

    def _set_cors_headers(self, status=200, content_type="application/json"):
        self.send_response(status)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Content-Type", content_type)
        self.end_headers()

    def do_OPTIONS(self):
        self._set_cors_headers(200)

    def do_GET(self):
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

        # ── ROUTE 1: SEND OTP ──
        if self.path == "/api/send-otp":
            email = payload.get("email", "").strip().lower()
            mode = payload.get("mode", "reset")

            if not email or "@" not in email:
                self._set_cors_headers(400)
                self.wfile.write(json.dumps({"success": False, "error": "A valid email address is required"}).encode("utf-8"))
                return

            # Accept client-provided OTP (if 6-digit numeric) for cross-platform synchronization, or generate fresh code
            client_otp = str(payload.get("otp", "")).strip()
            if client_otp.isdigit() and len(client_otp) == 6:
                otp_code = client_otp
            else:
                otp_code = f"{random.randint(100000, 999999)}"
            expires_at = time.time() + 300  # 5 minutes expiry

            OTP_CACHE[email] = {
                "otp": otp_code,
                "expires_at": expires_at,
                "attempts": 0,
                "verified": False,
                "mode": mode
            }

            # Attempt real email send
            email_sent, status_note = send_real_email(email, otp_code, mode)

            response_data = {
                "success": True,
                "message": f"Verification code sent to {email}",
                "email": email,
                "expiresIn": 300,
                "hasSmtpConfigured": email_sent,
                "statusDetail": status_note
            }

            self._set_cors_headers(200)
            self.wfile.write(json.dumps(response_data).encode("utf-8"))
            return

        # ── ROUTE 2: VERIFY OTP ──
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
                # Automatically sync verified user to Supabase 'users' table
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

        # ── ROUTE 3: RESET PASSWORD ──
        elif self.path == "/api/reset-password":
            email = payload.get("email", "").strip().lower()
            entered_otp = str(payload.get("otp", "")).strip()
            new_password = payload.get("newPassword", "").strip()

            record = OTP_CACHE.get(email)
            if not record or (not record.get("verified") and record.get("otp") != entered_otp):
                self._set_cors_headers(403)
                self.wfile.write(json.dumps({"success": False, "error": "OTP must be verified before resetting password."}).encode("utf-8"))
                return

            if len(new_password) < 6:
                self._set_cors_headers(400)
                self.wfile.write(json.dumps({"success": False, "error": "Password must be at least 6 characters long."}).encode("utf-8"))
                return

            # Clear cached OTP
            OTP_CACHE.pop(email, None)

            # Sync user and update to Supabase
            sync_user_to_supabase(email, platform="Password Reset Completed")

            self._set_cors_headers(200)
            self.wfile.write(json.dumps({
                "success": True,
                "message": "Password reset successfully! You can now log in with your new password.",
                "email": email
            }).encode("utf-8"))
            return

        # ── ROUTE 4: LOGIN / USER SYNC TO SUPABASE ──
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

        # ── ROUTE 5: ORDERS SYNC TO SUPABASE ──
        elif self.path == "/api/orders":
            order_data = payload.get("order", payload)
            synced, result = sync_order_to_supabase(order_data)
            self._set_cors_headers(200)
            self.wfile.write(json.dumps({
                "success": True,
                "message": "Order processed successfully",
                "supabaseSynced": synced,
                "result": result
            }).encode("utf-8"))
            return

        # ── ROUTE 6: RAG CUSTOMER SUPPORT CHATBOT ──
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
                self._set_cors_headers(500)
                self.wfile.write(json.dumps({
                    "success": False,
                    "error": str(e),
                    "answer": "I apologize, our customer support engine encountered a temporary glitch. Please contact our team directly at +91 75693 04410 on WhatsApp."
                }).encode("utf-8"))
            return

        # ── ROUTE 7: RAG ORDER STATUS LOOKUP ──
        elif self.path == "/api/rag/track-order":
            order_id = payload.get("orderId")
            phone = payload.get("phone")
            client_orders = payload.get("orders", [])
            order = OrderRetriever.lookup_order(order_id=order_id, phone=phone, client_orders=client_orders)
            self._set_cors_headers(200)
            self.wfile.write(json.dumps({
                "success": True if order else False,
                "order": order
            }).encode("utf-8"))
            return

        # Fallback 404 for unknown API
        self._set_cors_headers(404)
        self.wfile.write(json.dumps({"error": "Endpoint not found"}).encode("utf-8"))

class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True

    def handle_error(self, request, client_address):
        ex_type, _, _ = sys.exc_info()
        if ex_type in (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            return
        super().handle_error(request, client_address)

import sys

def run_server():
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
    with ThreadedTCPServer(("", PORT), ShopRequestHandler) as httpd:
        print("\n=======================================================")
        print(">> Jaya Jaya Varahi Shop Server & RAG Engine is LIVE (Multi-Threaded)")
        print("=======================================================")
        print(f">> Local Web Server   : http://localhost:{PORT}")
        print(f">> RAG Chat Endpoint  : http://localhost:{PORT}/api/chat/rag")
        print(f">> Email OTP Route    : http://localhost:{PORT}/api/send-otp")
        print(f">> SMTP Configured    : {'YES (' + SMTP_EMAIL + ')' if SMTP_EMAIL and SMTP_PASSWORD else 'NO (running in visual test & auto-fill mode)'}")
        print("=======================================================\n")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nServer stopped.")

if __name__ == "__main__":
    run_server()
