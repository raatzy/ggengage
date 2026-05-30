"""
Web Gecko — Email → Social Post Automation
==========================================
Starts the email monitor in a background thread and launches the
Flask approval dashboard on http://localhost:5000
"""

import logging
import threading
import sys
import os

# Allow imports from project root
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from email_automation.config import Config
from email_automation.database import init_db
from email_automation.email_monitor import run_monitor
from web.app import app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("webgecko")


def main():
    _check_config()
    init_db()

    monitor_thread = threading.Thread(target=run_monitor, daemon=True, name="EmailMonitor")
    monitor_thread.start()
    logger.info("Email monitor running in background thread.")

    logger.info("Starting approval dashboard on http://localhost:5000")
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)


def _check_config():
    missing = []
    if not Config.EMAIL_ADDRESS:
        missing.append("EMAIL_ADDRESS")
    if not Config.EMAIL_PASSWORD:
        missing.append("EMAIL_PASSWORD")
    if not Config.ANTHROPIC_API_KEY:
        missing.append("ANTHROPIC_API_KEY")
    if missing:
        logger.warning(
            "Missing config values: %s  —  copy .env.example to .env and fill them in.",
            ", ".join(missing),
        )


if __name__ == "__main__":
    main()
