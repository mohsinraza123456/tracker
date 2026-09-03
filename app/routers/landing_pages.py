from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import Click, LandingPage, User

router = APIRouter(prefix="/landing-pages", tags=["landing-pages"])
templates = Jinja2Templates(directory="app/templates")


@router.get("")
def list_landing_pages(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    landing_pages = (
        db.query(LandingPage).filter(LandingPage.user_id == current_user.id).order_by(LandingPage.name).all()
    )
    return templates.TemplateResponse(
        "landing_pages/list.html", {"request": request, "landing_pages": landing_pages}
    )


@router.get("/new")
def new_landing_page_form(request: Request, current_user: User = Depends(get_current_user)):
    return templates.TemplateResponse("landing_pages/form.html", {"request": request, "lp": None})


@router.post("/new")
def create_landing_page(
    name: str = Form(...), url: str = Form(...), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    lp = LandingPage(user_id=current_user.id, name=name, url=url)
    db.add(lp)
    db.commit()
    return RedirectResponse(url="/landing-pages?msg=Landing page created", status_code=303)


@router.get("/{lp_id}/edit")
def edit_landing_page_form(lp_id: int, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    lp = db.query(LandingPage).filter(LandingPage.id == lp_id, LandingPage.user_id == current_user.id).first()
    if not lp:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse("landing_pages/form.html", {"request": request, "lp": lp})


@router.post("/{lp_id}/edit")
def update_landing_page(
    lp_id: int, name: str = Form(...), url: str = Form(...), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    lp = db.query(LandingPage).filter(LandingPage.id == lp_id, LandingPage.user_id == current_user.id).first()
    if not lp:
        raise HTTPException(status_code=404)
    lp.name = name
    lp.url = url
    db.commit()
    return RedirectResponse(url="/landing-pages?msg=Landing page updated", status_code=303)


@router.get("/{lp_id}/delete")
def delete_landing_page(lp_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    lp = db.query(LandingPage).filter(LandingPage.id == lp_id, LandingPage.user_id == current_user.id).first()
    if lp:
        in_use = lp.campaign_links or db.query(Click).filter(Click.landing_page_id == lp_id).first()
        if in_use:
            return RedirectResponse(
                url="/landing-pages?msg=Cannot delete: landing page is used by a campaign",
                status_code=303,
            )
        db.delete(lp)
        db.commit()
    return RedirectResponse(url="/landing-pages?msg=Landing page deleted", status_code=303)
