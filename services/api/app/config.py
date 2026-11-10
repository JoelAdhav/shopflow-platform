"""All settings come from environment variables (12-factor config).

The same image runs in compose, kind dev and kind prod; only the env changes.
"""

import os

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql+psycopg://shopflow:shopflow@localhost:5432/shopflow"
)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
QUEUE_NAME = os.getenv("QUEUE_NAME", "orders")
SEED_DATA = os.getenv("SEED_DATA", "false").lower() == "true"
