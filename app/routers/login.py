import hmac

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.config import ADMIN_PASSWORD, ADMIN_USERNAME

router = APIRouter(tags=["auth"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/login")
def login_form(request: Request, next: str = "/"):
    if request.session.get("user"):
        return RedirectResponse(url=next or "/", status_code=303)
    return templates.TemplateResponse("login.html", {"request": request, "next": next, "error": None})


@router.post("/login")
async def login_submit(request: Request):
    form = await request.form()
    username = form.get("username", "")
    password = form.get("password", "")
    next_url = form.get("next") or "/"

    valid = hmac.compare_digest(username, ADMIN_USERNAME) and hmac.compare_digest(password, ADMIN_PASSWORD)
    if not valid:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "next": next_url, "error": "Invalid username or password"},
            status_code=401,
        )

    request.session["user"] = username
    return RedirectResponse(url=next_url, status_code=303)


@router.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)
