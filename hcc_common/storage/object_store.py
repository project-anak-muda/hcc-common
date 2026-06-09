from __future__ import annotations

import io
import boto3
import logging

from typing import Optional
from functools import lru_cache
from datetime import datetime
from botocore.exceptions import ClientError
from botocore.client import Config as BotoConfig

from hcc_common.db import utcnow
from hcc_common.config import get_settings


log = logging.getLogger(__name__)

def raw_frame_key(camera_name: str,) -> str:
    ts = utcnow()
    return (
        f"raw/{camera_name}/{ts:%Y-%m-%d}/{ts:%H}/"
        f"{ts:%Y%m%dT%H%M%S}_{ts.microsecond:06d}.jpg"
    )

def dataset_keys(model_name: str, stem: str) -> tuple[str, str]:
    return (
        f"{model_name}/images/{stem}.jpg",
        f"{model_name}/labels/{stem}.txt",
    )

class ObjectStore:
    def __init__(self) -> None:
        s = get_settings().storage
        self._s = s
        self.client = boto3.client(
            "s3",
            endpoint_url=s.endpoint or None,
            region_name=s.region,
            aws_access_key_id=s.access_key,
            aws_secret_access_key=s.secret_key,
            use_ssl=s.use_ssl,
            config=BotoConfig(signature_version="s3v4", s3={"addressing_style": "path"}),
        )

    @property
    def buckets(self) -> dict[str, str]:
        return {
            "raw": self._s.bucket_raw,
            "events": self._s.bucket_events,
            "datasets": self._s.bucket_datasets,
            "models": self._s.bucket_models,
        }

    def ensure_buckets(self) -> None:
        for bucket in self.buckets.values():
            try:
                self.client.head_bucket(Bucket=bucket)
            except ClientError:
                log.info("Creating bucket %s", bucket)
                self.client.create_bucket(Bucket=bucket)
        self._apply_raw_lifecycle()

    def _apply_raw_lifecycle(self) -> None:
        """Auto-expire raw frames after the retention window (backstop is janitor)."""
        days = self._s.raw_retention_days
        try:
            self.client.put_bucket_lifecycle_configuration(
                Bucket=self._s.bucket_raw,
                LifecycleConfiguration={
                    "Rules": [
                        {
                            "ID": f"expire-raw-{days}d",
                            "Filter": {"Prefix": "raw/"},
                            "Status": "Enabled",
                            "Expiration": {"Days": days},
                        }
                    ]
                },
            )
            log.info("Applied %d-day lifecycle to %s", days, self._s.bucket_raw)
        except ClientError as e:
            log.warning("Could not apply lifecycle rule (janitor will handle): %s", e)

    def put_bytes(
        self,
        bucket: str,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        self.client.put_object(Bucket=bucket, Key=key, Body=data, ContentType=content_type)
        return key

    def put_jpeg(self, bucket: str, key: str, data: bytes) -> str:
        return self.put_bytes(bucket, key, data, content_type="image/jpeg")

    def put_file(self, bucket: str, key: str, path: str, content_type: Optional[str] = None) -> str:
        extra = {"ContentType": content_type} if content_type else None
        self.client.upload_file(path, bucket, key, ExtraArgs=extra)
        return key

    def get_bytes(self, bucket: str, key: str) -> bytes:
        obj = self.client.get_object(Bucket=bucket, Key=key)
        return obj["Body"].read()

    def download_file(self, bucket: str, key: str, dest_path: str) -> None:
        self.client.download_file(bucket, key, dest_path)

    def exists(self, bucket: str, key: str) -> bool:
        from botocore.exceptions import ClientError

        try:
            self.client.head_object(Bucket=bucket, Key=key)
            return True
        except ClientError:
            return False

    def list_keys(self, bucket: str, prefix: str = "") -> list[str]:
        keys: list[str] = []
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            keys.extend(o["Key"] for o in page.get("Contents", []))
        return keys

    def delete_prefix(self, bucket: str, prefix: str) -> int:
        """Used by the janitor to purge expired hourly buckets."""
        deleted = 0
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            objs = [{"Key": o["Key"]} for o in page.get("Contents", [])]
            if objs:
                self.client.delete_objects(Bucket=bucket, Delete={"Objects": objs})
                deleted += len(objs)
        return deleted

    def presigned_url(self, bucket: str, key: str, expires: int = 3600) -> str:
        return self.client.generate_presigned_url(
            "get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=expires
        )

@lru_cache
def get_object_store() -> ObjectStore:
    return ObjectStore()