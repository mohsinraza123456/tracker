import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse, RedirectResponse, Response
from sqlalchemy.orm import Session, joinedload

from app.config import DEDUPE_WINDOW_SECONDS
from app.database import get_db
from app.enrichment import lookup_geo, parse_user_agent
from app.models import Campaign, Click, Conversion
from app.utils import TRANSPARENT_GIF, build_redirect_url, weighted_choice

router = APIRouter(tags=["tracking"])


@router.get("/click/{campaign_id}")
def track_click(campaign_id: int, request: Request, db: Session = Depends(get_db)):
    campaign = (
        db.query(Campaign)
        .options(
            joinedload(Campaign.campaign_offers),
            joinedload(Campaign.campaign_landing_pages),
        )
        .filter(Campaign.id == campaign_id)
        .first()
    )
    if not campaign or not campaign.is_active:
        raise HTTPException(status_code=404, detail="Unknown or inactive campaign")

    params = request.query_params
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    geo = lookup_geo(ip_address)
    ua_info = parse_user_agent(user_agent)

    # Same campaign+IP+UA within the dedupe window = a double-click/reload/retry, not a
    # new visitor. Reuse whichever variant that prior click already got, so a real person
    # double-clicking doesn't get bounced between two different offers.
    prior_click = None
    if ip_address and user_agent:
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=DEDUPE_WINDOW_SECONDS)
        prior_click = (
            db.query(Click)
            .filter(
                Click.campaign_id == campaign.id,
                Click.ip_address == ip_address,
                Click.user_agent == user_agent,
                Click.created_at >= cutoff,
            )
            .order_by(Click.created_at.desc())
            .first()
        )

    if prior_click:
        offer_id = prior_click.offer_id
        landing_page_id = prior_click.landing_page_id
    else:
        offer_id = weighted_choice([(co.offer_id, co.weight) for co in campaign.campaign_offers])
        if offer_id is None:
            raise HTTPException(status_code=404, detail="Campaign has no offers configured")
        landing_page_id = weighted_choice(
            [(clp.landing_page_id, clp.weight) for clp in campaign.campaign_landing_pages]
        )

    click = Click(
        campaign_id=campaign.id,
        offer_id=offer_id,
        landing_page_id=landing_page_id,
        ip_address=ip_address,
        user_agent=user_agent,
        referrer=request.headers.get("referer"),
        country=geo["country"],
        region=geo["region"],
        city=geo["city"],
        device_type=ua_info["device_type"],
        os=ua_info["os"],
        browser=ua_info["browser"],
        sub1=params.get("sub1"),
        sub2=params.get("sub2"),
        sub3=params.get("sub3"),
        sub4=params.get("sub4"),
        sub5=params.get("sub5"),
        is_bot=ua_info["is_bot"],
        is_duplicate=prior_click is not None,
    )
    db.add(click)
    db.commit()
    db.refresh(click)

    if click.landing_page:
        destination = build_redirect_url(click.landing_page.url, str(click.id))
    else:
        destination = build_redirect_url(click.offer.url, str(click.id))

    return RedirectResponse(url=destination, status_code=302)


@router.get("/go/{click_id}")
def continue_to_offer(click_id: uuid.UUID, db: Session = Depends(get_db)):
    """Used by a landing page to hand the visitor off to the offer that was chosen for this click."""
    click = db.get(Click, click_id)
    if not click or not click.offer:
        raise HTTPException(status_code=404, detail="Unknown click id")

    destination = build_redirect_url(click.offer.url, str(click.id))
    return RedirectResponse(url=destination, status_code=302)


def _record_conversion(
    db: Session, click_id: uuid.UUID, payout: float | None, external_id: str | None
) -> Conversion | None:
    click = db.get(Click, click_id)
    if not click:
        return None

    if external_id:
        existing = (
            db.query(Conversion)
            .filter(Conversion.click_id == click_id, Conversion.external_id == external_id)
            .first()
        )
        if existing:
            return existing

    resolved_payout = payout if payout is not None else (click.offer.payout if click.offer else 0.0)
    conversion = Conversion(
        click_id=click_id,
        payout=resolved_payout,
        external_id=external_id,
    )
    db.add(conversion)
    db.commit()
    db.refresh(conversion)
    return conversion


@router.get("/conv/{click_id}")
def track_conversion_pixel(
    click_id: uuid.UUID,
    payout: float | None = None,
    txid: str | None = None,
    db: Session = Depends(get_db),
):
    _record_conversion(db, click_id, payout, txid)
    return Response(content=TRANSPARENT_GIF, media_type="image/gif")


@router.get("/postback")
def track_conversion_postback(
    clickid: uuid.UUID,
    payout: float | None = None,
    txid: str | None = None,
    db: Session = Depends(get_db),
):
    conversion = _record_conversion(db, clickid, payout, txid)
    if not conversion:
        return PlainTextResponse("ERROR: unknown click id", status_code=404)
    return PlainTextResponse("OK")
