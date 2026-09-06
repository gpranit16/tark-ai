import asyncio
import io
import os
import sys
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.config import get_settings
from app.db.session import AsyncSessionLocal
from app.services import files as file_service
from app.storage.factory import get_storage_provider

DEV_USER_ID = UUID("00000000-0000-0000-0000-000000000001")


async def run_live_tests():
    print("=== STARTING LIVE STORAGE SELECTION VERIFICATION ===")

    # ---------------------------------------------------------
    # TEST A: Upload with LOCAL provider
    # ---------------------------------------------------------
    print("\n[TEST A] Uploading with storage_provider='local'...")
    test_a_bytes = b"%PDF-1.4 Mock PDF Content for Local Storage Test"
    async with AsyncSessionLocal() as session:
        file_a = await file_service.process_and_upload_file(
            session=session,
            file_stream=io.BytesIO(test_a_bytes),
            filename="live_test_local.pdf",
            mime_type="application/pdf",
            size_bytes=len(test_a_bytes),
            user_id=DEV_USER_ID,
            storage_provider="local",
        )
        file_a_id = file_a.id
        file_a_key = file_a.storage_key
        file_a_prov = file_a.storage_provider

    print("Test A File ID:", file_a_id)
    print("Test A DB storage_provider:", file_a_prov)
    assert file_a_prov == "local", f"Expected local, got {file_a_prov}"

    local_prov = get_storage_provider("local")
    local_exists = await local_prov.exists(file_a_key)
    print("Test A Local Disk Exists:", local_exists)
    assert local_exists, "Local file should exist on disk"

    dl_a = await local_prov.download(file_a_key)
    assert dl_a == test_a_bytes, "Downloaded content must match uploaded bytes"
    print("Test A Preview/Read verified: SUCCESS")

    # ---------------------------------------------------------
    # TEST B: Upload with B2 provider
    # ---------------------------------------------------------
    print("\n[TEST B] Uploading with storage_provider='b2'...")
    test_b_bytes = b"%PDF-1.4 Mock PDF Content for Backblaze B2 Live Verification"
    async with AsyncSessionLocal() as session:
        file_b = await file_service.process_and_upload_file(
            session=session,
            file_stream=io.BytesIO(test_b_bytes),
            filename="live_test_b2.pdf",
            mime_type="application/pdf",
            size_bytes=len(test_b_bytes),
            user_id=DEV_USER_ID,
            storage_provider="b2",
        )
        file_b_id = file_b.id
        file_b_key = file_b.storage_key
        file_b_prov = file_b.storage_provider

    print("Test B File ID:", file_b_id)
    print("Test B DB storage_provider:", file_b_prov)
    assert file_b_prov == "b2", f"Expected b2, got {file_b_prov}"

    b2_prov = get_storage_provider("b2")
    b2_exists = await b2_prov.exists(file_b_key)
    print("Test B Backblaze B2 Object Exists in Bucket:", b2_exists)
    assert b2_exists, "B2 object must exist in tarkai-files bucket"

    dl_b = await b2_prov.download(file_b_key)
    assert dl_b == test_b_bytes, "B2 downloaded content must match uploaded bytes"
    print("Test B Preview/Read verified: SUCCESS")

    # ---------------------------------------------------------
    # TEST C: Provider switching isolation & Stats
    # ---------------------------------------------------------
    print("\n[TEST C] Testing Provider Independence & Storage Stats...")
    async with AsyncSessionLocal() as session:
        stats = await file_service.get_storage_stats(session, DEV_USER_ID)
    print("Storage Stats -> Total:", stats["total_files"], "Local:", stats["local_files"], "B2:", stats["b2_files"])
    assert stats["local_files"] >= 1
    assert stats["b2_files"] >= 1

    settings = get_settings()
    orig_prov = settings.storage_provider
    try:
        settings.storage_provider = "local"
        async with AsyncSessionLocal() as session:
            f_b_record = await file_service.get_file(session, file_b_id, DEV_USER_ID)
            prov_for_b = get_storage_provider(f_b_record.storage_provider)
            content_b = await prov_for_b.download(f_b_record.storage_key)
            assert content_b == test_b_bytes
            print("  -> B2 file downloaded successfully while global provider is 'local'!")

        settings.storage_provider = "b2"
        async with AsyncSessionLocal() as session:
            f_a_record = await file_service.get_file(session, file_a_id, DEV_USER_ID)
            prov_for_a = get_storage_provider(f_a_record.storage_provider)
            content_a = await prov_for_a.download(f_a_record.storage_key)
            assert content_a == test_a_bytes
            print("  -> Local file downloaded successfully while global provider is 'b2'!")
    finally:
        settings.storage_provider = orig_prov

    # ---------------------------------------------------------
    # CLEANUP TEST FILES
    # ---------------------------------------------------------
    print("\n[CLEANUP] Deleting live test artifacts...")
    async with AsyncSessionLocal() as session:
        await file_service.delete_file(session, file_a_id, DEV_USER_ID)
        await file_service.delete_file(session, file_b_id, DEV_USER_ID)

    assert not await local_prov.exists(file_a_key)
    assert not await b2_prov.exists(file_b_key)
    print("Cleanup SUCCESS: Both test files safely removed from disk & B2 bucket.")

    print("\n>>> ALL LIVE VERIFICATION CHECKS (TEST A, TEST B, TEST C) PASSED 100%! <<<")


if __name__ == "__main__":
    asyncio.run(run_live_tests())
