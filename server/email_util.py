"""
Transactional email utility.
All emails configured via environment variables — see .env.example.
"""

import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

log = logging.getLogger(__name__)

SMTP_HOST  = os.environ.get("SMTP_HOST",  "smtp.gmail.com")
SMTP_PORT  = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER  = os.environ.get("SMTP_USER",  "")
SMTP_PASS  = os.environ.get("SMTP_PASS",  "")
FROM_EMAIL = os.environ.get("FROM_EMAIL", SMTP_USER)
FROM_NAME  = os.environ.get("FROM_NAME",  "MJS App Origins")
SUPPORT    = "support@mjsapporigins.com.au"
WEBSITE    = "https://mjsapporigins.com.au"
APP_NAME   = "Photo GeoTager"
DEEP_LINK  = "geotager"


def _send(to: str, subject: str, html: str, plain: str) -> bool:
    if not SMTP_USER or not SMTP_PASS:
        log.warning("SMTP not configured — skipping email to %s", to)
        return False
    msg             = MIMEMultipart("alternative")
    msg["Subject"]  = subject
    msg["From"]     = f"{FROM_NAME} <{FROM_EMAIL}>"
    msg["To"]       = to
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html,  "html"))
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as s:
            s.ehlo(); s.starttls(); s.login(SMTP_USER, SMTP_PASS)
            s.sendmail(FROM_EMAIL, to, msg.as_string())
        log.info("Email sent to %s — %s", to, subject)
        return True
    except Exception as exc:
        log.error("Email failed to %s: %s", to, exc)
        return False


def _first_name(name: str) -> str:
    return name.split()[0] if name else "there"


# ── License key email (sent after payment) ────────────────────────────────────

def send_license_email(to: str, name: str, key: str, receipt_url: str = "") -> bool:
    activate_link = f"{DEEP_LINK}://activate/{key}"
    fn = _first_name(name)
    receipt_html  = (f"&nbsp;<a href='{receipt_url}' style='color:#4caf50;'>"
                     f"View receipt &rarr;</a>") if receipt_url else ""
    html = f"""<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#f4f4f4;font-family:Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f4;padding:30px 0;">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0"
       style="background:#fff;border-radius:8px;box-shadow:0 2px 8px rgba(0,0,0,.08);">
  <tr><td style="background:#1e1e1e;padding:28px 40px;text-align:center;">
    <h1 style="color:#4caf50;margin:0;font-size:22px;">{APP_NAME}</h1>
    <p style="color:#aaa;margin:6px 0 0;font-size:13px;">MJS App Origins</p>
  </td></tr>
  <tr><td style="padding:36px 40px;color:#333;font-size:15px;line-height:1.6;">
    <p>Hi {fn},</p>
    <p>Your payment was successful. Your license is ready.</p>
    <div style="background:#f0f7f0;border:2px solid #4caf50;border-radius:6px;
                padding:20px;text-align:center;margin:28px 0;">
      <p style="margin:0 0 8px;font-size:12px;color:#666;text-transform:uppercase;
                letter-spacing:1px;">Your License Key</p>
      <p style="margin:0;font-size:26px;font-weight:bold;color:#1a1a1a;
                letter-spacing:4px;font-family:monospace;">{key}</p>
    </div>
    <p style="text-align:center;">
      <a href="{activate_link}"
         style="display:inline-block;background:#4caf50;color:#fff;
                text-decoration:none;padding:14px 32px;border-radius:6px;
                font-size:15px;font-weight:bold;">Activate Now</a>
    </p>
    <p style="font-size:13px;color:#888;text-align:center;margin-top:6px;">
      Click the button above while {APP_NAME} is installed, or open the app
      and choose <strong>Enter License Key</strong> to paste it manually.
    </p>
    <hr style="border:none;border-top:1px solid #eee;margin:28px 0;">
    <p><strong>Payment confirmed.</strong>{receipt_html}</p>
    <p style="font-size:13px;color:#666;">Your license is tied to the first device
    on which it is activated. To transfer it to a new computer, open the app and
    click <em>Enter License Key</em> — it will guide you through the process.</p>
  </td></tr>
  <tr><td style="background:#f8f8f8;padding:20px 40px;text-align:center;
                 font-size:12px;color:#aaa;">
    &copy; MJS App Origins &nbsp;&middot;&nbsp;
    <a href="{WEBSITE}" style="color:#4caf50;text-decoration:none;">{WEBSITE}</a>
    &nbsp;&middot;&nbsp;
    <a href="mailto:{SUPPORT}" style="color:#4caf50;text-decoration:none;">{SUPPORT}</a>
  </td></tr>
</table></td></tr></table></body></html>"""

    plain = (f"Hi {fn},\n\nYour license key is:\n\n  {key}\n\n"
             f"Open the app and click 'Enter License Key' to activate.\n"
             + (f"Receipt: {receipt_url}\n" if receipt_url else "")
             + f"\n-- MJS App Origins\n{WEBSITE}")

    return _send(to, f"Your {APP_NAME} License Key", html, plain)


