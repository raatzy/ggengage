"""
SQLAlchemy database models and session management.
Supports SQLite (development) and PostgreSQL (production via DATABASE_URL env var).
"""

import os
import secrets as _secrets
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import (Boolean, Column, DateTime, Integer, String,
                        create_engine)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

_DB_URL = os.environ.get(
    "DATABASE_URL",
    "sqlite:////data/licenses.db" if os.path.isdir("/data")
    else "sqlite:///./licenses.db")

if _DB_URL.startswith("postgres://"):
    _DB_URL = _DB_URL.replace("postgres://", "postgresql://", 1)

_engine = create_engine(
    _DB_URL,
    connect_args={"check_same_thread": False} if "sqlite" in _DB_URL else {})

SessionLocal = sessionmaker(bind=_engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


class License(Base):
    __tablename__ = "licenses"
    id                   = Column(Integer, primary_key=True, index=True)
    key                  = Column(String, unique=True, nullable=False, index=True)
    email                = Column(String, nullable=False)
    customer_name        = Column(String, default="")
    payment_id           = Column(String, nullable=True)
    payment_gateway      = Column(String, default="stripe")
    amount_paid_cents    = Column(Integer, default=0)
    currency             = Column(String, default="aud")
    created_at           = Column(DateTime,
                                  default=lambda: datetime.now(timezone.utc))
    activated_at         = Column(DateTime, nullable=True)
    hardware_fingerprint = Column(String, nullable=True)
    is_activated         = Column(Boolean, default=False)
    is_revoked           = Column(Boolean, default=False)


class TransferCode(Base):
    """One-time 6-digit codes emailed to customers for self-service machine transfers."""
    __tablename__ = "transfer_codes"
    id          = Column(Integer, primary_key=True)
    license_key = Column(String, nullable=False, index=True)
    code        = Column(String(6), nullable=False)
    expires_at  = Column(DateTime, nullable=False)
    used        = Column(Boolean, default=False)
    created_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class SupportTicket(Base):
    """Logged for every transfer or component-replacement request."""
    __tablename__ = "support_tickets"
    id             = Column(Integer, primary_key=True)
    ticket_ref     = Column(String(20), unique=True, nullable=False, index=True)
    license_key    = Column(String, index=True, nullable=True)
    ticket_type    = Column(String, nullable=False)  # "new_machine" | "component_replacement"
    component      = Column(String, nullable=True)   # "Hard Drive", "Motherboard", etc.
    description    = Column(String, nullable=True)
    customer_email = Column(String, nullable=True)
    status         = Column(String, default="open")  # open | resolved
    created_at     = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    resolved_at    = Column(DateTime, nullable=True)


def init_db() -> None:
    Base.metadata.create_all(bind=_engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── License helpers ───────────────────────────────────────────────────────────

def create_license(db: Session, *, key: str, email: str,
                   customer_name: str = "", payment_id: str = "",
                   amount_paid_cents: int = 0, currency: str = "aud") -> License:
    record = License(key=key, email=email, customer_name=customer_name,
                     payment_id=payment_id, amount_paid_cents=amount_paid_cents,
                     currency=currency)
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def get_license(db: Session, key: str) -> License | None:
    return db.query(License).filter(
        License.key == key.upper().replace("-", "")).first()


def activate_license(db: Session, record: License, fingerprint: str) -> None:
    record.is_activated         = True
    record.activated_at         = datetime.now(timezone.utc)
    record.hardware_fingerprint = fingerprint
    db.commit()


# ── Transfer-code helpers ─────────────────────────────────────────────────────

def create_transfer_code(db: Session, key: str) -> str:
    """
    Generate a fresh 6-digit code valid for 15 minutes.
    Any previous unused codes for this key are deleted first.
    """
    db.query(TransferCode).filter(TransferCode.license_key == key).delete()
    db.commit()
    code    = f"{_secrets.randbelow(1_000_000):06d}"
    expiry  = datetime.now(timezone.utc) + timedelta(minutes=15)
    db.add(TransferCode(license_key=key, code=code, expires_at=expiry))
    db.commit()
    return code


def verify_transfer_code(db: Session, key: str, code: str) -> bool:
    """Validate code and mark it used. Returns False if invalid or expired."""
    record = db.query(TransferCode).filter(
        TransferCode.license_key == key,
        TransferCode.code        == code,
        TransferCode.used        == False,
    ).first()
    if record is None:
        return False
    # Handle both naive and aware datetimes
    expiry = record.expires_at
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    if expiry < datetime.now(timezone.utc):
        return False
    record.used = True
    db.commit()
    return True


# ── Support-ticket helpers ────────────────────────────────────────────────────

def create_support_ticket(db: Session, *, license_key: str, ticket_type: str,
                          component: str = "", description: str = "",
                          customer_email: str = "") -> str:
    """Create a ticket and return its human-readable reference (TKT-YYYYMMDD-XXXX)."""
    ref = f"TKT-{date.today().strftime('%Y%m%d')}-{_secrets.token_hex(2).upper()}"
    db.add(SupportTicket(
        ticket_ref=ref, license_key=license_key, ticket_type=ticket_type,
        component=component, description=description,
        customer_email=customer_email))
    db.commit()
    return ref
