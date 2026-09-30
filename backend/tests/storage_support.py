"""S09 測試共用：測試資料與 MinIO 清理（直接使用 boto3，不經過受測的 S3Storage）。"""

import boto3

from app.config import load_settings

# 最小的 PNG 檔頭加上任意內容：驗證位元組完全相同即可
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + bytes(range(256)) * 4


def s3_cleanup(object_keys: list[str]) -> None:
    if not object_keys:
        return
    s = load_settings(env_file=None)
    client = boto3.client(
        "s3", endpoint_url=s.s3_endpoint_url, aws_access_key_id=s.s3_access_key_id,
        aws_secret_access_key=s.s3_secret_access_key.get_secret_value(), region_name=s.s3_region,
    )
    client.delete_objects(Bucket=s.s3_bucket, Delete={"Objects": [{"Key": k} for k in object_keys]})