# ── Transfer verification code email ─────────────────────────────────────────

def send_transfer_code_email(to: str, name: str, code: str) -> bool:
    fn   = _first_name(name)
    html = f"""<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#f4f4f4;font-family:Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f4;padding:30px 0;">
<tr><td align="center">
<table width="520" cellpadding="0" cellspacing="0"
       style="background:#fff;border-radius:8px;box-shadow:0 2px 8px rgba(0,0,0,.08);">
  <tr><td style="background:#1e1e1e;padding:24px 40px;text-align:center;">
    <h1 style="color:#4caf50;margin:0;font-size:20px;">{APP_NAME}</h1>
  </td></tr>
  <tr><td style="padding:36px 40px;color:#333;font-size:15px;line-height:1.6;">
    <p>Hi {fn},</p>
    <p>You requested a license transfer to a new computer.</p>
    <p>Enter this code in the app to confirm:</p>
    <div style="background:#f0f7f0;border:2px solid #4caf50;border-radius:6px;
                padding:24px;text-align:center;margin:24px 0;">
      <p style="margin:0;font-size:40px;font-weight:bold;color:#1a1a1a;
                letter-spacing:10px;font-family:monospace;">{code}</p>
      <p style="margin:10px 0 0;font-size:12px;color:#888;">
        Expires in 15 minutes</p>
    </div>
    <p style="font-size:13px;color:#888;">
      If you did not request this transfer, please ignore this email and
      contact <a href="mailto:{SUPPORT}" style="color:#4caf50;">{SUPPORT}</a>
      immediately.
    </p>
  </td></tr>
  <tr><td style="background:#f8f8f8;padding:16px 40px;text-align:center;
                 font-size:12px;color:#aaa;">
    &copy; MJS App Origins &nbsp;&middot;&nbsp;
    <a href="mailto:{SUPPORT}" style="color:#4caf50;text-decoration:none;">{SUPPORT}</a>
  </td></tr>
</table></td></tr></table></body></html>"""

    plain = (f"Hi {fn},\n\nYour transfer verification code is:\n\n"
             f"  {code}\n\nExpires in 15 minutes.\n\n"
             f"If you did not request this, contact {SUPPORT}.\n\n-- MJS App Origins")

    return _send(to, f"{APP_NAME} — Transfer Verification Code", html, plain)


# ── Support ticket notification (sent to support inbox) ──────────────────────

def send_support_notification(*, ticket_ref: str, license_key: str,
                               ticket_type: str, component: str,
                               description: str, customer_email: str) -> bool:
    subject = f"[{ticket_ref}] License Transfer Request — {ticket_type}"
    plain   = (f"Ticket:      {ticket_ref}\n"
               f"Type:        {ticket_type}\n"
               f"Component:   {component}\n"
               f"Customer:    {customer_email}\n"
               f"License key: {license_key}\n\n"
               f"Description:\n{description}\n\n"
               f"Action required: transfer the hardware binding via:\n"
               f"POST /api/admin/transfer/{license_key}\n"
               f"(X-Admin-Key header required)")
    html    = f"<pre>{plain}</pre>"
    return _send(SUPPORT, subject, html, plain)
