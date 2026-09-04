import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()
BASE_DIR = Path(__file__).resolve().parent


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-change-me")
    DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'minishop.db'}")
    DD_AGENT_HOST = os.getenv("DD_AGENT_HOST", "127.0.0.1")
    DD_DOGSTATSD_PORT = int(os.getenv("DD_DOGSTATSD_PORT", "8125"))
    DD_STATSD_ENABLED = os.getenv("DD_STATSD_ENABLED", "true").lower() == "true"