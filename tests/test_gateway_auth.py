"""Entra JWT verification and public MCP discovery, using locally signed tokens."""
import importlib.util
import os
import sys
import time
from pathlib import Path
from unittest.mock import patch

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from starlette.testclient import TestClient

import config
import gateway_auth

TENANT = "11111111-1111-1111-1111-111111111111"
APP = "22222222-2222-2222-2222-222222222222"
USER = "33333333-3333-3333-3333-333333333333"
CLIENT = "55555555-5555-5555-5555-555555555555"
OTHER = "44444444-4444-4444-4444-444444444444"
BASE = "https://andi.example.com"
SETTINGS = gateway_auth.EntraSettings(TENANT, APP, frozenset({USER}), frozenset({CLIENT}), BASE)


@pytest.fixture(scope="module")
def keys():
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = jwt.algorithms.RSAAlgorithm.to_jwk(private.public_key(), as_dict=True)
    jwk.update(kid="test-key", use="sig", alg="RS256")
    return private, {"keys": [jwk]}


def signed_token(keys, **changes):
    now = int(time.time())
    claims = {
        "iss": SETTINGS.issuer, "aud": APP, "tid": TENANT, "oid": USER,
        "azp": CLIENT, "scp": "andi.access", "ver": "2.0",
        "iat": now, "nbf": now, "exp": now + 600,
    }
    claims.update(changes)
    for name in list(claims):
        if claims[name] is None:
            del claims[name]
    return jwt.encode(claims, keys[0], algorithm="RS256", headers={"kid": "test-key"})


def verifier(keys):
    result = gateway_auth.EntraTokenVerifier(SETTINGS)
    result.jwks.fetch_data = lambda: keys[1]
    return result


def test_signed_token_requires_the_expected_identity_and_scope(keys):
    access = verifier(keys)._verify(signed_token(keys))
    assert access is not None
    assert access.client_id == CLIENT
    assert access.subject == USER
    assert access.scopes == [SETTINGS.qualified_scope]


@pytest.mark.parametrize("changes", [
    {"iss": "https://evil.example.com"}, {"aud": OTHER}, {"aud": [APP, OTHER]},
    {"tid": OTHER}, {"oid": OTHER}, {"azp": OTHER}, {"ver": "1.0"},
    {"scp": "andi.access.other"}, {"scp": None}, {"oid": None},
    {"exp": int(time.time()) - 300}, {"nbf": int(time.time()) + 300},
    {"iat": int(time.time()) + 300}, {"exp": None}, {"azp": None},
])
def test_other_identity_resource_client_or_expiry_is_rejected(keys, changes):
    assert verifier(keys)._verify(signed_token(keys, **changes)) is None


def test_invalid_signatures_and_algorithms_are_rejected(keys):
    token = signed_token(keys)
    head, payload, signature = token.split(".")
    tampered = f"{head}.{payload}.{'A' if signature[0] != 'A' else 'B'}{signature[1:]}"
    assert verifier(keys)._verify(tampered) is None
    hs_token = jwt.encode({"aud": APP}, "a-fake-key-that-has-at-least-32-characters", algorithm="HS256", headers={"kid": "test-key"})
    assert verifier(keys)._verify(hs_token) is None
    assert verifier(keys)._verify("not-a-token") is None
    assert verifier(keys)._verify("x" * 16385) is None


def test_jwks_unavailable_rejects_without_falling_back(keys):
    instance = gateway_auth.EntraTokenVerifier(SETTINGS)
    with patch.object(instance.jwks, "get_signing_key_from_jwt", side_effect=jwt.PyJWKClientConnectionError("offline")):
        assert instance._verify(signed_token(keys)) is None


def test_entra_configuration_is_fail_closed():
    valid = {
        "ENTRA_TENANT_ID": TENANT, "ENTRA_CLIENT_ID": APP,
        "ENTRA_ALLOWED_USER_IDS": USER, "PUBLIC_BASE_URL": BASE,
        "ENTRA_ALLOWED_CLIENT_IDS": CLIENT,
    }
    with patch.dict(os.environ, valid, clear=True):
        settings = gateway_auth.EntraSettings.from_environment()
        assert settings.allowed_clients == frozenset({CLIENT})
        assert settings.metadata_url == BASE + "/.well-known/oauth-protected-resource/mcp"
    for missing in valid:
        values = {key: value for key, value in valid.items() if key != missing}
        with patch.dict(os.environ, values, clear=True), pytest.raises(RuntimeError):
            gateway_auth.EntraSettings.from_environment()


