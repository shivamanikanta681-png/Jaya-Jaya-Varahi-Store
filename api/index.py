import sys
import os
import json
import traceback
from http.server import BaseHTTPRequestHandler
from pathlib import Path

# Add project root to sys.path so server.py and sibling modules (rag_engine, supabase_client) are importable
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

try:
    from server import ShopRequestHandler
    _import_error = None
except Exception:
    _import_error = traceback.format_exc()
    ShopRequestHandler = BaseHTTPRequestHandler

class handler(ShopRequestHandler):
    """
    Vercel Serverless Function entrypoint.
    Inherits from ShopRequestHandler to serve all /api/* routes:
    - /api/auth/firebase-phone
    - /api/register/complete
    - /api/login/password
    - /api/orders
    - /api/chat/rag
    - /api/admin/*
    - /api/health
    - /api/send-otp / /api/verify-otp (email flows)
    """

    def do_GET(self):
        if _import_error:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({
                "success": False,
                "error": "Serverless function initialization error",
                "detail": _import_error
            }).encode("utf-8"))
            return

        req_path = self.get_request_path()
        if req_path in ("/api", "/api/", "/api/health", "/api/rag/knowledge") or req_path.startswith("/api"):
            super().do_GET()
            return

        self.send_response(404)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps({"success": False, "error": f"Endpoint not found: {req_path}"}).encode("utf-8"))

    def do_POST(self):
        if _import_error:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({
                "success": False,
                "error": "Serverless function initialization error",
                "detail": _import_error
            }).encode("utf-8"))
            return
        super().do_POST()

    def do_OPTIONS(self):
        if _import_error:
            self.send_response(200)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS, DELETE")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, x-admin-token")
            self.end_headers()
            return
        super().do_OPTIONS()

    def do_DELETE(self):
        if _import_error:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({
                "success": False,
                "error": "Serverless function initialization error",
                "detail": _import_error
            }).encode("utf-8"))
            return
        super().do_DELETE()
