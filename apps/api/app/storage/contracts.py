"""Private object-store contract. All references originate in trusted database rows."""
from dataclasses import dataclass
from typing import BinaryIO, Protocol
from uuid import UUID
import re

MAX_OBJECT_BYTES = 5 * 1024 * 1024  # Also bounds regenerated image previews.


class StorageError(Exception):
    """Fixed safe errors; never expose a local path, endpoint or credential."""


class ObjectMissing(StorageError): pass
class ObjectCorrupt(StorageError): pass
class StorageUnavailable(StorageError): pass
class ObjectTooLarge(StorageError): pass


@dataclass(frozen=True)
class ObjectReference:
    workspace_id: UUID
    object_id: UUID
    sha256: str
    size_bytes: int

    def __post_init__(self):
        if (not isinstance(self.workspace_id, UUID) or not isinstance(self.object_id, UUID)
            or not re.fullmatch(r'[0-9a-f]{64}', self.sha256)
            or type(self.size_bytes) is not int or not 1 <= self.size_bytes <= MAX_OBJECT_BYTES):
            raise ValueError('Invalid internal object reference.')


class ObjectStorage(Protocol):
    backend: str
    def put(self, workspace_id: UUID, stream: BinaryIO, maximum_bytes: int) -> ObjectReference: ...
    def open(self, reference: ObjectReference) -> BinaryIO: ...
    def check(self, reference: ObjectReference) -> None: ...
    def delete(self, reference: ObjectReference) -> None: ...


def read_bounded(stream: BinaryIO, maximum_bytes: int) -> bytes:
    if type(maximum_bytes) is not int or not 1 <= maximum_bytes <= MAX_OBJECT_BYTES:
        raise ValueError('Invalid object limit.')
    data = bytearray()
    while True:
        chunk = stream.read(min(65536, maximum_bytes - len(data) + 1))
        if not chunk: break
        if not isinstance(chunk, bytes): raise ValueError('A binary stream is required.')
        data.extend(chunk)
        if len(data) > maximum_bytes: raise ObjectTooLarge('Object exceeds its allowed size.')
    if not data: raise ValueError('Empty objects are not accepted.')
    return bytes(data)
