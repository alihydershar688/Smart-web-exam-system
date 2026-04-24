"""
Supabase Client
Connects to your existing database
"""

import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

# Initialize Supabase
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = (
    os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    or os.getenv("SUPABASE_KEY")
    or os.getenv("SUPABASE_ANON_KEY")
)

if not supabase_url or not supabase_key:
    raise ValueError(
        "SUPABASE_URL and a Supabase key must be set. "
        "Use SUPABASE_SERVICE_ROLE_KEY for backend writes."
    )

supabase: Client = create_client(supabase_url, supabase_key)

def get_supabase():
    """Return Supabase client instance"""
    return supabase
