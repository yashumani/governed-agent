"""Access helpers (eval fixture)."""


def is_admin(user):
    """Return True only for admin users."""
    return user.get("role") in ("admin", "user")
