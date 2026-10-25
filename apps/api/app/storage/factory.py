from pathlib import Path
from app.core.config import Settings
from app.storage.contracts import ObjectStorage
from app.storage.local import LocalObjectStorage


def create_storage(settings: Settings) -> ObjectStorage:
    if settings.object_storage_backend == 'local':
        return LocalObjectStorage(Path(settings.object_storage_root))
    # Only operator config, never HTTP request values. Default deployment is local.
    import boto3
    from botocore.config import Config
    from app.storage.s3 import S3ObjectStorage
    client = boto3.client('s3', region_name=settings.s3_region,
        endpoint_url=settings.s3_endpoint, config=Config(connect_timeout=3, read_timeout=5,
            retries={'mode': 'standard', 'total_max_attempts': 2},
            s3={'addressing_style': 'path'}, signature_version='s3v4'))
    return S3ObjectStorage(client, settings.s3_bucket, settings.s3_prefix)
