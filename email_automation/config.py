import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    IMAP_SERVER = os.getenv("IMAP_SERVER", "imap.gmail.com")
    IMAP_PORT = int(os.getenv("IMAP_PORT", "993"))
    EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS", "")
    EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")

    TRIGGER_CODE = os.getenv("TRIGGER_CODE", "[WGPOST]")

    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

    BUSINESS_NAME = os.getenv("BUSINESS_NAME", "Web Gecko")
    BUSINESS_WEBSITE = os.getenv("BUSINESS_WEBSITE", "https://webgecko.com.au")
    REFERRAL_CODE = os.getenv("REFERRAL_CODE", "GECKO25")

    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
    DATABASE_PATH = os.getenv("DATABASE_PATH", "data/posts.db")
    UPLOADS_PATH = os.getenv("UPLOADS_PATH", "data/images")
    CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "120"))
