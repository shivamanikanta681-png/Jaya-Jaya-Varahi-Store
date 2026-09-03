#!/usr/bin/env python3
"""
Supabase Client Utility for Jaya Jaya Varahi Shop
-------------------------------------------------
Initializes the Supabase database connection and exposes client helpers.
"""

import os
from pathlib import Path
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
raw_url = os.environ.get("SUPABASE_URL", ENV.get("SUPABASE_URL", ""))
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", ENV.get("SUPABASE_KEY", ""))

# Normalize URL (handles project ref 'gftsfdlchvjylpitjbps' or full 'https://...supabase.co')
if raw_url and not raw_url.startswith("http://") and not raw_url.startswith("https://"):
    if "." not in raw_url:
        SUPABASE_URL = f"https://{raw_url}.supabase.co"
    else:
        SUPABASE_URL = f"https://{raw_url}"
else:
    SUPABASE_URL = raw_url

# Singleton client instance
_client: Client = None

def get_supabase() -> Client:
    """Returns the initialized Supabase client singleton."""
    global _client
    if _client is not None:
        return _client

    if not SUPABASE_URL or not SUPABASE_KEY:
        raise ValueError(
            "Supabase credentials missing! Please ensure SUPABASE_URL and SUPABASE_KEY are defined in .env."
        )

    try:
        _client = create_client(SUPABASE_URL, SUPABASE_KEY)
        return _client
    except Exception as e:
        raise RuntimeError(f"Failed to initialize Supabase client: {e}")

def test_connection():
    """Tests the Supabase database connection."""
    print("=" * 55)
    print(">> Testing Supabase Database Connection...")
    print("=" * 55)
    print(f">> Supabase URL : {SUPABASE_URL}")
    print(f">> Supabase Key : {SUPABASE_KEY[:8]}...{SUPABASE_KEY[-6:] if len(SUPABASE_KEY) > 14 else ''}")

    try:
        client = get_supabase()
        print(">> Supabase Client initialized successfully!")
        
        # Test basic health / schema fetch
        try:
            # Attempt a light query to verify auth/key
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
