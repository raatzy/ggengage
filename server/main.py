"""
GG Engage Photo Processor — License Server
==========================================
Endpoints
  POST /api/webhook/stripe          Stripe payment → generate key + email
  POST /api/activate                First-use hardware binding
  GET  /api/validate                Periodic license health check
  POST /api/transfer/request        Email a 6-digit code for machine transfer
  POST /api/transfer/confirm        Verify code → reset binding → activate
  POST /api/support/ticket          Log a component-replacement ticket
  GET  /api/admin/licenses          List all licenses  (admin)
  POST /api/admin/revoke/{key}      Revoke a license   (admin)
  POST /api/admin/transfer/{key}    Force-reset binding (admin)
  POST /api/admin/generate          Issue complimentary key (admin)
  GET  /api/admin/tickets           List support tickets    (admin)
"""

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
from email_util import (send_license_email, send_support_notification,
                        send_transfer_code_email)
from keygen import format_key, generate_key, normalise_key, validate_key_hmac

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

stripe.api_key        = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
ADMIN_API_KEY         = os.environ.get("ADMIN_API_KEY", "")

limiter = Limiter(key_func=get_remote_address)
app     = FastAPI(title="GG Engage License Server",
                  docs_url=None, redoc_url=None)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://ggengage.com.au", "https://www.ggengage.com.au"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"])

db_module.init_db()


# ── Pydantic request bodies ───────────────────────────────────────────────────

class ActivateBody(BaseModel):
    key:         str
    fingerprint: str

class TransferRequestBody(BaseModel):
    key: str

class TransferConfirmBody(BaseModel):
    key:         str
    code:        str
    fingerprint: str

class SupportTicketBody(BaseModel):
    key:         str
    ticket_type: str   # "component_replacement"
    component:   str = ""
    description: str = ""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _require_admin(x_admin_key: str = Header(default="")):
    if not ADMIN_API_KEY or x_admin_key != ADMIN_API_KEY:
        raise HTTPException(403, "Forbidden")


def _mask_email(email: str) -> str:
    """j***@gmail.com — shows just enough for the user to identify their account."""
    if "@" not in email:
        return "your registered email address"
    local, domain = email.split("@", 1)
    return f"{local[0]}***@{domain}"


# ── Stripe webhook ────────────────────────────────────────────────────────────

@app.post("/api/webhook/stripe", include_in_schema=False)
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig     = request.headers.get("stripe-signature", "")
    try:
        event = stripe.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)
    except stripe.error.SignatureVerificationError:
        raise HTTPException(400, "Invalid signature")
    except Exception as exc:
        log.error("Stripe webhook error: %s", exc)
        raise HTTPException(400, "Bad request")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        if session.get("payment_status") != "paid":
            return {"status": "skipped"}

        customer    = session.get("customer_details") or {}
        email       = customer.get("email", "")
        name        = customer.get("name", "")
        amount      = session.get("amount_total", 0)
        currency    = session.get("currency", "aud")
        pay_id      = session.get("payment_intent") or session.get("id", "")
        receipt_url = ""

        if pay_id and pay_id.startswith("pi_"):
            try:
                intent  = stripe.PaymentIntent.retrieve(pay_id)
                chg_id  = intent.get("latest_charge") or ""
                if chg_id:
                    receipt_url = stripe.Charge.retrieve(chg_id).get(
                        "receipt_url", "")
            except Exception:
                pass

        if not email:
            log.warning("No customer email in session %s", session.get("id"))
            return {"status": "no_email"}

        raw_key = generate_key()
        db_module.create_license(db, key=raw_key, email=email,
                                 customer_name=name, payment_id=pay_id,
                                 amount_paid_cents=amount, currency=currency)
        send_license_email(email, name, format_key(raw_key), receipt_url)
        log.info("License created for %s (payment %s)", email, pay_id)

    return {"status": "ok"}


# ── Activation ────────────────────────────────────────────────────────────────

