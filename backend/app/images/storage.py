from __future__ import annotations

import os

import boto3
from botocore.client import Config


def _make_client():
    return boto3.client(
        "s3",
        endpoint_url=os.environ["STORAGE_ENDPOINT_URL"],
        aws_access_key_id=os.environ["STORAGE_ACCESS_KEY"],
        aws_secret_access_key=os.environ["STORAGE_SECRET_KEY"],
        # s3v4 signatures are required by R2 and most S3-compatible providers.
        # Neon Object Storage requires path-style addressing; virtual-hosted style
        # (the boto3 default) produces 403s against their endpoint.
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        region_name=os.environ.get("STORAGE_REGION", "auto"),
    )


def upload(key: str, data: bytes, content_type: str = "image/webp") -> str:
    """
    Upload bytes to S3-compatible object storage and return the public URL.

    Required env vars:
        STORAGE_ENDPOINT_URL     e.g. https://<account>.r2.cloudflarestorage.com
        STORAGE_BUCKET           bucket name
        STORAGE_ACCESS_KEY       access key ID
        STORAGE_SECRET_KEY       secret access key
        STORAGE_PUBLIC_URL_BASE  public base URL for the bucket (no trailing slash)

    Optional:
        STORAGE_REGION           defaults to "auto" (correct for Cloudflare R2)
    """
    _make_client().put_object(
        Bucket=os.environ["STORAGE_BUCKET"],
        Key=key,
        Body=data,
        ContentType=content_type,
    )
    base = os.environ["STORAGE_PUBLIC_URL_BASE"].rstrip("/")
    return f"{base}/{key}"


def delete_keys(keys: list[str]) -> None:
    """Delete a batch of objects from storage. Called when an image is removed."""
    if not keys:
        return
    _make_client().delete_objects(
        Bucket=os.environ["STORAGE_BUCKET"],
        Delete={"Objects": [{"Key": k} for k in keys]},
    )
