import logging
import io
from datetime import timedelta
from minio import Minio
from minio.error import S3Error
from app.domain.document.interfaces import IStorageService

logger = logging.getLogger(__name__)


class MinioStorageService(IStorageService):
    def __init__(self, get_minio_fn):
        self.get_minio_fn = get_minio_fn
        # We assume the default bucket for documents is 'documents'
        self.default_bucket = "documents"
        self._ensure_bucket(self.default_bucket)

    def _ensure_bucket(self, bucket_name: str):
        client: Minio = self.get_minio_fn()
        try:
            if not client.bucket_exists(bucket_name):
                client.make_bucket(bucket_name)
                logger.info(f"Created MinIO bucket: {bucket_name}")
        except S3Error as e:
            logger.error(f"Error checking/creating bucket {bucket_name}: {e}")

    def get_presigned_upload_url(self, bucket_name: str, object_name: str, expires_in_sec: int = 3600) -> str:
        client: Minio = self.get_minio_fn()
        return client.presigned_put_object(bucket_name, object_name, expires=timedelta(seconds=expires_in_sec))

    def get_presigned_download_url(self, bucket_name: str, object_name: str, expires_in_sec: int = 3600) -> str:
        client: Minio = self.get_minio_fn()
        return client.presigned_get_object(bucket_name, object_name, expires=timedelta(seconds=expires_in_sec))

    def upload_file(self, bucket_name: str, object_name: str, file_data: bytes, content_type: str) -> None:
        client: Minio = self.get_minio_fn()
        stream = io.BytesIO(file_data)
        client.put_object(
            bucket_name=bucket_name,
            object_name=object_name,
            data=stream,
            length=len(file_data),
            content_type=content_type,
        )

    def delete_file(self, bucket_name: str, object_name: str) -> None:
        client: Minio = self.get_minio_fn()
        client.remove_object(bucket_name, object_name)

    def file_exists(self, bucket_name: str, object_name: str) -> bool:
        client: Minio = self.get_minio_fn()
        try:
            client.stat_object(bucket_name, object_name)
            return True
        except S3Error as e:
            if e.code == "NoSuchKey":
                return False
            raise e
