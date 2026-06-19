import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # Email
    IMAP_SERVER = os.getenv("IMAP_SERVER", "imap.gmail.com")
    IMAP_PORT = int(os.getenv("IMAP_PORT", "993"))
    EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS", "")
    EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")
    TRIGGER_CODE = os.getenv("TRIGGER_CODE", "[WGPOST]")

    # Anthropic
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

    # Business
    BUSINESS_NAME = os.getenv("BUSINESS_NAME", "Web Gecko")
    BUSINESS_WEBSITE = os.getenv("BUSINESS_WEBSITE", "https://webgecko.com.au")
    REFERRAL_CODE = os.getenv("REFERRAL_CODE", "GECKO25")

    # Dashboard auth
    DASHBOARD_USERNAME = os.getenv("DASHBOARD_USERNAME", "admin")
    DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "")
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")

    # Facebook / Instagram (Meta)
    FACEBOOK_PAGE_TOKEN = os.getenv("FACEBOOK_PAGE_TOKEN", "")
    FACEBOOK_PAGE_ID = os.getenv("FACEBOOK_PAGE_ID", "")
    INSTAGRAM_ACCOUNT_ID = os.getenv("INSTAGRAM_ACCOUNT_ID", "")

    # TikTok
    TIKTOK_ACCESS_TOKEN = os.getenv("TIKTOK_ACCESS_TOKEN", "")
    TIKTOK_OPEN_ID = os.getenv("TIKTOK_OPEN_ID", "")

    # X / Twitter
    TWITTER_API_KEY = os.getenv("TWITTER_API_KEY", "")
    TWITTER_API_SECRET = os.getenv("TWITTER_API_SECRET", "")
    TWITTER_ACCESS_TOKEN = os.getenv("TWITTER_ACCESS_TOKEN", "")
    TWITTER_ACCESS_TOKEN_SECRET = os.getenv("TWITTER_ACCESS_TOKEN_SECRET", "")

    # App
    DATABASE_PATH = os.getenv("DATABASE_PATH", "data/posts.db")
    UPLOADS_PATH = os.getenv("UPLOADS_PATH", "data/images")
    CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "120"))
