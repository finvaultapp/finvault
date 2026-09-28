"""OpenID Connect client: authorization code flow with PKCE, ID token validation via the provider's JWKS.

All HTTP goes through httpx (the JWKS client is a PyJWKClient whose fetch uses httpx), so tests can
replace the provider by monkeypatching httpx.get / httpx.post.
"""
import base64
import hashlib
import secrets
import time
from urllib.parse import urlencode

import httpx
import jwt
from jwt import PyJWKClient

from .. import config_admin

# Only asymmetric algorithms: an HS256 token would be "signed" with our client secret, and "none" is never OK.
ALLOWED_ALGS = ["RS256", "RS384", "RS512", "PS256", "PS384", "PS512", "ES256", "ES384", "ES512", "EdDSA"]
DISCOVERY_TTL = 3600


class OidcError(Exception):
    """`code` is a short machine-readable reason shown to the user as ?sso_error=<code>."""

    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code


class _HttpxJWKClient(PyJWKClient):
    def fetch_data(self):
        try:
            r = httpx.get(self.uri, timeout=10, headers={"Accept": "application/json"})
            r.raise_for_status()
            data = r.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise jwt.PyJWKClientConnectionError(f"Couldn't fetch the provider's keys: {exc}") from exc
        if self.jwk_set_cache is not None:
            self.jwk_set_cache.put(data)
        return data


_cache: dict = {"at": 0.0, "url": "", "doc": None, "jwks": None}


def reset_cache() -> None:
    _cache.update(at=0.0, url="", doc=None, jwks=None)


def discovery() -> dict:
    url = config_admin.OIDC_DISCOVERY_URL
    if _cache["doc"] and _cache["url"] == url and time.monotonic() - _cache["at"] < DISCOVERY_TTL:
        return _cache["doc"]
    try:
        r = httpx.get(url, timeout=10, headers={"Accept": "application/json"})
        r.raise_for_status()
        doc = r.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise OidcError("provider_unreachable", f"Couldn't read the provider's discovery document: {exc}") from exc
    for k in ("issuer", "authorization_endpoint", "token_endpoint", "jwks_uri"):
        if not doc.get(k):
            raise OidcError("provider_misconfigured", f"The discovery document has no {k}.")
    _cache.update(at=time.monotonic(), url=url, doc=doc, jwks=_HttpxJWKClient(doc["jwks_uri"], cache_jwk_set=True, lifespan=600))
    return doc


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def new_flow() -> dict:
    verifier = _b64url(secrets.token_bytes(48))
    return {"state": _b64url(secrets.token_bytes(24)), "nonce": _b64url(secrets.token_bytes(24)), "verifier": verifier,
            "challenge": _b64url(hashlib.sha256(verifier.encode()).digest())}


def authorize_url(flow: dict, redirect_uri: str) -> str:
    doc = discovery()
    params = {"response_type": "code", "client_id": config_admin.OIDC_CLIENT_ID, "redirect_uri": redirect_uri,
              "scope": config_admin.OIDC_SCOPES, "state": flow["state"], "nonce": flow["nonce"],
              "code_challenge": flow["challenge"], "code_challenge_method": "S256"}
    sep = "&" if "?" in doc["authorization_endpoint"] else "?"
    return doc["authorization_endpoint"] + sep + urlencode(params)


def exchange_code(code: str, verifier: str, redirect_uri: str) -> dict:
    doc = discovery()
    data = {"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri,
            "code_verifier": verifier, "client_id": config_admin.OIDC_CLIENT_ID}
    methods = doc.get("token_endpoint_auth_methods_supported") or ["client_secret_basic"]
    auth = None
    if config_admin.OIDC_CLIENT_SECRET:
        if "client_secret_basic" in methods:
            auth = (config_admin.OIDC_CLIENT_ID, config_admin.OIDC_CLIENT_SECRET)
        else:
            data["client_secret"] = config_admin.OIDC_CLIENT_SECRET
    try:
        r = httpx.post(doc["token_endpoint"], data=data, auth=auth, timeout=15, headers={"Accept": "application/json"})
    except httpx.HTTPError as exc:
        raise OidcError("provider_unreachable", str(exc)) from exc
    if r.status_code != 200:
        raise OidcError("token_exchange_failed", f"Token endpoint returned HTTP {r.status_code}")
    try:
        tokens = r.json()
    except ValueError as exc:
        raise OidcError("token_exchange_failed", "Token endpoint didn't return JSON") from exc
    if not tokens.get("id_token"):
        raise OidcError("token_exchange_failed", "No ID token in the token response")
    return tokens


def validate_id_token(id_token: str, nonce: str) -> dict:
    doc = discovery()
    algs = [a for a in (doc.get("id_token_signing_alg_values_supported") or ["RS256"]) if a in ALLOWED_ALGS]
    if not algs:
        raise OidcError("provider_misconfigured", "The provider signs ID tokens with no algorithm FinVault accepts.")
    try:
        key = _cache["jwks"].get_signing_key_from_jwt(id_token)
        claims = jwt.decode(id_token, key.key, algorithms=algs, audience=config_admin.OIDC_CLIENT_ID,
                            issuer=doc["issuer"], leeway=60,
                            options={"require": ["iss", "aud", "exp", "iat", "sub"]})
    except jwt.PyJWKClientError as exc:
        raise OidcError("invalid_token", f"Couldn't find the key that signed the ID token: {exc}") from exc
    except jwt.PyJWTError as exc:
        raise OidcError("invalid_token", f"ID token rejected: {exc}") from exc
    if not claims.get("nonce") or not secrets.compare_digest(str(claims["nonce"]).encode(), nonce.encode()):
        raise OidcError("bad_nonce", "The ID token's nonce doesn't match this sign-in.")
    aud = claims["aud"]
    if isinstance(aud, list) and len(aud) > 1 and claims.get("azp") != config_admin.OIDC_CLIENT_ID:
        raise OidcError("invalid_token", "The ID token was issued to another client.")
    return claims


def identity(tokens: dict, claims: dict) -> dict:
    """Email and verified flag, from the ID token or (when it lacks email) the userinfo endpoint."""
    info = dict(claims)
    if not info.get("email") and tokens.get("access_token"):
        ep = discovery().get("userinfo_endpoint")
        if ep:
            try:
                r = httpx.get(ep, headers={"Authorization": f"Bearer {tokens['access_token']}"}, timeout=10)
                r.raise_for_status()
                ui = r.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise OidcError("provider_unreachable", f"Couldn't read userinfo: {exc}") from exc
            if ui.get("sub") != claims["sub"]:
                raise OidcError("invalid_token", "Userinfo belongs to a different subject.")
            info.update({k: ui[k] for k in ("email", "email_verified", "name", "preferred_username") if k in ui})
    verified = info.get("email_verified")
    if isinstance(verified, str):
        verified = verified.lower() == "true"
    return {"sub": str(claims["sub"]), "issuer": claims["iss"], "email": (info.get("email") or "").strip().lower(),
            "email_verified": bool(verified), "name": info.get("name") or info.get("preferred_username") or ""}
