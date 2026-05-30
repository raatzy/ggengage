import imaplib
import email
import email.header
import logging
import time
from email.policy import default as email_default_policy

from .config import Config
from .database import already_processed, mark_processed, save_post, init_db
from .post_generator import generate_social_post
from .image_handler import save_image_from_bytes, create_branded_image

logger = logging.getLogger(__name__)


def _decode_header(value: str) -> str:
    parts = email.header.decode_header(value)
    decoded = []
    for part, enc in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(enc or "utf-8", errors="replace"))
        else:
            decoded.append(str(part))
    return "".join(decoded)


def _extract_parts(msg) -> tuple[str, bytes | None, str]:
    """Return (plain_text_body, image_bytes_or_None, image_ext)."""
    body = ""
    image_data = None
    image_ext = "jpg"

    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            cd = str(part.get("Content-Disposition", ""))

            if ct == "text/plain" and "attachment" not in cd:
                charset = part.get_content_charset() or "utf-8"
                body += part.get_payload(decode=True).decode(charset, errors="replace")

            elif ct.startswith("image/") and image_data is None:
                image_data = part.get_payload(decode=True)
                image_ext = ct.split("/")[1].split(";")[0].strip() or "jpg"
    else:
        charset = msg.get_content_charset() or "utf-8"
        body = msg.get_payload(decode=True).decode(charset, errors="replace")

    return body.strip(), image_data, image_ext


def _has_trigger(subject: str, body: str) -> bool:
    trigger = Config.TRIGGER_CODE.lower()
    return trigger in subject.lower() or trigger in body.lower()


def process_inbox():
    """Connect to IMAP, find triggered emails, generate posts, save to DB."""
    init_db()

    try:
        mail = imaplib.IMAP4_SSL(Config.IMAP_SERVER, Config.IMAP_PORT)
        mail.login(Config.EMAIL_ADDRESS, Config.EMAIL_PASSWORD)
    except Exception as exc:
        logger.error("IMAP login failed: %s", exc)
        return

    try:
        mail.select("INBOX")
        _, data = mail.search(None, "UNSEEN")
        ids = data[0].split()
        logger.info("Checking inbox — %d unread message(s)", len(ids))

        for num in ids:
            _, msg_data = mail.fetch(num, "(RFC822)")
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)

            message_id = msg.get("Message-ID", "").strip()
            if not message_id:
                continue
            if already_processed(message_id):
                continue

            subject = _decode_header(msg.get("Subject", "(no subject)"))
            sender = msg.get("From", "")
            body, image_bytes, image_ext = _extract_parts(msg)

            if not _has_trigger(subject, body):
                logger.debug("No trigger in message %s — skipping", message_id)
                mark_processed(message_id)
                continue

            logger.info("Trigger found in email from %s: %s", sender, subject)

            try:
                result = generate_social_post(subject, body)
            except Exception as exc:
                logger.error("Post generation failed: %s", exc)
                continue

            if image_bytes:
                image_path = save_image_from_bytes(image_bytes, image_ext)
            else:
                image_path = create_branded_image(result["headline"], result["post_text"])

            referral_link = (
                f"{Config.BUSINESS_WEBSITE}?ref={Config.REFERRAL_CODE}"
            )

            post_id = save_post(
                email_from=sender,
                email_subject=subject,
                email_body=body,
                generated_text=result["post_text"],
                image_path=image_path,
                hashtags=result["hashtags"],
                referral_link=referral_link,
            )
            mark_processed(message_id)
            logger.info("Post #%d created and pending approval", post_id)

    finally:
        try:
            mail.logout()
        except Exception:
            pass


def run_monitor():
    """Blocking loop — call from a background thread."""
    logger.info(
        "Email monitor started. Checking every %ds for trigger code: %s",
        Config.CHECK_INTERVAL,
        Config.TRIGGER_CODE,
    )
    while True:
        try:
            process_inbox()
        except Exception as exc:
            logger.error("Unexpected error in monitor loop: %s", exc)
        time.sleep(Config.CHECK_INTERVAL)
