"""
GG Engage Photo Processor — License Server
==========================================
FastAPI backend that handles:
  • Stripe payment webhooks → generate key + email customer
  • License activation (binds key to hardware fingerprint on first use)
  • License validation (periodic check from running app)
  • Admin endpoints (list / revoke licenses)

Deploy to Render.com: render.yaml is included in this directory.
All secrets are read from environment variables — see .env.example.
"""

import hashlib
import logging
import os
from datetime import datetime, timezone

import stripe
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

import database as db_module
from database import get_db
from email_util import send_license_email
from keygen import format_key, generate_key, normalise_key, validate_key_hmac

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# ── Stripe config ─────────────────────────────────────────────────────────────
stripe.api_key             = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET      = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

# Admin API key for protected endpoints
ADMIN_API_KEY              = os.environ.get("ADMIN_API_KEY", "")

# ── App setup ─────────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="GG Engage License Server",
    docs_url=None,   # disable Swagger UI in production
    redoc_url=None)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://ggengage.com.au", "https://www.ggengage.com.au"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"])

db_module.init_db()


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class ActivateRequest(BaseModel):
    key:         str   # XXXX-XXXX-XXXX-XXXX (hyphens optional)
    fingerprint: str   # SHA-256 hex of hardware info, computed client-side


class ValidateRequest(BaseModel):
    key:         str
    fingerprint: str


# ── Helper ────────────────────────────────────────────────────────────────────

def _require_admin(x_admin_key: str = Header(default="")):
    if not ADMIN_API_KEY or x_admin_key != ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Forbidden")


# ── Stripe webhook ────────────────────────────────────────────────────────────

@app.post("/api/webhook/stripe", include_in_schema=False)
async def stripe_webhook(request: Request,
                         db: Session = Depends(get_db)):
    payload   = await request.body()
    sig       = request.headers.get("stripe-signature", "")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig, STRIPE_WEBHOOK_SECRET)
    except stripe.error.SignatureVerificationError:
        log.warning("Stripe webhook signature verification failed")
        raise HTTPException(400, "Invalid signature")
    except Exception as exc:
        log.error("Stripe webhook error: %s", exc)
        raise HTTPException(400, "Bad request")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]

        # Only process paid sessions
        if session.get("payment_status") != "paid":
            return {"status": "skipped"}

        customer = session.get("customer_details") or {}
        email    = customer.get("email", "")
        name     = customer.get("name", "")
        amount   = session.get("amount_total", 0)       # cents
        currency = session.get("currency", "aud")
        pay_id   = session.get("payment_intent") or session.get("id", "")

        # Stripe auto-sends a payment receipt; we just need the URL if available
        receipt_url = ""
        if pay_id and pay_id.startswith("pi_"):
            try:
                intent      = stripe.PaymentIntent.retrieve(pay_id)
                charge_id   = (intent.get("latest_charge") or "")
                if charge_id:
                    charge      = stripe.Charge.retrieve(charge_id)
                    receipt_url = charge.get("receipt_url", "")
            except Exception:
                pass

        if not email:
            log.warning("Stripe webhook: no customer email for session %s",
                        session.get("id"))
            return {"status": "no_email"}

        raw_key = generate_key()
        db_module.create_license(
            db,
            key=raw_key,
            email=email,
            customer_name=name,
            payment_id=pay_id,
            amount_paid_cents=amount,
            currency=currency)

        send_license_email(email, name, format_key(raw_key), receipt_url)
        log.info("License created for %s (payment %s)", email, pay_id)

    return {"status": "ok"}


# ── Activation endpoint ───────────────────────────────────────────────────────

