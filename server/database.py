"""
SQLAlchemy database models and session management.
Supports SQLite (development) and PostgreSQL (production via DATABASE_URL env var).
"""

import os
from datetime import datetime, timezone

from sqlalchemy import (Boolean, Column, DateTime, Integer, String,
                        create_engine, text)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

# SQLite for dev; set DATABASE_URL for PostgreSQL in production
_DB_URL = os.environ.get(
    "DATABASE_URL",
    "sqlite:////data/licenses.db" if os.path.isdir("/data")
    else "sqlite:///./licenses.db")

# Render.com provides postgres:// URLs; SQLAlchemy needs postgresql://
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
    payment_id           = Column(String, nullable=True)   # Stripe payment/session ID
    payment_gateway      = Column(String, default="stripe")
    amount_paid_cents    = Column(Integer, default=0)
    currency             = Column(String, default="aud")
    created_at           = Column(DateTime,
                                  default=lambda: datetime.now(timezone.utc))
    activated_at         = Column(DateTime, nullable=True)
    hardware_fingerprint = Column(String, nullable=True)   # SHA-256, bound at activation
    is_activated         = Column(Boolean, default=False)
    is_revoked           = Column(Boolean, default=False)  # admin can revoke


def init_db() -> None:
    Base.metadata.create_all(bind=_engine)


def get_db():
    """FastAPI dependency that yields a DB session and closes it after."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Convenience helpers used by main.py ──────────────────────────────────────

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
        License.key == key.upper().replace("-", "")
    ).first()


def activate_license(db: Session, record: License,
                     fingerprint: str) -> None:
    record.is_activated         = True
    record.activated_at         = datetime.now(timezone.utc)
    record.hardware_fingerprint = fingerprint
    db.commit()
