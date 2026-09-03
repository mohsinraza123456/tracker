from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import TrackingDomain

router = APIRouter(prefix="/tracking-domains", tags=["tracking-domains"])
templates = Jinja2Templates(directory="app/templates")


@router.get("")
def list_tracking_domains(request: Request, db: Session = Depends(get_db)):
    domains = db.query(TrackingDomain).order_by(TrackingDomain.domain).all()
    return templates.TemplateResponse(
        "tracking_domains/list.html", {"request": request, "domains": domains}
    )


@router.get("/new")
def new_tracking_domain_form(request: Request):
    return templates.TemplateResponse(
        "tracking_domains/form.html", {"request": request, "domain": None}
    )


@router.post("/new")
def create_tracking_domain(
    domain: str = Form(...), notes: str = Form(""), db: Session = Depends(get_db)
):
    td = TrackingDomain(domain=domain.rstrip("/"), notes=notes or None)
    db.add(td)
    db.commit()
    return RedirectResponse(url="/tracking-domains?msg=Tracking domain created", status_code=303)


@router.get("/{td_id}/edit")
def edit_tracking_domain_form(td_id: int, request: Request, db: Session = Depends(get_db)):
    td = db.get(TrackingDomain, td_id)
    if not td:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(
        "tracking_domains/form.html", {"request": request, "domain": td}
    )


@router.post("/{td_id}/edit")
def update_tracking_domain(
    td_id: int, domain: str = Form(...), notes: str = Form(""), db: Session = Depends(get_db)
):
    td = db.get(TrackingDomain, td_id)
    if not td:
        raise HTTPException(status_code=404)
    td.domain = domain.rstrip("/")
    td.notes = notes or None
    db.commit()
    return RedirectResponse(url="/tracking-domains?msg=Tracking domain updated", status_code=303)


@router.get("/{td_id}/delete")
def delete_tracking_domain(td_id: int, db: Session = Depends(get_db)):
    td = db.get(TrackingDomain, td_id)
    if td:
        if td.campaigns:
            return RedirectResponse(
                url="/tracking-domains?msg=Cannot delete: domain is used by a campaign",
                status_code=303,
            )
        db.delete(td)
        db.commit()
    return RedirectResponse(url="/tracking-domains?msg=Tracking domain deleted", status_code=303)
