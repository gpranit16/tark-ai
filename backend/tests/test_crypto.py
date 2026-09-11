from uuid import uuid4
import pytest
from app.core.security import (
    create_oauth_state,
    decrypt_secret,
    encrypt_secret,
    verify_oauth_state,
)


def test_encrypt_decrypt_secret():
    secret_text = "ya29.a0AfH6SMB_secret_access_token_123456789"
    ciphertext = encrypt_secret(secret_text)
    assert ciphertext != secret_text
    assert len(ciphertext) > 20

    decrypted = decrypt_secret(ciphertext)
    assert decrypted == secret_text


def test_encrypt_decrypt_empty():
    assert encrypt_secret("") == ""
    assert decrypt_secret("") == ""


def test_oauth_state_generation_and_verification():
    user_id = uuid4()
    state = create_oauth_state(user_id=user_id, provider="google", service="calendar")
    assert isinstance(state, str)
    assert len(state) > 10

    verified_user_id = verify_oauth_state(state, expected_provider="google", expected_service="calendar")
    assert verified_user_id == user_id


def test_oauth_state_tampered_or_mismatched():
    user_id = uuid4()
    state = create_oauth_state(user_id=user_id, provider="google", service="calendar")

    # Mismatched provider/service expectation
    with pytest.raises(ValueError, match="mismatch"):
        verify_oauth_state(state, expected_provider="github", expected_service="calendar")

    # Tampered token
    with pytest.raises(ValueError, match="Invalid"):
        verify_oauth_state(state + "tampered", expected_provider="google", expected_service="calendar")
