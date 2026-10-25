"""Private S3-compatible adapter. Tested with a stubbed boto3 client, not live S3.

No ACLs, presigned URLs, public bucket creation, or client-controlled endpoints.
Configure a dedicated private bucket/least-privilege credentials outside the app.
Server-side encryption and backup/version lifecycle remain operator duties.
"""
from hashlib import sha256
from io import BytesIO
from typing import BinaryIO
from uuid import UUID, uuid4
from botocore.exceptions import BotoCoreError, ClientError
from app.storage.contracts import (ObjectReference, ObjectMissing, ObjectCorrupt,
    StorageUnavailable, read_bounded)


class S3ObjectStorage:
    backend = 's3'
    def __init__(self, client, bucket: str, prefix: str = 'evidence-v1'):
        import re
        if not re.fullmatch(r'[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]', bucket) or '..' in bucket:
            raise ValueError('Use an explicit dedicated bucket name.')
        if not re.fullmatch(r'[a-z0-9-]{1,40}', prefix): raise ValueError('Invalid object prefix.')
        self.client, self.bucket, self.prefix = client, bucket, prefix

    def _key(self, ref: ObjectReference) -> str:
        return f'{self.prefix}/{ref.workspace_id}/{ref.object_id}'

    def _failure(self, exc):
        if isinstance(exc, ClientError) and str(exc.response.get('Error', {}).get('Code')) in {'404', 'NoSuchKey', 'NotFound'}:
            raise ObjectMissing('Stored object is unavailable.') from None
        raise StorageUnavailable('Object storage is unavailable.') from None

    def put(self, workspace_id: UUID, stream: BinaryIO, maximum_bytes: int) -> ObjectReference:
        data = read_bounded(stream, maximum_bytes)
        ref = ObjectReference(workspace_id, uuid4(), sha256(data).hexdigest(), len(data))
        try:
            self.client.put_object(Bucket=self.bucket, Key=self._key(ref), Body=data,
                ContentType='application/octet-stream', ContentLength=len(data),
                IfNoneMatch='*', Metadata={'sha256': ref.sha256})
        except (BotoCoreError, ClientError) as exc: self._failure(exc)
        return ref

    def check(self, ref: ObjectReference) -> None:
        try: result = self.client.head_object(Bucket=self.bucket, Key=self._key(ref))
        except (BotoCoreError, ClientError) as exc: self._failure(exc)
        if result.get('ContentLength') != ref.size_bytes or result.get('Metadata', {}).get('sha256') != ref.sha256:
            raise ObjectCorrupt('Stored object metadata does not match.')

    def open(self, ref: ObjectReference) -> BinaryIO:
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=self._key(ref))
            body = response['Body']
            try:
                if response.get('ContentLength') != ref.size_bytes:
                    raise ObjectCorrupt('Stored object does not match its recorded size.')
                data = body.read(ref.size_bytes + 1)
            finally: body.close()
        except (BotoCoreError, ClientError) as exc: self._failure(exc)
        if len(data) != ref.size_bytes or sha256(data).hexdigest() != ref.sha256:
            raise ObjectCorrupt('Stored object failed its integrity check.')
        return BytesIO(data)

    def delete(self, ref: ObjectReference) -> None:
        try: self.client.delete_object(Bucket=self.bucket, Key=self._key(ref))
        except (BotoCoreError, ClientError) as exc: self._failure(exc)
