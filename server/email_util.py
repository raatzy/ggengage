"""
Transactional email — sends the license key to customers after payment.
Configured via environment variables; uses SMTP (Gmail / Outlook / any provider).
"""

import os
import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

log = logging.getLogger(__name__)

SMTP_HOST  = os.environ.get("SMTP_HOST",  "smtp.gmail.com")
SMTP_PORT  = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER  = os.environ.get("SMTP_USER",  "")
SMTP_PASS  = os.environ.get("SMTP_PASS",  "")
FROM_EMAIL = os.environ.get("FROM_EMAIL", SMTP_USER)
FROM_NAME  = os.environ.get("FROM_NAME",  "GG Engage")
APP_NAME   = "GG Engage Photo Processor"
SUPPORT    = "support@ggengage.com.au"
WEBSITE    = "https://ggengage.com.au"
DEEP_LINK_SCHEME = "ggphoto"


def _html_body(name: str, key_formatted: str, receipt_url: str) -> str:
    activate_link = f"{DEEP_LINK_SCHEME}://activate/{key_formatted}"
    name_display  = name.split()[0] if name else "there"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Your {APP_NAME} License</title>
</head>
<body style="margin:0;padding:0;background:#f4f4f4;font-family:Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f4;padding:30px 0;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0"
             style="background:#ffffff;border-radius:8px;overflow:hidden;
                    box-shadow:0 2px 8px rgba(0,0,0,0.08);">

        <!-- Header -->
        <tr>
          <td style="background:#1e1e1e;padding:28px 40px;text-align:center;">
            <h1 style="color:#4caf50;margin:0;font-size:22px;">{APP_NAME}</h1>
            <p style="color:#aaa;margin:6px 0 0;font-size:13px;">GG Engage</p>
          </td>
        </tr>

        <!-- Body -->
        <tr>
          <td style="padding:36px 40px;color:#333;font-size:15px;line-height:1.6;">
            <p>Hi {name_display},</p>
            <p>Thank you for your purchase! Your payment was successful and your
               license is ready to use.</p>

            <!-- Key box -->
            <div style="background:#f0f7f0;border:2px solid #4caf50;border-radius:6px;
                        padding:20px;text-align:center;margin:28px 0;">
              <p style="margin:0 0 8px;font-size:13px;color:#666;
                        text-transform:uppercase;letter-spacing:1px;">
                Your License Key</p>
              <p style="margin:0;font-size:26px;font-weight:bold;color:#1a1a1a;
                        letter-spacing:4px;font-family:monospace;">
                {key_formatted}</p>
            </div>

            <!-- Activate button (deep link) -->
            <p style="text-align:center;">
              <a href="{activate_link}"
                 style="display:inline-block;background:#4caf50;color:#fff;
                        text-decoration:none;padding:14px 32px;border-radius:6px;
                        font-size:15px;font-weight:bold;">
                Activate Now
              </a>
            </p>
            <p style="font-size:13px;color:#888;text-align:center;margin-top:6px;">
              Click the button above while {APP_NAME} is installed,<br>
              or open the app and choose <strong>Enter License Key</strong> to type it manually.
            </p>

            <hr style="border:none;border-top:1px solid #eee;margin:28px 0;">

            <!-- Receipt -->
            <p><strong>Payment confirmed.</strong>
            {"&nbsp; <a href='" + receipt_url + "' style='color:#4caf50;'>View your receipt &rarr;</a>" if receipt_url else ""}</p>

            <p style="font-size:13px;color:#666;">
              Your license is tied to the first device on which it is activated.
              If you need to transfer it to a new computer, contact
              <a href="mailto:{SUPPORT}" style="color:#4caf50;">{SUPPORT}</a>.
            </p>
          </td>
        </tr>

        <!-- Footer -->
        <tr>
          <td style="background:#f8f8f8;padding:20px 40px;text-align:center;
                     font-size:12px;color:#aaa;">
            &copy; GG Engage &nbsp;·&nbsp;
            <a href="{WEBSITE}" style="color:#4caf50;text-decoration:none;">{WEBSITE}</a>
            &nbsp;·&nbsp;
            <a href="mailto:{SUPPORT}" style="color:#4caf50;text-decoration:none;">{SUPPORT}</a>
          </td>
        </tr>

      </table>
    </td></tr>
  </table>
</body>
</html>"""


def _text_body(name: str, key_formatted: str, receipt_url: str) -> str:
    name_display = name.split()[0] if name else "there"
    lines = [
        f"Hi {name_display},",
        "",
        f"Thank you for purchasing {APP_NAME}!",
        "",
        "YOUR LICENSE KEY",
        "================",
        key_formatted,
        "",
        "To activate, open the app and click 'Enter License Key', then paste the",
        "key above.",
        "",
    ]
    if receipt_url:
        lines += [f"View your payment receipt: {receipt_url}", ""]
    lines += [
        "Your license is tied to the first device on which it is activated.",
        f"To transfer it to a new computer, contact {SUPPORT}.",
        "",
        "-- GG Engage",
        WEBSITE,
    ]
    return "\n".join(lines)


def send_license_email(to_email: str, customer_name: str,
                       key_formatted: str, receipt_url: str = "") -> bool:
    """
    Send the license key email. Returns True on success.
    Logs a warning and returns False if SMTP is not configured.
    """
    if not SMTP_USER or not SMTP_PASS:
        log.warning("SMTP not configured — skipping license email to %s", to_email)
        return False

    subject = f"Your {APP_NAME} License Key"
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"{FROM_NAME} <{FROM_EMAIL}>"
    msg["To"]      = to_email

    msg.attach(MIMEText(_text_body(customer_name, key_formatted, receipt_url), "plain"))
    msg.attach(MIMEText(_html_body(customer_name, key_formatted, receipt_url), "html"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(FROM_EMAIL, to_email, msg.as_string())
        log.info("License email sent to %s", to_email)
        return True
    except Exception as exc:
        log.error("Failed to send license email to %s: %s", to_email, exc)
        return False
