"""JWT decoding, JWKS/key signature validation, and RFC 9728 OAuth metadata."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import jwt
from jwt import PyJWKClient

from app.config.settings import Settings


class AuthenticationError(Exception):
    """Raised when an incoming bearer JWT fails cryptographic or claim verification."""

    def __init__(self, message: str, *, error_code: str = "invalid_token") -> None:
        super().__init__(message)
        self.message = message
        self.error_code = error_code


@dataclass(frozen=True, slots=True)
class VerifiedTokenClaims:
    """Normalized claims extracted from a verified JWT."""

    subject: str
    client_id: str
    issuer: str | None
    audience: str | None
    scopes: frozenset[str]
    expires_at: int | None
    raw_claims: dict[str, Any]


@lru_cache(maxsize=8)
def _get_jwks_client(jwks_url: str) -> PyJWKClient:
    return PyJWKClient(jwks_url, cache_keys=True, lifespan=300)


def _extract_scopes(claims: dict[str, Any]) -> frozenset[str]:
    scopes: set[str] = set()
    raw_scope = claims.get("scope")
    if isinstance(raw_scope, str):
        scopes.update(part.strip() for part in raw_scope.split() if part.strip())
    elif isinstance(raw_scope, list):
        scopes.update(str(item).strip() for item in raw_scope if str(item).strip())

    raw_scp = claims.get("scp")
    if isinstance(raw_scp, str):
        scopes.update(part.strip() for part in raw_scp.split() if part.strip())
    elif isinstance(raw_scp, list):
        scopes.update(str(item).strip() for item in raw_scp if str(item).strip())
    return frozenset(scopes)


def _decode_jwt(
    token: str,
    *,
    key: Any,
    algorithms: list[str],
    issuer: str,
    audience: str,
    leeway: int,
) -> VerifiedTokenClaims:
    try:
        claims = jwt.decode(
            token,
            key=key,
            algorithms=algorithms,
            issuer=issuer,
            audience=audience,
            leeway=leeway,
            options={
                "require": ["exp", "sub", "iss", "aud"],
                "verify_signature": True,
                "verify_exp": True,
                "verify_iss": True,
                "verify_aud": True,
            },
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError("Bearer token has expired.") from exc
    except jwt.InvalidIssuerError as exc:
        raise AuthenticationError("Bearer token issuer mismatch.") from exc
    except jwt.InvalidAudienceError as exc:
        raise AuthenticationError("Bearer token audience mismatch.") from exc
    except jwt.PyJWTError as exc:
        raise AuthenticationError(f"Bearer token validation failed: {type(exc).__name__}.") from exc

    subject = str(claims.get("sub") or "").strip()
    if not subject:
        raise AuthenticationError("Bearer token missing non-empty 'sub' claim.")

    client_id = str(claims.get("azp") or claims.get("client_id") or subject).strip()
    aud_claim = claims.get("aud")
    audience_str = aud_claim[0] if isinstance(aud_claim, list) and aud_claim else (str(aud_claim) if aud_claim else None)
    exp_raw = claims.get("exp")
    expires_at = int(exp_raw) if isinstance(exp_raw, int | float) else None

    return VerifiedTokenClaims(
        subject=subject,
        client_id=client_id,
        issuer=str(claims.get("iss")) if claims.get("iss") else None,
        audience=audience_str,
        scopes=_extract_scopes(claims),
        expires_at=expires_at,
        raw_claims=claims,
    )


def verify_delegated_jwt(token: str, settings: Settings) -> VerifiedTokenClaims:
    """Verify an internal delegated user JWT presented alongside X-Internal-API-Key."""
    alg = settings.internal_jwt_algorithm
    if alg.startswith("HS"):
        key: Any = settings.internal_jwt_secret.get_secret_value()
    elif settings.internal_jwt_public_key is not None:
        key = settings.internal_jwt_public_key.get_secret_value()
    else:
        raise AuthenticationError("Internal delegated JWT public key is not configured.")

    return _decode_jwt(
        token,
        key=key,
        algorithms=[alg],
        issuer=settings.internal_jwt_issuer,
        audience=settings.internal_jwt_audience,
        leeway=settings.jwt_leeway_seconds,
    )


def verify_oauth_jwt(token: str, settings: Settings) -> VerifiedTokenClaims:
    """Verify an external OAuth 2.1 Bearer JWT via JWKS or configured verification key."""
    if not settings.oauth_enabled:
        raise AuthenticationError("External OAuth 2.1 authentication is disabled.")

    signing_key: Any = None
    if settings.oauth_jwks_url:
        try:
            jwk_client = _get_jwks_client(settings.oauth_jwks_url)
            signing_key = jwk_client.get_signing_key_from_jwt(token).key
        except jwt.PyJWTError as exc:
            raise AuthenticationError("Unable to resolve signing key from JWKS.") from exc
    elif settings.oauth_public_key is not None:
        signing_key = settings.oauth_public_key.get_secret_value()
    else:
        raise AuthenticationError(
            "OAuth 2.1 verification requires MCP_OAUTH_JWKS_URL or MCP_OAUTH_PUBLIC_KEY.",
            error_code="server_error",
        )

    return _decode_jwt(
        token,
        key=signing_key,
        algorithms=settings.oauth_algorithms,
        issuer=settings.oauth_issuer,
        audience=settings.oauth_audience,
        leeway=settings.jwt_leeway_seconds,
    )


def build_protected_resource_metadata(settings: Settings) -> dict[str, Any]:
    """Build RFC 9728 OAuth 2.0 Protected Resource Metadata payload."""
    return {
        "resource": settings.oauth_resource_server_url,
        "authorization_servers": [settings.oauth_issuer],
        "scopes_supported": list(settings.oauth_supported_scopes),
        "bearer_methods_supported": ["header"],
        "resource_name": "Market Intelligence MCP Server",
    }
