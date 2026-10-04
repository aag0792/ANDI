"""Microsoft Entra authentication for the gateway; no tokens are persisted."""
import asyncio
import logging
import os
import re
from dataclasses import dataclass
from urllib.parse import urlsplit
from uuid import UUID

import jwt
from mcp.server.auth.provider import AccessToken

_log = logging.getLogger("andi.auth")


def _guid(value: str, name: str) -> str:
    try:
        return str(UUID(value))
    except (ValueError, AttributeError) as exc:
        raise RuntimeError(f"{name} debe ser un UUID válido.") from exc


def public_base_url(value: str) -> str:
    """Only a configured HTTPS origin; never derive discovery from Host headers."""
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https" or not parsed.hostname
        or not re.fullmatch(r"[a-zA-Z0-9](?:[a-zA-Z0-9.-]*[a-zA-Z0-9])?", parsed.hostname)
        or parsed.username or parsed.password or parsed.query or parsed.fragment
        or parsed.path not in {"", "/"} or any(c.isspace() for c in value)
    ):
        raise RuntimeError("PUBLIC_BASE_URL debe ser un origen HTTPS sin ruta, usuario ni parámetros.")
    return value.rstrip("/")


@dataclass(frozen=True)
class EntraSettings:
    tenant_id: str
    audience: str
    allowed_users: frozenset[str]
    allowed_clients: frozenset[str]
    base_url: str
    scope: str = "andi.access"

    @classmethod
    def from_environment(cls):
        tenant = _guid(os.getenv("ENTRA_TENANT_ID", ""), "ENTRA_TENANT_ID")
        audience = _guid(os.getenv("ENTRA_CLIENT_ID", ""), "ENTRA_CLIENT_ID")
        users = frozenset(
            _guid(value.strip(), "ENTRA_ALLOWED_USER_IDS")
            for value in os.getenv("ENTRA_ALLOWED_USER_IDS", "").split(",") if value.strip()
        )
        if not users:
            raise RuntimeError("ENTRA_ALLOWED_USER_IDS debe incluir al menos un usuario autorizado.")
        clients = frozenset(
            _guid(value.strip(), "ENTRA_ALLOWED_CLIENT_IDS")
            for value in os.getenv("ENTRA_ALLOWED_CLIENT_IDS", "").split(",") if value.strip()
        )
        if not clients:
            raise RuntimeError("ENTRA_ALLOWED_CLIENT_IDS no puede estar vacío.")
        return cls(tenant, audience, users, clients, public_base_url(os.getenv("PUBLIC_BASE_URL", "")))

    @property
    def issuer(self):
        return f"https://login.microsoftonline.com/{self.tenant_id}/v2.0"

    @property
    def resource(self):
        return f"{self.base_url}/mcp"

    @property
    def qualified_scope(self):
        return f"{self.resource}/{self.scope}"

    @property
    def metadata_url(self):
        return f"{self.base_url}/.well-known/oauth-protected-resource/mcp"


class EntraTokenVerifier:
    """PyJWT verifies signatures/time/issuer/audience; allowlists authorize users."""

    def __init__(self, settings: EntraSettings):
        self.settings = settings
        # Tenant is a validated UUID. Never follow a token-supplied jku or issuer.
        self.jwks = jwt.PyJWKClient(
            f"https://login.microsoftonline.com/{settings.tenant_id}/discovery/v2.0/keys",
            cache_jwk_set=True, lifespan=300, timeout=5,
        )

    def _verify(self, token: str) -> AccessToken | None:
        if not token or len(token) > 16384:
            return None
        try:
            header = jwt.get_unverified_header(token)
            if (
                header.get("alg") != "RS256"
                or not isinstance(header.get("kid"), str)
                or not 1 <= len(header["kid"]) <= 200
            ):
                return None
            key = self.jwks.get_signing_key_from_jwt(token).key
            claims = jwt.decode(
                token, key, algorithms=["RS256"],
                audience=self.settings.audience, issuer=self.settings.issuer,
                options={
                    "require": ["exp", "iat", "nbf", "iss", "aud", "tid", "oid", "azp", "scp", "ver"],
                    "strict_aud": True,
                },
            )
            if (
                claims["ver"] != "2.0"
                or claims["tid"] != self.settings.tenant_id
                or claims["oid"] not in self.settings.allowed_users
                or claims["azp"] not in self.settings.allowed_clients
                or not isinstance(claims["scp"], str)
                or self.settings.scope not in claims["scp"].split()
            ):
                return None
            return AccessToken(
                token=token, client_id=claims["azp"],
                scopes=[self.settings.qualified_scope],
                expires_at=claims["exp"], subject=claims["oid"],
            )
        except (jwt.InvalidTokenError, jwt.PyJWKClientError, OSError, TypeError, ValueError):
            # No tokens, personal data or exception messages in logs.
            _log.info("Token de Microsoft rechazado.")
            return None

    async def verify_token(self, token: str) -> AccessToken | None:
        # JWKS discovery can block. Keep it outside the ASGI event loop.
        return await asyncio.to_thread(self._verify, token)
