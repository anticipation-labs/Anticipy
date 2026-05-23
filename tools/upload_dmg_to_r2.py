#!/usr/bin/env python3
"""
Upload a .dmg file to the Anticipy Cloudflare R2 bucket and print the public URL.

Usage:
    python3 tools/upload_dmg_to_r2.py /path/to/Anticipy_1.0.0_aarch64.dmg

Reads from environment (sourced from .env.local at the repo root):
    R2_ACCOUNT_ID        - Cloudflare account ID
    R2_ACCESS_KEY_ID     - R2 S3-compatible access key
    R2_SECRET_ACCESS_KEY - R2 S3-compatible secret
    R2_ENDPOINT          - S3-compatible endpoint URL for this account
    R2_BUCKET            - bucket name (anticipy-downloads)
    R2_PUBLIC_URL        - the bucket's public access URL (set after Omar
                           enables Public Access in the R2 bucket settings)

The script always uploads the file as Anticipy_1.0.0_aarch64.dmg in the bucket
root, sets Content-Type to application/x-apple-diskimage, and prints the
public URL when R2_PUBLIC_URL is configured. R2 object-level ACLs do not
exist; public readability is controlled by the bucket's Public Access setting
in the Cloudflare dashboard.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path


TARGET_KEY = "Anticipy_1.0.0_aarch64.dmg"
CONTENT_TYPE = "application/x-apple-diskimage"


def env_or_die(name: str) -> str:
    v = os.environ.get(name, "").strip()
    if not v:
        print(f"FATAL: required env var {name} not set. Source .env.local first.", file=sys.stderr)
        sys.exit(2)
    return v


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: upload_dmg_to_r2.py <path/to/Anticipy_1.0.0_aarch64.dmg>", file=sys.stderr)
        return 2

    src = Path(argv[1]).resolve()
    if not src.exists():
        print(f"FATAL: source file does not exist: {src}", file=sys.stderr)
        return 2
    if not src.is_file():
        print(f"FATAL: not a regular file: {src}", file=sys.stderr)
        return 2

    size_bytes = src.stat().st_size
    size_mb = size_bytes / (1024 * 1024)
    print(f"source: {src}")
    print(f"size:   {size_bytes:,} bytes ({size_mb:.1f} MB)")

    endpoint = env_or_die("R2_ENDPOINT")
    access_key = env_or_die("R2_ACCESS_KEY_ID")
    secret_key = env_or_die("R2_SECRET_ACCESS_KEY")
    bucket = env_or_die("R2_BUCKET")
    public_url_base = os.environ.get("R2_PUBLIC_URL", "").rstrip("/")

    try:
        import boto3  # type: ignore
        from botocore.config import Config  # type: ignore
    except ImportError:
        print("FATAL: boto3 not installed. Run: .verifier-venv/bin/pip install boto3", file=sys.stderr)
        return 2

    # R2's S3-compatible API expects the auth region to be 'auto'. Use
    # virtual-hosted addressing via the account-scoped endpoint URL.
    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="auto",
        config=Config(
            signature_version="s3v4",
            retries={"max_attempts": 4, "mode": "standard"},
            # 2+ GB files: bump the multipart threshold so boto3 streams instead
            # of buffering the whole file in memory.
            s3={"addressing_style": "path"},
        ),
    )

    print(f"uploading to s3://{bucket}/{TARGET_KEY} via {endpoint} ...")
    started = time.time()

    # Multipart upload for files over 64 MB.
    from boto3.s3.transfer import TransferConfig  # type: ignore
    transfer_config = TransferConfig(
        multipart_threshold=64 * 1024 * 1024,
        multipart_chunksize=64 * 1024 * 1024,
        max_concurrency=8,
        use_threads=True,
    )

    last_pct = -1

    def progress(bytes_amount: int) -> None:
        nonlocal last_pct
        progress.transferred = getattr(progress, "transferred", 0) + bytes_amount
        if size_bytes > 0:
            pct = int(progress.transferred * 100 / size_bytes)
            if pct != last_pct and pct % 5 == 0:
                last_pct = pct
                elapsed = time.time() - started
                rate_mbps = (progress.transferred / (1024 * 1024)) / max(elapsed, 0.001)
                print(f"  {pct:3d}%  {progress.transferred:,}/{size_bytes:,} bytes  {rate_mbps:.1f} MB/s")

    try:
        client.upload_file(
            Filename=str(src),
            Bucket=bucket,
            Key=TARGET_KEY,
            ExtraArgs={
                "ContentType": CONTENT_TYPE,
                # Cache for an hour; new builds bump the filename.
                "CacheControl": "public, max-age=3600",
            },
            Config=transfer_config,
            Callback=progress,
        )
    except Exception as e:
        print(f"FATAL: upload failed: {e}", file=sys.stderr)
        return 1

    elapsed = time.time() - started
    print(f"upload complete in {elapsed:.1f}s ({size_mb / max(elapsed, 0.001):.1f} MB/s).")

    # Head the object to confirm Content-Type stuck and verify size on R2.
    try:
        head = client.head_object(Bucket=bucket, Key=TARGET_KEY)
        remote_size = head.get("ContentLength", 0)
        remote_ct = head.get("ContentType", "?")
        print(f"verified on R2: size={remote_size:,} bytes, Content-Type={remote_ct}")
        if remote_size != size_bytes:
            print(f"WARNING: remote size {remote_size:,} does not match local {size_bytes:,}", file=sys.stderr)
    except Exception as e:
        print(f"WARNING: head_object failed (upload itself succeeded): {e}", file=sys.stderr)

    # Public URL
    if public_url_base:
        public_url = f"{public_url_base}/{TARGET_KEY}"
        print(f"\nPublic download URL:\n  {public_url}")
        print("\nCustomers reach the DMG by visiting that URL.")
    else:
        print(
            "\nR2_PUBLIC_URL is not set in .env.local yet.\n"
            "Enable Public Access on the anticipy-downloads bucket in the Cloudflare dashboard,\n"
            "copy the public URL (it looks like https://pub-<hash>.r2.dev), and paste it as\n"
            "R2_PUBLIC_URL and NEXT_PUBLIC_R2_PUBLIC_URL in .env.local. Then re-run this script\n"
            "to print the final customer-facing URL."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
