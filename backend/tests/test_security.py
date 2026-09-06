import pytest
from app.storage.b2 import validate_storage_key
from fastapi import HTTPException


def test_storage_key_traversal_prevention():
    traversal_payloads = [
        "../secret.txt",
        "../../etc/shadow",
        "..\\..\\windows\\system32\\config",
        "/etc/passwd",
        "users/123/../../456/file.txt",
        "users/123/././file.txt",
        "users/123/\x00malicious.pdf",
    ]

    for payload in traversal_payloads:
        with pytest.raises(HTTPException) as exc_info:
            validate_storage_key(payload)
        assert exc_info.value.status_code == 400


def test_b2_no_credentials_in_logs_or_repr():
    from app.storage.b2 import B2StorageProvider
    
    provider = B2StorageProvider(
        key_id="secret_key_id_12345",
        application_key="super_secret_app_key_67890",
        bucket_name="private-bucket",
    )
    
    rep = repr(provider)
    assert "super_secret_app_key_67890" not in rep
    assert provider.provider_name == "b2"
