from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.auth import get_current_user
from app.config import BASE_URL
from app.database import get_db
from app.models import (
    Campaign,
    CampaignLandingPage,
    CampaignOffer,
    Click,
    Conversion,
    LandingPage,
    Offer,
    TrackingDomain,
    TrafficSource,
    User,
)
from app.stats import COUNTABLE_CLICK_FILTER, aggregate_clicks

router = APIRouter(prefix="/campaigns", tags=["campaigns"])
templates = Jinja2Templates(directory="app/templates")


def _campaign_stats(db: Session, campaign: Campaign) -> dict:
    clicks = (
        db.query(func.count(Click.id))
        .filter(Click.campaign_id == campaign.id, *COUNTABLE_CLICK_FILTER)
        .scalar()
        or 0
    )
    conv_query = (
        db.query(func.count(Conversion.id), func.coalesce(func.sum(Conversion.payout), 0.0))
        .join(Click, Conversion.click_id == Click.id)
        .filter(Click.campaign_id == campaign.id, *COUNTABLE_CLICK_FILTER)
        .first()
    )
    conversions, revenue = conv_query
    cost = clicks * campaign.cost_per_click
    profit = revenue - cost
    cvr = (conversions / clicks * 100) if clicks else 0.0
    roi = (profit / cost * 100) if cost else (100.0 if revenue else 0.0)
    return {
        "clicks": clicks,
        "conversions": conversions,
        "revenue": revenue,
        "cost": cost,
        "profit": profit,
        "cvr": cvr,
        "roi": roi,
    }


def _apply_variants(
    db: Session, campaign: Campaign, form, prefix: str, assoc_model, id_field: str, owned_ids: set[int]
) -> int:
    """Read `{prefix}{id}` weight fields from a submitted form and (re)create variant rows.
    Ids outside `owned_ids` are silently skipped (e.g. a crafted request referencing
    another user's landing page/offer). Returns the number of variants created."""
    count = 0
    for key, raw_value in form.multi_items():
        if not key.startswith(prefix):
            continue
        item_id = key[len(prefix):]
        try:
            weight = int(raw_value) if raw_value else 0
            item_id = int(item_id)
        except ValueError:
            continue
        if weight > 0 and item_id in owned_ids:
            db.add(assoc_model(campaign_id=campaign.id, weight=weight, **{id_field: item_id}))
            count += 1
    return count


def delete_campaign_cascade(db: Session, campaign: Campaign) -> None:
    """Delete a campaign and everything that references it. Does not commit —
    callers commit once, whether deleting one campaign or cascading a whole user."""
    db.query(Conversion).filter(
        Conversion.click_id.in_(db.query(Click.id).filter(Click.campaign_id == campaign.id))
    ).delete(synchronize_session=False)
    db.query(Click).filter(Click.campaign_id == campaign.id).delete(synchronize_session=False)
    db.delete(campaign)


