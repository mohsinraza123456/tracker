from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Click, Offer

router = APIRouter(prefix="/offers", tags=["offers"])
templates = Jinja2Templates(directory="app/templates")


@router.get("")
def list_offers(request: Request, db: Session = Depends(get_db)):
    offers = db.query(Offer).order_by(Offer.name).all()
    return templates.TemplateResponse("offers/list.html", {"request": request, "offers": offers})


@router.get("/new")
def new_offer_form(request: Request):
    return templates.TemplateResponse("offers/form.html", {"request": request, "offer": None})


@router.post("/new")
def create_offer(
    name: str = Form(...), url: str = Form(...), payout: float = Form(0.0), db: Session = Depends(get_db)
):
    offer = Offer(name=name, url=url, payout=payout)
    db.add(offer)
    db.commit()
    return RedirectResponse(url="/offers?msg=Offer created", status_code=303)


@router.get("/{offer_id}/edit")
def edit_offer_form(offer_id: int, request: Request, db: Session = Depends(get_db)):
    offer = db.get(Offer, offer_id)
    if not offer:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse("offers/form.html", {"request": request, "offer": offer})


@router.post("/{offer_id}/edit")
def update_offer(
    offer_id: int,
    name: str = Form(...),
    url: str = Form(...),
    payout: float = Form(0.0),
    db: Session = Depends(get_db),
):
    offer = db.get(Offer, offer_id)
    if not offer:
        raise HTTPException(status_code=404)
    offer.name = name
    offer.url = url
    offer.payout = payout
    db.commit()
    return RedirectResponse(url="/offers?msg=Offer updated", status_code=303)


@router.get("/{offer_id}/delete")
def delete_offer(offer_id: int, db: Session = Depends(get_db)):
    offer = db.get(Offer, offer_id)
    if offer:
        in_use = offer.campaign_links or db.query(Click).filter(Click.offer_id == offer_id).first()
        if in_use:
            return RedirectResponse(
                url="/offers?msg=Cannot delete: offer is used by a campaign", status_code=303
            )
        db.delete(offer)
        db.commit()
    return RedirectResponse(url="/offers?msg=Offer deleted", status_code=303)