@pytest.mark.parametrize("url", [
    "http://andi.example.com", "https://andi.example.com/mcp",
    'https://andi.example.com/?foo="bar"', "https://user:pass@andi.example.com",
    "https://andi.example.com/#fragment", "https://andi.example.com\n",
])
def test_discovery_url_never_uses_an_invalid_origin(url):
    with pytest.raises(RuntimeError):
        gateway_auth.public_base_url(url)


@pytest.fixture(scope="module")
def oauth_app(keys):
    # Build a fresh gateway so FastMCP's session manager is started only once.
    env = {
        "ENTRA_TENANT_ID": TENANT, "ENTRA_CLIENT_ID": APP,
        "ENTRA_ALLOWED_USER_IDS": USER, "PUBLIC_BASE_URL": BASE,
        "ENTRA_ALLOWED_CLIENT_IDS": CLIENT,
    }
    name = "andi_oauth_test_gateway"
    spec = importlib.util.spec_from_file_location(name, Path(__file__).parents[1] / "main.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    with patch.dict(os.environ, env), patch.object(config, "GATEWAY_AUTH_MODE", "entra"), patch.object(config, "PUBLIC_BASE_URL", BASE):
        spec.loader.exec_module(module)
    module.token_verifier.jwks.fetch_data = lambda: keys[1]
    with TestClient(module.app, base_url=BASE) as client:
        yield module, client
    del sys.modules[name]


def mcp_request(client, token=None, method="tools/list", params=None, headers=None):
    all_headers = {"Accept": "application/json, text/event-stream"}
    if token:
        all_headers["Authorization"] = f"Bearer {token}"
    all_headers.update(headers or {})
    return client.post(
        "/mcp", headers=all_headers,
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}},
        follow_redirects=False,
    )


def test_discovery_challenge_and_real_signed_oauth_mcp(oauth_app, keys):
    module, client = oauth_app
    response = client.get("/.well-known/oauth-protected-resource/mcp")
    assert response.status_code == 200
    meta = response.json()
    assert meta["resource"] == SETTINGS.resource
    assert meta["authorization_servers"] == [SETTINGS.issuer]
    assert meta["scopes_supported"] == [SETTINGS.qualified_scope]
    assert meta["bearer_methods_supported"] == ["header"]
    missing = mcp_request(client)
    assert missing.status_code == 401
    assert SETTINGS.metadata_url in missing.headers["www-authenticate"]
    assert mcp_request(client, config.GATEWAY_TOKEN).status_code == 401
    assert mcp_request(client, signed_token(keys, oid=OTHER)).status_code == 401
    response = mcp_request(client, signed_token(keys))
    assert response.status_code == 200
    assert "cliente_360" in {tool["name"] for tool in response.json()["result"]["tools"]}
    tool = next(tool for tool in response.json()["result"]["tools"] if tool["name"] == "cliente_360")
    assert tool["_meta"]["securitySchemes"][0]["scopes"] == [SETTINGS.qualified_scope]
    with patch.object(module.db, "call_procedure_sets", return_value=[[{"CLIENTE": "C0090"}], [], []]) as call, patch.object(module.db, "audit"):
        result = mcp_request(client, signed_token(keys), "tools/call", {
            "name": "cliente_360", "arguments": {"codigo_cliente": "C0090"},
        })
        assert result.status_code == 200
        assert not result.json()["result"].get("isError")
        call.assert_called_once_with("andi.sp_cliente_360", "C0090")


def test_remote_host_keeps_rebinding_protection(oauth_app, keys):
    _, client = oauth_app
    response = mcp_request(client, signed_token(keys), headers={"Host": "evil.example.com"})
    assert response.status_code == 421


def test_oauth_covers_non_mcp_routes_and_blocks_repository_assets(oauth_app, keys):
    _, client = oauth_app
    assert client.get("/health").status_code == 200
    assert client.get("/assets/Andi%20blanco.jpeg").status_code == 200
    for path in ("/assets/.env", "/assets/conexion.env", "/assets/main.py", "/assets/db.py"):
        assert client.get(path).status_code == 401
        assert client.get(path, headers={"Authorization": f"Bearer {signed_token(keys)}"}).status_code == 404
    assert client.post("/assistant/chat", json={"message": "Hola"}).status_code == 401
    valid = client.post(
        "/assistant/chat", json={"message": "Hola"},
        headers={"Authorization": f"Bearer {signed_token(keys)}"},
    )
    assert valid.status_code == 200
