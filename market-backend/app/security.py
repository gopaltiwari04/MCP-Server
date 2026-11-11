"""Zero-trust internal gateway verification & delegated JWT extraction."""

from __future__ import annotations

import secrets
from dataclasses import dataclass

import jwt
from fastapi import Depends, Header, HTTPException, status

from app.config import BackendSettings, get_backend_settings


@dataclass(frozen=True, slots=True)
class GatewayCaller:
    user_id: str
    scopes: frozenset[str]
    request_id: str | None
    mcp_tool_name: str | None


def verify_gateway_caller(
    x_internal_api_key: str = Header(..., alias="X-Internal-API-Key"),
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_request_id: str | None = Header(default=None, alias="X-Request-ID"),
    x_mcp_tool_name: str | None = Header(default=None, alias="X-MCP-Tool-Name"),
    settings: BackendSettings = Depends(get_backend_settings),
) -> GatewayCaller:
    expected = settings.internal_api_key.get_secret_value()
    if not secrets.compare_digest(x_internal_api_key, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "PERMISSION_DENIED", "message": "Invalid X-Internal-API-Key."},
        )

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "PERMISSION_DENIED", "message": "Missing delegated Bearer JWT."},
        )

    token = authorization[7:].strip()
    key = (
        settings.oauth_public_key.get_secret_value()
        if settings.oauth_public_key is not None
        else settings.jwt_secret.get_secret_value()
    )

    try:
        claims = jwt.decode(
            token,
            key=key,
            algorithms=settings.jwt_algorithms,
            audience=settings.jwt_allowed_audiences,
            options={"require": ["sub", "exp", "iss"]},
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "PERMISSION_DENIED", "message": f"Invalid delegated JWT: {type(exc).__name__}"},
        ) from exc

    if str(claims.get("iss")) not in settings.jwt_allowed_issuers:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "PERMISSION_DENIED", "message": "Untrusted JWT issuer."},
        )

    raw_scope = claims.get("scope") or claims.get("scp") or ""
    if isinstance(raw_scope, str):
        scopes = frozenset(s.strip() for s in raw_scope.split() if s.strip())
    else:
        scopes = frozenset(str(s).strip() for s in raw_scope if str(s).strip())

    return GatewayCaller(
        user_id=str(claims["sub"]),
        scopes=scopes,
        request_id=x_request_id,
        mcp_tool_name=x_mcp_tool_name,
    )


def verify_health_key(
    x_internal_api_key: str = Header(..., alias="X-Internal-API-Key"),
    settings: BackendSettings = Depends(get_backend_settings),
) -> None:
    if not secrets.compare_digest(x_internal_api_key, settings.internal_api_key.get_secret_value()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid internal key.")


def require_scope(scope: str):
    def _dep(caller: GatewayCaller = Depends(verify_gateway_caller)) -> GatewayCaller:
        if scope not in caller.scopes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "PERMISSION_DENIED", "message": f"Missing required scope: {scope}"},
            )
        return caller

    return _dep
