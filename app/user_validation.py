import hmac

from sqlalchemy.orm import Session

from app.config import ADMIN_USERNAME
from app.models import User


def validate_new_account(db: Session, username: str, password: str, confirm: str) -> str | None:
    """Shared rules for both self-registration and admin-created accounts.
    Returns an error message, or None if the account is good to create."""
    if len(username) < 3:
        return "Username must be at least 3 characters."
    if len(password) < 8:
        return "Password must be at least 8 characters."
    if password != confirm:
        return "Passwords don't match."
    if hmac.compare_digest(username, ADMIN_USERNAME):
        return "That username is reserved."
    if db.query(User).filter(User.username == username).first():
        return "That username is already taken."
    return None
