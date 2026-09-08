#!/usr/bin/env python3
"""
Supabase Client Utility for Jaya Jaya Varahi Shop
-------------------------------------------------
Initializes the Supabase database connection and exposes client helpers.
Supports both public (anon) and privileged (service-role) instances.
"""

import os
from pathlib import Path
from typing import Optional
from supabase import create_client, Client

# Base directory
BASE_DIR = Path(__file__).resolve().parent

def load_env():
    """Simple parser for .env file."""
    env_path = BASE_DIR / ".env"
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

# Retrieve credentials
raw_url = os.environ.get("SUPABASE_URL", ENV.get("SUPABASE_URL", "https://gftsfdlchvjylpitjbps.supabase.co"))
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", ENV.get("SUPABASE_ANON_KEY", os.environ.get("SUPABASE_KEY", ENV.get("SUPABASE_KEY", "sb_publishable_aJ2OouHZ-cfj9WmmUVNOPA_IPS6GF51"))))
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", ENV.get("SUPABASE_SERVICE_ROLE_KEY", ""))

# Normalize URL
if raw_url and not raw_url.startswith("http://") and not raw_url.startswith("https://"):
    if "." not in raw_url:
        SUPABASE_URL = f"https://{raw_url}.supabase.co"
    else:
        SUPABASE_URL = f"https://{raw_url}"
else:
    SUPABASE_URL = raw_url

# Singleton client instances
_public_client: Optional[Client] = None
_service_client: Optional[Client] = None

def get_supabase(admin: bool = False) -> Client:
    """
    Returns the initialized Supabase client singleton.
    If admin=True and SUPABASE_SERVICE_ROLE_KEY is set, returns privileged client.
    """
    global _public_client, _service_client

    if admin:
        if _service_client is not None:
            return _service_client
        key = SUPABASE_SERVICE_ROLE_KEY or SUPABASE_ANON_KEY
        if not SUPABASE_URL or not key:
            raise ValueError("Supabase credentials missing for admin client!")
        try:
            _service_client = create_client(SUPABASE_URL, key)
            return _service_client
        except Exception as e:
            # Fallback to public client if service role client fails
            return get_supabase(admin=False)

    if _public_client is not None:
        return _public_client

    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        raise ValueError("Supabase credentials missing! Check SUPABASE_URL and SUPABASE_ANON_KEY in .env.")

    try:
        _public_client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
        return _public_client
    except Exception as e:
        raise RuntimeError(f"Failed to initialize Supabase public client: {e}")

def test_connection():
    """Tests the Supabase database connection."""
    print("=" * 55)
    print(">> Testing Supabase Database Connection...")
    print("=" * 55)
    print(f">> Supabase URL : {SUPABASE_URL}")
    print(f">> Supabase Anon Key : {SUPABASE_ANON_KEY[:8]}... (configured)")
    print(f">> Service Role Key  : {'Configured' if SUPABASE_SERVICE_ROLE_KEY else 'Not configured (using fallback)'}")

    try:
        client = get_supabase()
        print(">> Supabase Public Client initialized successfully!")
        try:
            res = client.table("products").select("*").limit(1).execute()
            print(f">> Connection Verified! Queried 'products' table successfully: {len(res.data)} record(s)")
        except Exception as query_err:
            print(f">> Note: Connected to Supabase project, table query note: {query_err}")
        return True
    except Exception as e:
        print(f">> Connection Error: {e}")
        return False

if __name__ == "__main__":
    test_connection()