@app.post("/api/activate")
@limiter.limit("8/minute")
async def activate(request: Request, body: ActivateBody,
                   db: Session = Depends(get_db)):
    """
    Binds a key to the calling machine's hardware fingerprint on first use.
    Returns conflict=True when the key is already bound to a *different* machine
    so the client can offer the three-option resolution dialog.
    """
    key_raw     = normalise_key(body.key)
    fingerprint = body.fingerprint.strip()

    if not validate_key_hmac(key_raw):
        return JSONResponse({"success": False, "conflict": False,
                             "message": "Invalid license key. Please check and try again."})

    record = db_module.get_license(db, key_raw)

    if record is None:
        return JSONResponse({"success": False, "conflict": False,
                             "message": "License key not found. "
                                        "Please check for typos or contact support."})

    if record.is_revoked:
        return JSONResponse({"success": False, "conflict": False,
                             "message": "This license has been revoked. "
                                        "Contact support@ggengage.com.au for help."})

    if not record.is_activated:
        db_module.activate_license(db, record, fingerprint)
        log.info("Key activated: %s... → fingerprint %s...",
                 key_raw[:4], fingerprint[:8])
        return JSONResponse({"success": True, "conflict": False,
                             "message": "License activated successfully. "
                                        "Thank you for your purchase!"})

    if record.hardware_fingerprint == fingerprint:
        return JSONResponse({"success": True, "conflict": False,
                             "message": "License is active on this device."})

    # ── Machine mismatch — return conflict flag so the app shows the dialog ──
    log.info("Key %s... conflict — fingerprint mismatch", key_raw[:4])
    return JSONResponse({"success": False, "conflict": True,
                         "message": "This license is already activated on a different device."})


# ── Periodic validation ───────────────────────────────────────────────────────

@app.get("/api/validate")
@limiter.limit("30/minute")
async def validate(request: Request, key: str, fingerprint: str,
                   db: Session = Depends(get_db)):
    raw    = normalise_key(key)
    record = db_module.get_license(db, raw)
    valid  = (record is not None
              and record.is_activated
              and not record.is_revoked
              and record.hardware_fingerprint == fingerprint)
    return {"valid": valid}


# ── Machine transfer — step 1: request a verification code ───────────────────

@app.post("/api/transfer/request")
@limiter.limit("3/hour")
async def transfer_request(request: Request, body: TransferRequestBody,
                           db: Session = Depends(get_db)):
    """
    Customer says "I bought a new computer."
    Sends a 6-digit code to the registered email address.
    """
    key_raw = normalise_key(body.key)

    if not validate_key_hmac(key_raw):
        return JSONResponse({"success": False,
                             "message": "Invalid key."})

    record = db_module.get_license(db, key_raw)
    if record is None or record.is_revoked:
        return JSONResponse({"success": False,
                             "message": "Key not found. Contact support."})

    if not record.is_activated:
        return JSONResponse({"success": False,
                             "message": "This key has not been activated yet — "
                                        "you can activate it directly."})

    code   = db_module.create_transfer_code(db, key_raw)
    masked = _mask_email(record.email)
    send_transfer_code_email(record.email, record.customer_name, code)

    log.info("Transfer code sent for %s... to %s", key_raw[:4], masked)
    return JSONResponse({"success": True,
                         "masked_email": masked,
                         "message": f"A 6-digit verification code has been "
                                    f"sent to {masked}. It expires in 15 minutes."})


# ── Machine transfer — step 2: confirm with the code ─────────────────────────

@app.post("/api/transfer/confirm")
@limiter.limit("10/minute")
async def transfer_confirm(request: Request, body: TransferConfirmBody,
                           db: Session = Depends(get_db)):
    """
    Validates the code, resets the hardware binding, and activates on
    the new machine. Also logs a support ticket for the record.
    """
    key_raw     = normalise_key(body.key)
    code        = body.code.strip()
    fingerprint = body.fingerprint.strip()

    record = db_module.get_license(db, key_raw)
    if record is None:
        return JSONResponse({"success": False,
                             "message": "Key not found."})

    if not db_module.verify_transfer_code(db, key_raw, code):
        return JSONResponse({"success": False,
                             "message": "That code is incorrect or has expired.\n"
                                        "Please click 'Send new code' and try again."})

    db_module.activate_license(db, record, fingerprint)
    ticket_ref = db_module.create_support_ticket(
        db,
        license_key=key_raw,
        ticket_type="new_machine",
        description="Customer transferred license to a new machine via email verification.",
        customer_email=record.email)

    log.info("Transfer confirmed: %s... → ticket %s", key_raw[:4], ticket_ref)
    return JSONResponse({"success": True,
                         "message": "Your license has been transferred and activated "
                                    "on this computer."})


# ── Component-replacement support ticket ─────────────────────────────────────

