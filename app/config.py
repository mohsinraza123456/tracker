import os
import secrets

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql+psycopg2://tracker:tracker@localhost:5432/tracker"
)
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
if not ADMIN_PASSWORD:
    ADMIN_PASSWORD = "admin"
    print(
        "WARNING: ADMIN_PASSWORD is not set in the environment — using the insecure "
        "default 'admin'. Set ADMIN_USERNAME/ADMIN_PASSWORD in .env before exposing "
        "this app beyond your own machine.",
        flush=True,
    )

# Random per-process default so restarting the app invalidates old sessions if the
# operator hasn't pinned one — set SECRET_KEY in .env to keep sessions across restarts.
SECRET_KEY = os.getenv("SECRET_KEY") or secrets.token_hex(32)

# Repeat clicks from the same campaign+IP+User-Agent within this window are flagged as
# duplicates (double-clicks, reloads, retry loops) and excluded from stats/cost.
DEDUPE_WINDOW_SECONDS = int(os.getenv("DEDUPE_WINDOW_SECONDS", "10"))
