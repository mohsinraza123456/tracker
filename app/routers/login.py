import hmac
import secrets

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import ADMIN_PASSWORD, ADMIN_USERNAME
from app.database import get_db
from app.models import User
from app.passwords import hash_password, verify_password

router = APIRouter(tags=["auth"])
templates = Jinja2Templates(directory="app/templates")

DEFAULT_AUTHED_PATH = "/dashboard"


def _log_in_as(request: Request, user: User) -> None:
    request.session["user"] = user.username
    request.session["is_admin"] = user.is_admin


@router.get("/login")
def login_form(request: Request, next: str = DEFAULT_AUTHED_PATH):
    if request.session.get("user"):
        return RedirectResponse(url=next or DEFAULT_AUTHED_PATH, status_code=303)
    return templates.TemplateResponse("login.html", {"request": request, "next": next, "error": None})


@router.post("/login")
async def login_submit(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    username = form.get("username", "")
    password = form.get("password", "")
    next_url = form.get("next") or DEFAULT_AUTHED_PATH

    # The env-var admin credential works alongside registered users — a break-glass
    # account for initial setup / recovery. It still needs a real row in `users` so
    # it can own data like anyone else; get-or-create it here rather than relying
    # solely on the one-time migration backfill (handles a fresh install too).
    if hmac.compare_digest(username, ADMIN_USERNAME) and hmac.compare_digest(password, ADMIN_PASSWORD):
        admin_user = db.query(User).filter(User.username == username).first()
        if not admin_user:
            admin_user = User(
                username=username,
                password_hash=hash_password(secrets.token_urlsafe(32)),
                is_admin=True,
            )
            db.add(admin_user)
            db.commit()
        elif not admin_user.is_admin:
            admin_user.is_admin = True
            db.commit()
        _log_in_as(request, admin_user)
        return RedirectResponse(url=next_url, status_code=303)

    user = db.query(User).filter(User.username == username).first()
    if user and verify_password(password, user.password_hash):
        _log_in_as(request, user)
        return RedirectResponse(url=next_url, status_code=303)

    return templates.TemplateResponse(
        "login.html",
        {"request": request, "next": next_url, "error": "Invalid username or password"},
        status_code=401,
    )


@router.get("/register")
def register_form(request: Request):
    if request.session.get("user"):
        return RedirectResponse(url=DEFAULT_AUTHED_PATH, status_code=303)
    return templates.TemplateResponse("register.html", {"request": request, "error": None})


@router.post("/register")
async def register_submit(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    username = (form.get("username") or "").strip()
    password = form.get("password") or ""
    confirm = form.get("confirm") or ""

    error = None
    if len(username) < 3:
        error = "Username must be at least 3 characters."
    elif len(password) < 8:
        error = "Password must be at least 8 characters."
    elif password != confirm:
        error = "Passwords don't match."
    elif hmac.compare_digest(username, ADMIN_USERNAME):
        error = "That username is reserved."
    elif db.query(User).filter(User.username == username).first():
        error = "That username is already taken."

    if error:
        return templates.TemplateResponse(
            "register.html", {"request": request, "error": error}, status_code=400
        )

    user = User(username=username, password_hash=hash_password(password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return templates.TemplateResponse(
            "register.html",
            {"request": request, "error": "That username is already taken."},
            status_code=400,
        )

    _log_in_as(request, user)
    return RedirectResponse(url=DEFAULT_AUTHED_PATH, status_code=303)


@router.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)