@app.post("/api/support/ticket")
@limiter.limit("5/hour")
async def support_ticket(request: Request, body: SupportTicketBody,
                         db: Session = Depends(get_db)):
    """
    Logs a manual transfer request for customers who replaced a component
    (motherboard, hard drive) and whose hardware fingerprint has changed.
    """
    key_raw        = normalise_key(body.key)
    record         = db_module.get_license(db, key_raw)
    customer_email = record.email if record else ""

    ticket_ref = db_module.create_support_ticket(
        db,
        license_key=key_raw,
        ticket_type=body.ticket_type,
        component=body.component,
        description=body.description,
        customer_email=customer_email)

    send_support_notification(
        ticket_ref=ticket_ref,
        license_key=key_raw,
        ticket_type=body.ticket_type,
        component=body.component,
        description=body.description,
        customer_email=customer_email)

    log.info("Support ticket %s created (%s)", ticket_ref, body.ticket_type)
    return JSONResponse({"success": True,
                         "ticket_ref": ticket_ref,
                         "message": (f"Support ticket {ticket_ref} has been logged.\n\n"
                                     f"Please also send an email to support@ggengage.com.au "
                                     f"— your email client will open pre-filled.\n\n"
                                     f"We aim to process transfer requests within "
                                     f"1 business day.")})


# ── Admin endpoints ───────────────────────────────────────────────────────────

@app.get("/api/admin/licenses", dependencies=[Depends(_require_admin)])
def admin_list(db: Session = Depends(get_db)):
    records = db.query(db_module.License).order_by(
        db_module.License.created_at.desc()).all()
    return [
        {"key": format_key(r.key), "email": r.email, "name": r.customer_name,
         "amount": f"{r.amount_paid_cents / 100:.2f} {r.currency.upper()}",
         "payment_id": r.payment_id, "activated": r.is_activated,
         "activated_at": r.activated_at.isoformat() if r.activated_at else None,
         "revoked": r.is_revoked,
         "created_at": r.created_at.isoformat()}
        for r in records
    ]


@app.get("/api/admin/tickets", dependencies=[Depends(_require_admin)])
def admin_tickets(db: Session = Depends(get_db)):
    tickets = db.query(db_module.SupportTicket).order_by(
        db_module.SupportTicket.created_at.desc()).all()
    return [
        {"ref": t.ticket_ref, "type": t.ticket_type, "key": t.license_key,
         "component": t.component, "description": t.description,
         "email": t.customer_email, "status": t.status,
         "created": t.created_at.isoformat()}
        for t in tickets
    ]


@app.post("/api/admin/revoke/{key}", dependencies=[Depends(_require_admin)])
def admin_revoke(key: str, db: Session = Depends(get_db)):
    record = db_module.get_license(db, normalise_key(key))
    if record is None:
        raise HTTPException(404, "Key not found")
    record.is_revoked = True
    db.commit()
    return {"revoked": True}


@app.post("/api/admin/transfer/{key}", dependencies=[Depends(_require_admin)])
def admin_transfer(key: str, db: Session = Depends(get_db)):
    record = db_module.get_license(db, normalise_key(key))
    if record is None:
        raise HTTPException(404, "Key not found")
    record.is_activated         = False
    record.hardware_fingerprint = None
    record.activated_at         = None
    db.commit()
    return {"transferred": True, "key": format_key(record.key)}


@app.post("/api/admin/generate", dependencies=[Depends(_require_admin)])
def admin_generate(email: str, name: str = "", db: Session = Depends(get_db)):
    raw = generate_key()
    db_module.create_license(db, key=raw, email=email,
                             customer_name=name, payment_id="manual")
    send_license_email(email, name, format_key(raw))
    return {"key": format_key(raw), "email": email}


@app.post("/api/admin/resolve/{ticket_ref}", dependencies=[Depends(_require_admin)])
def admin_resolve_ticket(ticket_ref: str, db: Session = Depends(get_db)):
    ticket = db.query(db_module.SupportTicket).filter(
        db_module.SupportTicket.ticket_ref == ticket_ref).first()
    if ticket is None:
        raise HTTPException(404, "Ticket not found")
    ticket.status      = "resolved"
    ticket.resolved_at = datetime.now(timezone.utc)
    db.commit()
    return {"resolved": True}


@app.get("/health")
def health():
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat()}
