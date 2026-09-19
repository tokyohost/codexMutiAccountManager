from backend.utils.logger import redact


def test_redact_sensitive_values() -> None:
    value = redact('Authorization: Bearer secret access_token=abc "refreshToken":"xyz"')
    assert "secret" not in value
    assert "abc" not in value
    assert "xyz" not in value
    assert "***" in value
