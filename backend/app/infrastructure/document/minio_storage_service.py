import logging
import io
from datetime import timedelta
from minio import Minio
from minio.error import S3Error
from app.domain.document.interfaces import IStorageService

logger = logging.getLogger(__name__)


class MinioStorageService(IStorageService):
    """S3-compatible storage via MinIO (ADR-006).

    Bucket creation and initialization is handled by infra_init.py at startup.
    This service only performs object-level operations.
    """

    def __init__(self, get_minio_fn):
        self.get_minio_fn = get_minio_fn

    def get_presigned_upload_url(
        self, bucket_name: str, object_name: str, expires_in_sec: int = 3600
    ) -> str:
        client: Minio = self.get_minio_fn()
        return client.presigned_put_object(
            bucket_name, object_name, expires=timedelta(seconds=expires_in_sec)
        )

    def get_presigned_download_url(
        self, bucket_name: str, object_name: str, expires_in_sec: int = 3600
    ) -> str:
        client: Minio = self.get_minio_fn()
        return client.presigned_get_object(
            bucket_name, object_name, expires=timedelta(seconds=expires_in_sec)
        )

    def upload_file(
        self, bucket_name: str, object_name: str, file_data: bytes, content_type: str
    ) -> None:
        client: Minio = self.get_minio_fn()
        stream = io.BytesIO(file_data)
        client.put_object(
            bucket_name=bucket_name,
            object_name=object_name,
            data=stream,
            length=len(file_data),
            content_type=content_type,
        )
        logger.info(
            "Uploaded '%s' to bucket '%s' (%d bytes).",
            object_name,
            bucket_name,
            len(file_data),
        )

    def delete_file(self, bucket_name: str, object_name: str) -> None:
        client: Minio = self.get_minio_fn()
        client.remove_object(bucket_name, object_name)
        logger.info("Deleted '%s' from bucket '%s'.", object_name, bucket_name)

    def file_exists(self, bucket_name: str, object_name: str) -> bool:
        client: Minio = self.get_minio_fn()
        try:
            client.stat_object(bucket_name, object_name)
            return True
        except S3Error as exc:
            if exc.code == "NoSuchKey":
                return False
            raise
