import hmac
import re

from fastapi import Depends, Header, HTTPException, status

from .models import Actor, Role
from .settings import Settings, get_settings

DEVICE_SUBJECT = re.compile(r"^dev-[a-z0-9-]{8,64}$")


def current_actor(
    x_actor_id: str | None = Header(default=None),
    x_expert_token: str | None = Header(default=None),
    x_actor_role: str | None = Header(default=None),
    x_actor_locale: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> Actor:
    """Farmers are anonymous per-device ids generated in the browser; officers add the node's expert access code."""
    subject = (x_actor_id or "local-farmer").strip().lower()
    if subject != "local-farmer" and not DEVICE_SUBJECT.match(subject):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid device id")
    roles = {Role.farmer}
    if settings.expert_access_token:
        if x_expert_token:
            if not hmac.compare_digest(x_expert_token, settings.expert_access_token):
                raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid expert access code")
            roles.add(Role.expert)
    elif x_actor_role and "expert" in x_actor_role and settings.app_env != "production":
        # No access code configured: local development only.
        roles.add(Role.expert)
    return Actor(subject=subject, node_id=settings.node_id, roles=roles, locale=x_actor_locale or settings.default_locale)


def require_roles(*required: Role):
    def dependency(actor: Actor = Depends(current_actor)) -> Actor:
        if not actor.roles.intersection(required):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient role")
        return actor

    return dependency
