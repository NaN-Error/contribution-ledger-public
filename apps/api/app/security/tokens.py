"""256-bit opaque bearer tokens, purpose-separated hashes, and session-bound CSRF."""
import hashlib
import hmac
import re
import secrets
from datetime import datetime, timezone


def now() -> datetime:
    return datetime.now(timezone.utc)


def utc(value: datetime) -> datetime:
    # SQLite's test-only driver drops timezone information; PostgreSQL does not.
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def new_token() -> str:
    return secrets.token_urlsafe(32)


def valid_token(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9_-]{43}", value))


def token_hash(value: str, purpose: str) -> str:
    return hashlib.sha256(f"{purpose}:v1:{value}".encode("utf-8")).hexdigest()


def csrf_for(session_token: str) -> str:
    # A synchronizer value derived from a server-issued session secret. Only its
    # session hash is retained by the server. This is NOT a readable token cookie.
    return hmac.new(session_token.encode("ascii"), b"contribution-ledger:csrf:v1", hashlib.sha256).hexdigest()
