from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.database import get_db
from app.models import Campaign, LandingPage, Offer, TrackingDomain, TrafficSource, User
from app.passwords import hash_password
from app.routers.campaigns import delete_campaign_cascade
from app.user_validation import validate_new_account

router = APIRouter(prefix="/admin/users", tags=["admin-users"])
templates = Jinja2Templates(directory="app/templates")


@router.get("")
def list_users(request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    users = db.query(User).order_by(User.username).all()
    campaign_counts = dict(
        db.query(Campaign.user_id, func.count(Campaign.id)).group_by(Campaign.user_id).all()
    )
    admin_count = db.query(func.count(User.id)).filter(User.is_admin.is_(True)).scalar() or 0
    return templates.TemplateResponse(
        "admin/users.html",
        {
            "request": request,
            "users": users,
            "campaign_counts": campaign_counts,
            "current_user": current_user,
            "admin_count": admin_count,
        },
    )


@router.get("/new")
def new_user_form(request: Request, current_user: User = Depends(require_admin)):
    return templates.TemplateResponse("admin/user_form.html", {"request": request, "error": None})


@router.post("/new")
async def create_user(request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    form = await request.form()
    username = (form.get("username") or "").strip()
    password = form.get("password") or ""
    confirm = form.get("confirm") or ""
    make_admin = form.get("is_admin") == "on"

    error = validate_new_account(db, username, password, confirm)
    if error:
        return templates.TemplateResponse(
            "admin/user_form.html", {"request": request, "error": error}, status_code=400
        )

    user = User(username=username, password_hash=hash_password(password), is_admin=make_admin)
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return templates.TemplateResponse(
            "admin/user_form.html",
            {"request": request, "error": "That username is already taken."},
            status_code=400,
        )

    return RedirectResponse(url="/admin/users?msg=User created", status_code=303)


@router.get("/{user_id}/toggle-admin")
def toggle_admin(user_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404)

    if target.is_admin:
        admin_count = db.query(func.count(User.id)).filter(User.is_admin.is_(True)).scalar() or 0
        if admin_count <= 1:
            return RedirectResponse(
                url="/admin/users?msg=Cannot remove admin: at least one admin must remain",
                status_code=303,
            )
        target.is_admin = False
    else:
        target.is_admin = True
    db.commit()
    return RedirectResponse(url="/admin/users?msg=Updated admin status", status_code=303)


@router.get("/{user_id}/delete")
def delete_user(user_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    if user_id == current_user.id:
        return RedirectResponse(url="/admin/users?msg=Cannot delete your own account", status_code=303)

    target = db.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404)

    if target.is_admin:
        admin_count = db.query(func.count(User.id)).filter(User.is_admin.is_(True)).scalar() or 0
        if admin_count <= 1:
            return RedirectResponse(
                url="/admin/users?msg=Cannot delete the only remaining admin",
                status_code=303,
            )

    # Cascade: everything this user owns, in FK-safe order (campaigns/clicks first,
    # so the resources they reference are unreferenced by the time we delete them).
    for campaign in db.query(Campaign).filter(Campaign.user_id == user_id).all():
        delete_campaign_cascade(db, campaign)
    db.query(TrafficSource).filter(TrafficSource.user_id == user_id).delete(synchronize_session=False)
    db.query(LandingPage).filter(LandingPage.user_id == user_id).delete(synchronize_session=False)
    db.query(Offer).filter(Offer.user_id == user_id).delete(synchronize_session=False)
    db.query(TrackingDomain).filter(TrackingDomain.user_id == user_id).delete(synchronize_session=False)
    db.delete(target)
    db.commit()
    return RedirectResponse(url="/admin/users?msg=User deleted", status_code=303)
