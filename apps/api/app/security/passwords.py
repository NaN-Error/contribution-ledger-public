from functools import lru_cache
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError


@lru_cache
def password_hasher() -> PasswordHasher:
    # Explicit Argon2id parameters: 64 MiB, 3 iterations, 4 lanes. No runtime
    # setting permits a production caller to silently weaken these parameters.
    return PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)


@lru_cache
def dummy_hash() -> str:
    return password_hasher().hash("Synthetic timing equalization; never a login password")


def hash_password(password: str) -> str:
    return password_hasher().hash(password)


def verify_password(encoded: str | None, password: str) -> bool:
    try:
        matches = password_hasher().verify(encoded or dummy_hash(), password)
        return bool(encoded and matches)
    except (VerificationError, InvalidHashError):
        return False
