"""Read-only mounted secret adapter. No secret value is returned by application APIs."""
import os
from pathlib import Path
from typing import Protocol


class SecretUnavailable(Exception):
    def __init__(self):
        super().__init__('The operator-provisioned credential is unavailable or invalid.')


class SecretStore(Protocol):
    def read(self, name: str) -> bytes: ...


class MountedSecretStore:
    """Only fixed names; reject links, directories, oversized and world-writable files.

    Parent-directory/volume permissions and backups remain the operator's duty.
    A mount alone is not a guarantee against privileged host administrators.
    """
    allowed_names = frozenset({'github-private-key.pem', 'github-client-secret', 'github-webhook-secret'})

    def __init__(self, root: str):
        self.root = Path(root).absolute()

    def read(self, name: str) -> bytes:
        if name not in self.allowed_names:
            raise SecretUnavailable()
        path = self.root / name
        try:
            if self.root.is_symlink() or path.is_symlink():
                raise SecretUnavailable()
            flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0)
            fd = os.open(path, flags)
            with os.fdopen(fd, 'rb') as handle:
                import stat
                info = os.fstat(handle.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_size > 16384 or info.st_mode & stat.S_IWOTH:
                    raise SecretUnavailable()
                data = handle.read(16385)
            if not data.strip() or len(data) > 16384:
                raise SecretUnavailable()
            return data.strip()
        except (OSError, ValueError):
            raise SecretUnavailable() from None
