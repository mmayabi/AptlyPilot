from app.core.password import hash_password, verify_password
from app.core.tokens import create_access_token, decode_access_token


def test_password_hash_and_verify() -> None:
    password = "secret-password"
    hashed = hash_password(password)

    assert hashed != password
    assert verify_password(password, hashed)
    assert not verify_password("wrong-password", hashed)


def test_create_and_decode_access_token() -> None:
    token = create_access_token(subject="123")
    payload = decode_access_token(token)

    assert payload["sub"] == "123"
    assert payload["type"] == "access"