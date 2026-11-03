"""Supabase Auth email transport. HTTP acceptance is never proof of delivery.

An existing identity receives a recovery link only after Supabase explicitly
reports that the invite endpoint cannot invite that identity. The application
grant stays in PostgreSQL and is never inferred from an Auth email/session.
"""
from uuid import UUID
from urllib.parse import urlsplit

import httpx


class InvitationProviderError(RuntimeError):
    def __init__(self, http_status: int | None, provider_code: str, method: str = "invite", retry_after: int = 0):
        super().__init__("supabase_invitation_send_failed")
        self.http_status, self.provider_code, self.method = http_status, provider_code, method
        self.retry_after = retry_after


class InvitationNetworkError(RuntimeError):
    def __init__(self, method: str):
        super().__init__("supabase_invitation_network_uncertain")
        self.method = method


def provider_code(response: httpx.Response) -> str:
    try:
        raw = response.json().get("code")
    except (ValueError, AttributeError):
        raw = None
    # Never persist free-form provider bodies, which can contain PII or links.
    allowed = {"user_already_exists", "email_exists", "over_email_send_rate_limit",
               "over_request_rate_limit", "email_address_not_authorized",
               "email_address_invalid", "validation_failed", "unexpected_failure",
               "email_provider_disabled", "request_timeout"}
    return raw if raw in allowed else "provider_rejected"


def redirect_url(config, invitation_id: UUID) -> str:
    origin = config.app_public_url.rstrip("/")
    parsed = urlsplit(origin)
    if (parsed.scheme not in ("https", "http") or not parsed.hostname or parsed.path
            or parsed.query or parsed.fragment or parsed.username or parsed.password
            or "*" in origin):
        raise RuntimeError("invitation_not_configured")
    if getattr(config, "environment", "development") == "production":
        if parsed.scheme != "https" or origin != config.cors_origin:
            raise RuntimeError("invitation_private_origin_mismatch")
    elif parsed.scheme == "http" and parsed.hostname not in ("localhost", "127.0.0.1"):
        raise RuntimeError("invitation_not_configured")
    return f"{origin}/invite/accept?invitation_id={invitation_id}"


async def _request(config, email: str, invitation_id: UUID, method: str) -> httpx.Response:
    key = config.supabase_service_role_key.get_secret_value().strip()
    if not key or not config.supabase_url:
        raise RuntimeError("invitation_not_configured")
    callback = redirect_url(config, invitation_id)
    try:
        async with httpx.AsyncClient(trust_env=False, timeout=httpx.Timeout(8, connect=3)) as client:
            return await client.post(f"{config.supabase_url}/auth/v1/{'recover' if method == 'recovery' else 'invite'}",
                params={"redirect_to": callback},
                headers={"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={"email": email})
    except httpx.HTTPError:
        raise InvitationNetworkError(method) from None


def _check(response: httpx.Response, method: str) -> int:
    if response.status_code in ((200, 202) if method == "recovery" else (200, 201)):
        return response.status_code
    # A gateway/server error may occur after the email side effect; do not retry automatically.
    if response.status_code >= 500:
        raise InvitationNetworkError(method)
    raw_retry = getattr(response, "headers", {}).get("retry-after", "")
    retry_after = max(1, min(int(raw_retry), 3600)) if str(raw_retry).isdigit() else (60 if response.status_code == 429 else 0)
    raise InvitationProviderError(response.status_code, provider_code(response), method, retry_after)


async def send_invitation(config, email: str, invitation_id: UUID) -> tuple[str, int]:
    response = await _request(config, email, invitation_id, "invite")
    if response.status_code not in (200, 201) and provider_code(response) in ("user_already_exists", "email_exists"):
        return "recovery", await send_recovery(config, email, invitation_id)
    return "invite", _check(response, "invite")


async def send_recovery(config, email: str, invitation_id: UUID) -> int:
    return _check(await _request(config, email, invitation_id, "recovery"), "recovery")
