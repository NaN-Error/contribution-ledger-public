"""Account factors. TOTP seeds are AEAD ciphertext; recovery codes are hashes."""
from datetime import datetime
from uuid import UUID
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base

class Authenticator(Base):
    __tablename__ = "authenticators"
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    encrypted_secret: Mapped[str | None] = mapped_column(String(512))
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    must_enroll: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    enrollment_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_counter: Mapped[int] = mapped_column(Integer, nullable=False, default=-1, server_default="-1")
    recovery_hashes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
