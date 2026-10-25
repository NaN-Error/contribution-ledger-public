"""Private UUID-addressed local blobs, immutable writes and verified reads.

The root must be operator-owned and outside the webroot. No attacker-controlled
path components, original filenames or symlink targets are used for storage.
OS administrators remain trusted; this is not a sandbox against the operator.
"""
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from typing import BinaryIO
from uuid import UUID, uuid4
import os
import stat
from app.storage.contracts import (ObjectReference, ObjectMissing, ObjectCorrupt,
    StorageUnavailable, read_bounded)


class LocalObjectStorage:
    backend = 'local'

    def __init__(self, root: Path):
        self.root = Path(root).absolute()

    def _directory(self, workspace_id: UUID, *, create=False) -> Path:
        if not isinstance(workspace_id, UUID): raise ValueError('A workspace UUID is required.')
        # Reject existing symlink ancestors rather than silently resolving them.
        for part in [*reversed(self.root.parents), self.root]:
            if part.is_symlink(): raise StorageUnavailable('Object storage is unavailable.')
        if create: self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        directory = self.root / str(workspace_id)
        if directory.is_symlink(): raise StorageUnavailable('Object storage is unavailable.')
        if create: directory.mkdir(exist_ok=True, mode=0o700)
        return directory

    def _path(self, reference: ObjectReference) -> Path:
        return self._directory(reference.workspace_id) / str(reference.object_id)

    def put(self, workspace_id: UUID, stream: BinaryIO, maximum_bytes: int) -> ObjectReference:
        data = read_bounded(stream, maximum_bytes)
        reference = ObjectReference(workspace_id, uuid4(), sha256(data).hexdigest(), len(data))
        path = None
        created = False
        try:
            path = self._directory(workspace_id, create=True) / str(reference.object_id)
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0)
            fd = os.open(path, flags, 0o600)
            created = True
            with os.fdopen(fd, 'wb') as target:
                target.write(data); target.flush(); os.fsync(target.fileno())
            return reference
        except OSError:
            # This UUID is unique to this attempt; never remove an existing collision.
            if created and path and path.exists() and not path.is_symlink():
                # Cleanup is best effort; an interrupted write is never referenced by DB.
                try: path.unlink()
                except OSError: pass
            raise StorageUnavailable('Object storage is unavailable.') from None

    def check(self, reference: ObjectReference) -> None:
        try:
            info = self._path(reference).lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise ObjectCorrupt('Stored object is not a private regular file.')
            if info.st_size != reference.size_bytes:
                raise ObjectCorrupt('Stored object does not match its recorded size.')
        except FileNotFoundError: raise ObjectMissing('Stored object is unavailable.') from None
        except OSError: raise StorageUnavailable('Object storage is unavailable.') from None

    def open(self, reference: ObjectReference) -> BinaryIO:
        self.check(reference)
        try:
            flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
            with os.fdopen(os.open(self._path(reference), flags), 'rb') as source:
                info = os.fstat(source.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size != reference.size_bytes:
                    raise ObjectCorrupt('Stored object changed during access.')
                data = source.read(reference.size_bytes + 1)
        except FileNotFoundError: raise ObjectMissing('Stored object is unavailable.') from None
        except OSError: raise StorageUnavailable('Object storage is unavailable.') from None
        if len(data) != reference.size_bytes or sha256(data).hexdigest() != reference.sha256:
            raise ObjectCorrupt('Stored object failed its integrity check.')
        # Bounded verified bytes avoid a time-of-check/time-of-stream replacement.
        return BytesIO(data)

    def delete(self, reference: ObjectReference) -> None:
        try:
            path = self._path(reference)
            if path.is_symlink(): raise StorageUnavailable('Object storage is unavailable.')
            path.unlink(missing_ok=True)
        except OSError: raise StorageUnavailable('Object storage is unavailable.') from None
