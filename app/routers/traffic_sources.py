from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import TrafficSource, User

router = APIRouter(prefix="/traffic-sources", tags=["traffic-sources"])
templates = Jinja2Templates(directory="app/templates")


@router.get("")
def list_traffic_sources(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    traffic_sources = (
        db.query(TrafficSource)
        .filter(TrafficSource.user_id == current_user.id)
        .order_by(TrafficSource.name)
        .all()
    )
    return templates.TemplateResponse(
        "traffic_sources/list.html",
        {"request": request, "traffic_sources": traffic_sources},
    )


@router.get("/new")
def new_traffic_source_form(request: Request, current_user: User = Depends(get_current_user)):
    return templates.TemplateResponse(
        "traffic_sources/form.html", {"request": request, "ts": None}
    )


@router.post("/new")
def create_traffic_source(
    name: str = Form(...),
    cost_model: str = Form("manual"),
    default_cost: float = Form(0.0),
    notes: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ts = TrafficSource(
        user_id=current_user.id, name=name, cost_model=cost_model, default_cost=default_cost, notes=notes or None
    )
    db.add(ts)
    db.commit()
    return RedirectResponse(url="/traffic-sources?msg=Traffic source created", status_code=303)


@router.get("/{ts_id}/edit")
def edit_traffic_source_form(ts_id: int, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    ts = db.query(TrafficSource).filter(TrafficSource.id == ts_id, TrafficSource.user_id == current_user.id).first()
    if not ts:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse("traffic_sources/form.html", {"request": request, "ts": ts})


@router.post("/{ts_id}/edit")
def update_traffic_source(
    ts_id: int,
    name: str = Form(...),
    cost_model: str = Form("manual"),
    default_cost: float = Form(0.0),
    notes: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ts = db.query(TrafficSource).filter(TrafficSource.id == ts_id, TrafficSource.user_id == current_user.id).first()
    if not ts:
        raise HTTPException(status_code=404)
    ts.name = name
    ts.cost_model = cost_model
    ts.default_cost = default_cost
    ts.notes = notes or None
    db.commit()
    return RedirectResponse(url="/traffic-sources?msg=Traffic source updated", status_code=303)


@router.get("/{ts_id}/delete")
def delete_traffic_source(ts_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    ts = db.query(TrafficSource).filter(TrafficSource.id == ts_id, TrafficSource.user_id == current_user.id).first()
    if ts:
        if ts.campaigns:
            return RedirectResponse(
                url="/traffic-sources?msg=Cannot delete: traffic source is used by a campaign",
                status_code=303,
            )
        db.delete(ts)
        db.commit()
    return RedirectResponse(url="/traffic-sources?msg=Traffic source deleted", status_code=303)
