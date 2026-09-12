"""Request authentication.

Two kinds of caller reach this API and they authenticate differently:

- An administrator's browser, holding an Auth0 access token for the signed-in
  user. Verified against Auth0's public keys.
- The collector agent, which is an unattended process on the monitored Mac
  with no user to sign in as. It presents a shared secret instead.
"""

import os
import secrets

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

AUTH0_DOMAIN = os.getenv("AUTH0_DOMAIN")
AUTH0_AUDIENCE = os.getenv("AUTH0_AUDIENCE")
AGENT_TOKEN = os.getenv("AGENT_TOKEN")

# auto_error=False so a missing header produces our own 401 rather than a 403,
# which is what HTTPBearer returns by default and is the wrong code here.
_bearer = HTTPBearer(auto_error=False)

# Caches Auth0's signing keys and refreshes them when a token references an
# unknown key id, so normal key rotation doesn't require a restart.
_jwks_client = (
    jwt.PyJWKClient(f"https://{AUTH0_DOMAIN}/.well-known/jwks.json")
    if AUTH0_DOMAIN else None
)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict:
    """Verify an Auth0 access token and return its claims."""
    if not credentials:
        raise _unauthorized("Missing bearer token")

    try:
        signing_key = _jwks_client.get_signing_key_from_jwt(credentials.credentials)
        return jwt.decode(
            credentials.credentials,
            signing_key.key,
            algorithms=["RS256"],
            audience=AUTH0_AUDIENCE,
            issuer=f"https://{AUTH0_DOMAIN}/",
        )
    except jwt.PyJWTError as e:
        # Includes an opaque (non-JWT) token, which is what Auth0 issues when
        # the audience isn't a registered API in the tenant.
        raise _unauthorized(f"Invalid token: {e}")


def require_agent(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> None:
    """Authenticate the collector agent via its shared secret."""
    if not credentials:
        raise _unauthorized("Missing agent token")
    # Constant-time compare so a wrong token can't be recovered by timing.
    if not secrets.compare_digest(credentials.credentials, AGENT_TOKEN):
        raise _unauthorized("Invalid agent token")


def check_config() -> None:
    """Fail at startup rather than serving telemetry unprotected."""
    missing = [
        name for name, value in (
            ("AUTH0_DOMAIN", AUTH0_DOMAIN),
            ("AUTH0_AUDIENCE", AUTH0_AUDIENCE),
            ("AGENT_TOKEN", AGENT_TOKEN),
        ) if not value
    ]
    if missing:
        raise RuntimeError(
            f"Refusing to start without {', '.join(missing)} — these protect the "
            f"telemetry API. See .env.example."
        )
