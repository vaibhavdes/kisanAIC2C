import hmac
import re
from functools import lru_cache

from fastapi import Depends, Header, HTTPException, status
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from .models import Actor, Role
from .settings import Settings, get_settings


@lru_cache
def _google_request() -> google_requests.Request:
    return google_requests.Request()


DEVICE_SUBJECT = re.compile(r"^dev-[a-z0-9-]{8,64}$")


def current_actor(
    authorization: str | None = Header(default=None),
    x_actor_id: str | None = Header(default=None),
    x_expert_token: str | None = Header(default=None),
    x_actor_role: str | None = Header(default=None),
    x_actor_locale: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> Actor:
    if settings.auth_mode == "local":
        if settings.app_env == "production":
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Local authentication is disabled")
        # Farmers are identified by an anonymous per-device id generated in the browser.
        subject = (x_actor_id or "local-farmer").strip().lower()
        if subject != "local-farmer" and not DEVICE_SUBJECT.match(subject):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid device id")
        roles = {Role.farmer}
        if settings.expert_access_token:
            if x_expert_token:
                if not hmac.compare_digest(x_expert_token, settings.expert_access_token):
                    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid expert access code")
                roles.add(Role.expert)
        elif x_actor_role and "expert" in x_actor_role:
            # No access code configured: local development only.
            roles.add(Role.expert)
        return Actor(
            subject=subject,
            node_id=settings.node_id,
            roles=roles,
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
