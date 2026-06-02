#!/usr/bin/env python3
"""
GG Engage Photo Processor — Developer License Key Generator
============================================================
DO NOT DISTRIBUTE THIS FILE. Keep it private on your own machine.
It contains the same secrets as the compiled application.

Usage:
    python keygen.py              # generate 1 key
    python keygen.py 10           # generate 10 keys
    python keygen.py --validate ABCD-EF01-2345-6789

Each key works on any machine (machine-binding is handled by the
encrypted storage layer inside the app, not by the key itself).
A customer who reinstalls Windows can re-enter the same key.
"""

import argparse
import hashlib
import hmac
import secrets
import sys

# Must exactly match _LIC_SECRET in process_photos.py
_SECRET = b"GGEngagePhotoProc-k9xP2025#mR7"


def generate_key() -> str:
    """Generate one valid 16-hex-char license key (XXXX-XXXX-XXXX-XXXX)."""
    payload  = secrets.token_hex(4).upper()         # 8 random hex chars
    sig      = hmac.new(_SECRET, payload.encode(),
                        hashlib.sha256).hexdigest()[:8].upper()
    combined = payload + sig
    return f"{combined[0:4]}-{combined[4:8]}-{combined[8:12]}-{combined[12:16]}"


def validate_key(key: str) -> bool:
    k = key.strip().upper().replace("-", "").replace(" ", "")
    if len(k) != 16:
        return False
    payload  = k[:8]
    expected = hmac.new(_SECRET, payload.encode(),
                        hashlib.sha256).hexdigest()[:8].upper()
    return k[8:] == expected


def main():
    parser = argparse.ArgumentParser(
        description="Generate or validate GG Engage Photo Processor license keys.")
    parser.add_argument("count", nargs="?", type=int, default=1,
                        help="Number of keys to generate (default: 1)")
    parser.add_argument("--validate", metavar="KEY",
                        help="Validate an existing key and exit")
    args = parser.parse_args()

    if args.validate:
        ok = validate_key(args.validate)
        print(f"{'VALID  ' if ok else 'INVALID'}  {args.validate}")
        sys.exit(0 if ok else 1)

    if not 1 <= args.count <= 500:
        print("Count must be between 1 and 500.", file=sys.stderr)
        sys.exit(1)

    for _ in range(args.count):
        print(generate_key())


if __name__ == "__main__":
    main()
