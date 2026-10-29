"""Offline checks for the real-JWT A/B runner; no Docker or network."""
import jwt
import pytest

from run_auth_ab import auth_url, identity_from_token, expect


def test_auth_url_rejects_non_supabase_or_non_https():
    assert auth_url("https://fictional.supabase.co") == "https://fictional.supabase.co"
    for value in ("http://fictional.supabase.co", "https://example.com", "https://fictional.supabase.co/path"):
        with pytest.raises(ValueError):
            auth_url(value)


def test_token_identity_is_only_used_for_allowlist_setup():
    token = jwt.encode({"sub": "11111111-1111-4111-8111-111111111111"}, "fictional-test-key-with-more-than-32-bytes", algorithm="HS256")
    assert str(identity_from_token(token)) == "11111111-1111-4111-8111-111111111111"
    with pytest.raises(ValueError):
        identity_from_token("not-a-jwt")


def test_expected_status_does_not_print_response_payload(capsys):
    class Response:
        status_code = 404
        content = b'{"detail":"private"}'
        def json(self):
            return {"detail": "private"}
    assert expect(Response(), 404, "CROSS_OWNER") == {"detail": "private"}
    assert capsys.readouterr().out == "CROSS_OWNER=PASS\n"
