from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User


def _redirect_to_login(request: Request) -> HTTPException:
    return HTTPException(status_code=303, headers={"Location": f"/login?next={request.url.path}"})


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """Enforces login and returns the logged-in user's row, for scoping owned data.

    Every route that reads or writes user-owned data (campaigns, offers, traffic
    sources, landing pages, tracking domains) should depend on this rather than
    just checking that *someone* is logged in.
    """
    username = request.session.get("user")
    if not username:
        raise _redirect_to_login(request)

    user = db.query(User).filter(User.username == username).first()
    if not user:
        # Session refers to a user that no longer exists (e.g. deleted) — force re-login.
        request.session.clear()
        raise _redirect_to_login(request)
    return user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user
