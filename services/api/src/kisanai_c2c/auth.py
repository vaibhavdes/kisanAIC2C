from functools import lru_cache

from fastapi import Depends, Header, HTTPException, status
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from .models import Actor, Role
from .settings import Settings, get_settings


@lru_cache
def _google_request() -> google_requests.Request:
    return google_requests.Request()


def current_actor(
    authorization: str | None = Header(default=None),
    x_actor_id: str | None = Header(default=None),
    x_actor_role: str | None = Header(default=None),
    x_actor_locale: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> Actor:
    if settings.auth_mode == "local":
        if settings.app_env == "production":
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Local authentication is disabled")
        subject = (x_actor_id or "local-farmer").strip()
        requested = {part.strip() for part in (x_actor_role or "farmer").split(",") if part.strip()}
        try:
            roles = {Role(role) for role in requested}
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid X-Actor-Role") from exc
        return Actor(
            subject=subject,
            node_id=settings.node_id,
            roles=roles or {Role.farmer},
            locale=x_actor_locale or settings.default_locale,
        )

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Bearer token required")
    token = authorization.removeprefix("Bearer ").strip()
    try:
        claims = id_token.verify_firebase_token(token, _google_request(), audience=settings.google_cloud_project)
    except Exception as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired Firebase token") from exc
    subject = str(claims.get("sub") or claims.get("user_id") or "")
    if not subject:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Firebase token has no subject")
    token_roles = claims.get("roles") or []
    if isinstance(token_roles, str):
        token_roles = [token_roles]
    roles = {Role.farmer}
    roles.update(Role(role) for role in token_roles if role in Role._value2member_map_)
    if subject in settings.expert_subject_set:
        roles.add(Role.expert)
    return Actor(
        subject=subject,
        node_id=settings.node_id,
        roles=roles,
        locale=str(claims.get("locale") or settings.default_locale),
        email=claims.get("email"),
    )


def require_roles(*required: Role):
    def dependency(actor: Actor = Depends(current_actor)) -> Actor:
        if not actor.roles.intersection(required):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient role")
        return actor

    return dependency
