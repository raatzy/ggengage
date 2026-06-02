#!/usr/bin/env python3
"""
GG Engage Photo Processor — Developer License Key Generator
============================================================
DO NOT DISTRIBUTE THIS FILE.
Keep it private; it contains the same secret as the compiled application.

Usage:
    python keygen.py            # generate one key
    python keygen.py 5          # generate 5 keys
    python keygen.py --validate ABCD-EF01-2345-6789

Each generated key is unique, validated offline, and never contacts a server.
"""

import argparse
import hashlib
import hmac
import secrets
import sys

# Must match _LICENSE_SECRET in process_photos.py exactly.
_SECRET = b"GGEngagePhotoProc-k9xP2025#mR7"


def generate_key() -> str:
    """Generate one valid 16-hex-char license key in XXXX-XXXX-XXXX-XXXX format."""
    payload  = secrets.token_hex(4).upper()          # 8 random hex chars
    sig      = hmac.new(_SECRET, payload.encode(),
                        hashlib.sha256).hexdigest()[:8].upper()
    combined = payload + sig                         # 16 hex chars
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
                        help="Validate an existing key instead of generating")
    args = parser.parse_args()

    if args.validate:
        ok = validate_key(args.validate)
        print(f"{'VALID' if ok else 'INVALID'}:  {args.validate}")
        sys.exit(0 if ok else 1)

    if args.count < 1 or args.count > 1000:
        print("Count must be between 1 and 1000.", file=sys.stderr)
        sys.exit(1)

    keys = [generate_key() for _ in range(args.count)]
    for k in keys:
        print(k)


if __name__ == "__main__":
    main()
