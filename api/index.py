import sys
import os
from pathlib import Path

# Add project root to sys.path so server.py and sibling modules (rag_engine, supabase_client) are importable
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Import the authoritative request handler from server.py
from server import ShopRequestHandler

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
    pass