@app.post("/api/activate")
@limiter.limit("8/minute")
async def activate(request: Request,
                   body: ActivateRequest,
                   db: Session = Depends(get_db)):
    """
    Called by the Windows app when a user enters their license key.
    On first call: binds the key to the supplied hardware fingerprint.
    On subsequent calls from the same machine: returns success.
    From a different machine: returns an error — key is already bound.
    """
    key_raw     = normalise_key(body.key)
    fingerprint = body.fingerprint.strip()

    # Reject clearly invalid keys without touching the DB
    if not validate_key_hmac(key_raw):
        return JSONResponse({"success": False,
                             "message": "Invalid license key. Please check and try again."})

    record = db_module.get_license(db, key_raw)

    if record is None:
        log.warning("Activation attempt for unknown key %s", key_raw[:4] + "...")
        return JSONResponse({"success": False,
                             "message": "License key not found. "
                                        "Please check for typos or contact support."})

    if record.is_revoked:
        return JSONResponse({"success": False,
                             "message": "This license has been revoked. "
                                        "Please contact support@ggengage.com.au"})

    if not record.is_activated:
        db_module.activate_license(db, record, fingerprint)
        log.info("Key activated: %s → fingerprint %s...",
                 key_raw[:4], fingerprint[:8])
        return JSONResponse({"success": True,
                             "message": "License activated successfully. "
                                        "Thank you for your purchase!"})

    if record.hardware_fingerprint == fingerprint:
        return JSONResponse({"success": True,
                             "message": "License is active on this device."})

    # Key is bound to a different machine
    log.info("Key %s... rejected — fingerprint mismatch", key_raw[:4])
    return JSONResponse({"success": False,
                         "message": (
                             "This license is already activated on a different device.\n\n"
                             "To transfer your license to this computer, "
                             "please contact support@ggengage.com.au with your "
                             "original purchase email.")})


# ── Validation endpoint (periodic check from running app) ────────────────────

@app.get("/api/validate")
@limiter.limit("30/minute")
async def validate(request: Request,
                   key: str, fingerprint: str,
                   db: Session = Depends(get_db)):
    """
    Lightweight check: is this key still valid on this machine?
    Called by the app on startup (non-blocking; failure = trust local cache).
    """
    raw    = normalise_key(key)
    record = db_module.get_license(db, raw)

    valid = (record is not None
             and record.is_activated
             and not record.is_revoked
             and record.hardware_fingerprint == fingerprint)

    return {"valid": valid}


# ── Admin endpoints ───────────────────────────────────────────────────────────

@app.get("/api/admin/licenses",
         dependencies=[Depends(_require_admin)])
def admin_list(db: Session = Depends(get_db)):
    """List all license records. Requires X-Admin-Key header."""
    records = db.query(db_module.License).order_by(
        db_module.License.created_at.desc()).all()
    return [
        {
            "key":          format_key(r.key),
            "email":        r.email,
            "name":         r.customer_name,
            "amount":       f"{r.amount_paid_cents / 100:.2f} {r.currency.upper()}",
            "payment_id":   r.payment_id,
            "activated":    r.is_activated,
            "activated_at": r.activated_at.isoformat() if r.activated_at else None,
            "revoked":      r.is_revoked,
            "created_at":   r.created_at.isoformat(),
        }
        for r in records
    ]


@app.post("/api/admin/revoke/{key}",
          dependencies=[Depends(_require_admin)])
def admin_revoke(key: str, db: Session = Depends(get_db)):
    """Revoke a license (e.g. after a chargeback). Requires X-Admin-Key header."""
    record = db_module.get_license(db, normalise_key(key))
    if record is None:
        raise HTTPException(404, "Key not found")
    record.is_revoked = True
    db.commit()
    log.info("License revoked: %s", key)
    return {"revoked": True}


@app.post("/api/admin/generate",
          dependencies=[Depends(_require_admin)])
def admin_generate(email: str, name: str = "",
                   db: Session = Depends(get_db)):
    """Manually issue a complimentary license key (e.g. for support cases)."""
    raw = generate_key()
    db_module.create_license(db, key=raw, email=email,
                             customer_name=name, payment_id="manual")
    send_license_email(email, name, format_key(raw))
    return {"key": format_key(raw), "email": email}


@app.post("/api/admin/transfer/{key}",
          dependencies=[Depends(_require_admin)])
def admin_transfer(key: str, db: Session = Depends(get_db)):
    """
    Remove the hardware binding from an activated license so the customer
    can activate it on a new device (e.g. after buying a new PC).
    """
    record = db_module.get_license(db, normalise_key(key))
    if record is None:
        raise HTTPException(404, "Key not found")
    record.is_activated         = False
    record.hardware_fingerprint = None
    record.activated_at         = None
    db.commit()
    log.info("License transfer reset: %s", key)
    return {"transferred": True, "key": format_key(record.key)}


# ── Health check ──────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat()}