@router.get("")
def list_campaigns(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    campaigns = (
        db.query(Campaign)
        .options(
            joinedload(Campaign.campaign_landing_pages).joinedload(CampaignLandingPage.landing_page),
            joinedload(Campaign.campaign_offers).joinedload(CampaignOffer.offer),
        )
        .filter(Campaign.user_id == current_user.id)
        .order_by(Campaign.name)
        .all()
    )
    return templates.TemplateResponse("campaigns/list.html", {"request": request, "campaigns": campaigns})


@router.get("/new")
def new_campaign_form(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return templates.TemplateResponse(
        "campaigns/form.html",
        {
            "request": request,
            "campaign": None,
            "traffic_sources": db.query(TrafficSource).filter(TrafficSource.user_id == current_user.id).order_by(TrafficSource.name).all(),
            "landing_pages": db.query(LandingPage).filter(LandingPage.user_id == current_user.id).order_by(LandingPage.name).all(),
            "offers": db.query(Offer).filter(Offer.user_id == current_user.id).order_by(Offer.name).all(),
            "tracking_domains": db.query(TrackingDomain).filter(TrackingDomain.user_id == current_user.id).order_by(TrackingDomain.domain).all(),
            "existing_lp_weights": {},
            "existing_offer_weights": {},
        },
    )


@router.post("/new")
async def create_campaign(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    form = await request.form()

    traffic_source_id = int(form.get("traffic_source_id"))
    if not db.query(TrafficSource).filter(
        TrafficSource.id == traffic_source_id, TrafficSource.user_id == current_user.id
    ).first():
        raise HTTPException(status_code=400, detail="Unknown traffic source")

    tracking_domain_id = form.get("tracking_domain_id") or ""
    if tracking_domain_id and not db.query(TrackingDomain).filter(
        TrackingDomain.id == int(tracking_domain_id), TrackingDomain.user_id == current_user.id
    ).first():
        raise HTTPException(status_code=400, detail="Unknown tracking domain")

    cost_override = form.get("cost_override") or ""
    bot_redirect_url = form.get("bot_redirect_url") or ""
    campaign = Campaign(
        user_id=current_user.id,
        name=form.get("name", "").strip(),
        traffic_source_id=traffic_source_id,
        tracking_domain_id=int(tracking_domain_id) if tracking_domain_id else None,
        cost_override=float(cost_override) if cost_override else None,
        bot_redirect_url=bot_redirect_url or None,
        is_active=form.get("is_active") == "on",
    )
    db.add(campaign)
    db.flush()

    owned_lp_ids = {lp.id for lp in db.query(LandingPage.id).filter(LandingPage.user_id == current_user.id)}
    owned_offer_ids = {o.id for o in db.query(Offer.id).filter(Offer.user_id == current_user.id)}
    _apply_variants(db, campaign, form, "lp_weight_", CampaignLandingPage, "landing_page_id", owned_lp_ids)
    offer_count = _apply_variants(db, campaign, form, "offer_weight_", CampaignOffer, "offer_id", owned_offer_ids)

    if offer_count == 0:
        db.rollback()
        raise HTTPException(status_code=400, detail="At least one offer needs a weight greater than 0")

    db.commit()
    return RedirectResponse(url="/campaigns?msg=Campaign created", status_code=303)


@router.get("/{campaign_id}")
def campaign_detail(campaign_id: int, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    campaign = (
        db.query(Campaign)
        .options(
            joinedload(Campaign.campaign_landing_pages).joinedload(CampaignLandingPage.landing_page),
            joinedload(Campaign.campaign_offers).joinedload(CampaignOffer.offer),
            joinedload(Campaign.tracking_domain),
        )
        .filter(Campaign.id == campaign_id, Campaign.user_id == current_user.id)
        .first()
    )
    if not campaign:
        raise HTTPException(status_code=404)
    stats = _campaign_stats(db, campaign)
    recent_clicks = (
        db.query(Click)
        .filter(Click.campaign_id == campaign_id)
        .order_by(Click.created_at.desc())
        .limit(50)
        .all()
    )
    recent_conversions = (
        db.query(Conversion)
        .join(Click, Conversion.click_id == Click.id)
        .filter(Click.campaign_id == campaign_id)
        .order_by(Conversion.created_at.desc())
        .limit(50)
        .all()
    )

    all_clicks = (
        db.query(Click)
        .options(joinedload(Click.offer), joinedload(Click.landing_page))
        .filter(Click.campaign_id == campaign_id, *COUNTABLE_CLICK_FILTER)
        .all()
    )
    offer_rows, _ = aggregate_clicks(
        db, all_clicks, lambda c: c.offer.name if c.offer else "(unknown offer)"
    )
    lp_rows = None
    if campaign.campaign_landing_pages:
        lp_rows, _ = aggregate_clicks(
            db, all_clicks, lambda c: c.landing_page.name if c.landing_page else "(direct to offer)"
        )

    excluded_count = (
        db.query(func.count(Click.id))
        .filter(Click.campaign_id == campaign_id, (Click.is_bot.is_(True)) | (Click.is_duplicate.is_(True)))
        .scalar()
        or 0
    )

    return templates.TemplateResponse(
        "campaigns/detail.html",
        {
            "request": request,
            "campaign": campaign,
            "stats": stats,
            "recent_clicks": recent_clicks,
            "recent_conversions": recent_conversions,
            "offer_rows": offer_rows,
            "lp_rows": lp_rows,
            "excluded_count": excluded_count,
            "base_url": campaign.tracking_domain.domain if campaign.tracking_domain else BASE_URL,
        },
    )


@router.get("/{campaign_id}/edit")
def edit_campaign_form(campaign_id: int, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    campaign = (
        db.query(Campaign)
        .options(
            joinedload(Campaign.campaign_landing_pages),
            joinedload(Campaign.campaign_offers),
        )
        .filter(Campaign.id == campaign_id, Campaign.user_id == current_user.id)
        .first()
    )
    if not campaign:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(
        "campaigns/form.html",
        {
            "request": request,
            "campaign": campaign,
            "traffic_sources": db.query(TrafficSource).filter(TrafficSource.user_id == current_user.id).order_by(TrafficSource.name).all(),
            "landing_pages": db.query(LandingPage).filter(LandingPage.user_id == current_user.id).order_by(LandingPage.name).all(),
            "offers": db.query(Offer).filter(Offer.user_id == current_user.id).order_by(Offer.name).all(),
            "tracking_domains": db.query(TrackingDomain).filter(TrackingDomain.user_id == current_user.id).order_by(TrackingDomain.domain).all(),
            "existing_lp_weights": {clp.landing_page_id: clp.weight for clp in campaign.campaign_landing_pages},
            "existing_offer_weights": {co.offer_id: co.weight for co in campaign.campaign_offers},
        },
    )


@router.post("/{campaign_id}/edit")
async def update_campaign(campaign_id: int, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id, Campaign.user_id == current_user.id).first()
    if not campaign:
        raise HTTPException(status_code=404)

    form = await request.form()

    traffic_source_id = int(form.get("traffic_source_id"))
    if not db.query(TrafficSource).filter(
        TrafficSource.id == traffic_source_id, TrafficSource.user_id == current_user.id
    ).first():
        raise HTTPException(status_code=400, detail="Unknown traffic source")

    tracking_domain_id = form.get("tracking_domain_id") or ""
    if tracking_domain_id and not db.query(TrackingDomain).filter(
        TrackingDomain.id == int(tracking_domain_id), TrackingDomain.user_id == current_user.id
    ).first():
        raise HTTPException(status_code=400, detail="Unknown tracking domain")

    cost_override = form.get("cost_override") or ""
    bot_redirect_url = form.get("bot_redirect_url") or ""
    campaign.name = form.get("name", "").strip()
    campaign.traffic_source_id = traffic_source_id
    campaign.tracking_domain_id = int(tracking_domain_id) if tracking_domain_id else None
    campaign.cost_override = float(cost_override) if cost_override else None
    campaign.bot_redirect_url = bot_redirect_url or None
    campaign.is_active = form.get("is_active") == "on"

    db.query(CampaignLandingPage).filter(CampaignLandingPage.campaign_id == campaign.id).delete()
    db.query(CampaignOffer).filter(CampaignOffer.campaign_id == campaign.id).delete()
    db.flush()

    owned_lp_ids = {lp.id for lp in db.query(LandingPage.id).filter(LandingPage.user_id == current_user.id)}
    owned_offer_ids = {o.id for o in db.query(Offer.id).filter(Offer.user_id == current_user.id)}
    _apply_variants(db, campaign, form, "lp_weight_", CampaignLandingPage, "landing_page_id", owned_lp_ids)
    offer_count = _apply_variants(db, campaign, form, "offer_weight_", CampaignOffer, "offer_id", owned_offer_ids)

    if offer_count == 0:
        db.rollback()
        raise HTTPException(status_code=400, detail="At least one offer needs a weight greater than 0")

    db.commit()
    return RedirectResponse(url=f"/campaigns/{campaign_id}?msg=Campaign updated", status_code=303)


@router.get("/{campaign_id}/delete")
def delete_campaign(campaign_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id, Campaign.user_id == current_user.id).first()
    if campaign:
        delete_campaign_cascade(db, campaign)
        db.commit()
    return RedirectResponse(url="/campaigns?msg=Campaign deleted", status_code=303)
