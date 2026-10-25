"""Database-backed fixed windows. Counts are committed before expensive authentication."""
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session
from app.auth.models import ThrottleBucket
from app.core.errors import ApiError
from app.security.tokens import now, token_hash


def reserve_attempts(db: Session, keys: list[tuple[str, int]], *, window_seconds: int = 900) -> None:
    window = int(now().timestamp()) // window_seconds
    dialect = db.get_bind().dialect.name
    if dialect not in {"postgresql", "sqlite"}:
        raise RuntimeError("Unsupported authentication database")
    insert = pg_insert if dialect == "postgresql" else sqlite_insert
    exceeded = False
    for key, limit in sorted(keys):
        statement = insert(ThrottleBucket).values(key_hash=token_hash(key, "throttle"), window=window, attempts=1)
        statement = statement.on_conflict_do_update(
            index_elements=[ThrottleBucket.key_hash, ThrottleBucket.window],
            set_={"attempts": ThrottleBucket.attempts + 1}).returning(ThrottleBucket.attempts)
        exceeded |= db.execute(statement).scalar_one() > limit
    # Keep the table bounded over time. A local trusted proxy shares one peer-IP
    # bucket; no untrusted X-Forwarded-For value is accepted to evade this limit.
    db.execute(delete(ThrottleBucket).where(ThrottleBucket.window < window - 2))
    db.commit()
    if exceeded:
        raise ApiError(429, "rate_limited", "Too many attempts. Wait up to 15 minutes before trying again.", retry_after=window_seconds)
