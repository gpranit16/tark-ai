"""Migration script: Migrate local files to Backblaze B2 storage.

Features:
- Idempotent: Skips files already uploaded to B2 with identical storage key.
- Non-destructive: Preserves local files on disk.
- Safe logging: Never logs or prints credentials/secrets.
- Fault-tolerant: Continues on individual file errors and produces summary report.
- Supports --dry-run for pre-migration inspection.
"""

from __future__ import annotations

import argparse
import asyncio
import io
import os
import sys
from pathlib import Path
from typing import NamedTuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Ensure backend root is in sys.path
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import get_settings
from app.db.session import AsyncSessionLocal
from app.models.file import File
from app.storage.b2 import B2StorageProvider
from app.storage.local import LocalStorageProvider


class MigrationResult(NamedTuple):
    total_discovered: int
    migrated: int
    already_in_b2: int
    failed: int
    errors: list[dict[str, str]]


async def run_migration(dry_run: bool = False, uploads_dir: str = "uploads") -> MigrationResult:
    settings = get_settings()
    
    print("=" * 60)
    print("TARK AI — LOCAL STORAGE TO BACKBLAZE B2 MIGRATION")
    print(f"Mode: {'DRY RUN (No changes will be made)' if dry_run else 'LIVE MIGRATION'}")
    print(f"Target B2 Bucket: {settings.b2_bucket_name or '[NOT CONFIGURED]'}")
    print("=" * 60)

    if not dry_run:
        if not settings.b2_key_id or not settings.b2_application_key or not settings.b2_bucket_name:
            print("ERROR: B2 credentials or bucket name are missing in environment configuration.")
            print("Please configure B2_KEY_ID, B2_APPLICATION_KEY, and B2_BUCKET_NAME before running live migration.")
            return MigrationResult(0, 0, 0, 0, [{"error": "Missing B2 credentials"}])

    local_provider = LocalStorageProvider(upload_dir=uploads_dir)
    b2_provider = B2StorageProvider() if not dry_run else None

    migrated_count = 0
    already_in_b2_count = 0
    failed_count = 0
    errors: list[dict[str, str]] = []

    async with AsyncSessionLocal() as session:
        # Fetch all files from database
        stmt = select(File).order_by(File.created_at.asc())
        result = await session.execute(stmt)
        files = list(result.scalars().all())

        total_files = len(files)
        print(f"\nDiscovered {total_files} file records in database.\n")

        for idx, db_file in enumerate(files, 1):
            file_id_str = str(db_file.id)
            storage_key = db_file.storage_key
            sanitized_name = db_file.original_filename
            mime_type = db_file.mime_type or "application/octet-stream"

            print(f"[{idx}/{total_files}] Processing File ID: {file_id_str} | Name: {sanitized_name}")
            print(f"       Storage Key: {storage_key}")
            print(f"       Current Provider in DB: {db_file.storage_provider}")

            if dry_run:
                local_exists = await local_provider.exists(storage_key)
                print(f"       [DRY RUN] Local Exists: {local_exists} | Action: Would migrate to B2\n")
                migrated_count += 1
                continue

            try:
                # 1. Check if already exists in B2
                b2_exists = await b2_provider.exists(storage_key)
                if b2_exists:
                    print("       Status: Already exists in B2 (Idempotent skip).")
                    if db_file.storage_provider != "b2":
                        db_file.storage_provider = "b2"
                        await session.commit()
                        print("       DB Updated: storage_provider set to 'b2'.")
                    already_in_b2_count += 1
                    print()
                    continue

                # 2. Check local file availability
                local_exists = await local_provider.exists(storage_key)
                if not local_exists:
                    err_msg = f"Local file not found on disk at key '{storage_key}'."
                    print(f"       ERROR: {err_msg}")
                    failed_count += 1
                    errors.append({"file_id": file_id_str, "storage_key": storage_key, "error": err_msg})
                    print()
                    continue

                # 3. Read local file bytes
                local_bytes = await local_provider.download(storage_key)
                byte_stream = io.BytesIO(local_bytes)

                # 4. Upload to B2
                print("       Action: Uploading to B2...")
                await b2_provider.upload(byte_stream, storage_key, mime_type)

                # 5. Verify upload in B2
                verified = await b2_provider.exists(storage_key)
                if not verified:
                    raise RuntimeError("Verification failed: file not found in B2 immediately after upload.")

                # 6. Update database record
                db_file.storage_provider = "b2"
                await session.commit()

                print("       Status: Successfully uploaded to B2 and verified. DB record updated.")
                migrated_count += 1

            except Exception as exc:
                err_msg = str(exc)
                print(f"       ERROR: Migration failed: {err_msg}")
                failed_count += 1
                errors.append({"file_id": file_id_str, "storage_key": storage_key, "error": err_msg})

            print()

    print("=" * 60)
    print("MIGRATION SUMMARY")
    print(f"Total Discovered:  {total_files}")
    print(f"Migrated to B2:    {migrated_count}")
    print(f"Already in B2:     {already_in_b2_count}")
    print(f"Failed:            {failed_count}")
    print(f"Local files kept:  YES (Non-destructive)")
    print("=" * 60)

    return MigrationResult(
        total_discovered=total_files,
        migrated=migrated_count,
        already_in_b2=already_in_b2_count,
        failed=failed_count,
        errors=errors,
    )


def main():
    parser = argparse.ArgumentParser(description="Migrate TARK AI local files to Backblaze B2.")
    parser.add_argument("--dry-run", action="store_true", help="Inspect and simulate migration without changing data.")
    parser.add_argument("--uploads-dir", default="uploads", help="Path to local uploads directory (default: 'uploads').")
    args = parser.parse_args()

    asyncio.run(run_migration(dry_run=args.dry_run, uploads_dir=args.uploads_dir))


if __name__ == "__main__":
    main()
