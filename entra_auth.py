"""Validación de tokens de acceso Microsoft Entra para el MCP de ANDI.

Los tokens deben emitirse PARA la API de ANDI (audience = ENTRA_CLIENT_ID
o ENTRA_AUDIENCE). No se aceptan ID tokens ni tokens de Microsoft Graph.
"""
import os
from functools import lru_cache
import jwt
from jwt import PyJWKClient

def _csv(name):
    return {v.strip().lower() for v in os.getenv(name, "").split(",") if v.strip()}

@lru_cache(maxsize=4)
def _jwks(tenant):
    return PyJWKClient(
        f"https://login.microsoftonline.com/{tenant}/discovery/v2.0/keys",
        cache_jwk_set=True,
        lifespan=300,
        timeout=5,
    )

def validate_entra_token(token):
    tenant = os.environ["ENTRA_TENANT_ID"].strip()
    audience = os.getenv("ENTRA_AUDIENCE", os.environ["ENTRA_CLIENT_ID"]).strip()
    issuer = f"https://login.microsoftonline.com/{tenant}/v2.0"
    signing_key = _jwks(tenant).get_signing_key_from_jwt(token)
    claims = jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        audience=audience,
        issuer=issuer,
        options={"require": ["exp", "iat", "iss", "aud", "tid"]},
        leeway=60,
    )
    if claims["tid"].lower() != tenant.lower():
        raise ValueError("Tenant no autorizado")
    allowed_users = _csv("ENTRA_ALLOWED_USER_IDS")
    allowed_clients = _csv("ENTRA_ALLOWED_CLIENT_IDS")
    if not allowed_users or not allowed_clients:
        raise ValueError("Listas de usuarios/clientes permitidos sin configurar")
    if claims.get("oid", "").lower() not in allowed_users:
        raise ValueError("Usuario no autorizado")
    client = (claims.get("azp") or claims.get("appid") or "").lower()
    if client not in allowed_clients:
        raise ValueError("Cliente OAuth no autorizado")
    # Los tokens delegados deben incluir el scope expuesto por la API.
    required_scope = os.getenv("ENTRA_REQUIRED_SCOPE", "access_as_user")
    if required_scope not in claims.get("scp", "").split():
        raise ValueError("Scope requerido ausente")
    return claims
