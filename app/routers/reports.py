from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import Campaign, Click
from app.stats import COUNTABLE_CLICK_FILTER, aggregate_clicks

router = APIRouter(prefix="/reports", tags=["reports"])
templates = Jinja2Templates(directory="app/templates")

DIMENSIONS = {
    "campaign": "Campaign",
    "traffic_source": "Traffic Source",
    "landing_page": "Landing Page",
    "offer": "Offer",
    "country": "Country",
    "region": "Region",
    "city": "City",
    "device_type": "Device",
    "os": "OS",
    "browser": "Browser",
    "sub1": "Sub1",
}


def _parse_date(value: str | None, fallback: date) -> date:
    if not value:
        return fallback
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return fallback


def _dimension_key(click: Click, dimension: str) -> str:
    if dimension == "campaign":
        return click.campaign.name
    if dimension == "traffic_source":
        return click.campaign.traffic_source.name
    if dimension == "landing_page":
        return click.landing_page.name if click.landing_page else "(direct to offer)"
    if dimension == "offer":
        return click.offer.name if click.offer else "(unknown offer)"
    value = getattr(click, dimension, None)
    return value or "(unknown)"


@router.get("")
def reports(
    request: Request,
    dimension: str = "country",
    start: str | None = None,
    end: str | None = None,
    db: Session = Depends(get_db),
):
    if dimension not in DIMENSIONS:
        dimension = "country"

    today = datetime.now(timezone.utc).date()
    start_date = _parse_date(start, today - timedelta(days=30))
    end_date = _parse_date(end, today)
    range_start = datetime.combine(start_date, time.min, tzinfo=timezone.utc)
    range_end = datetime.combine(end_date, time.max, tzinfo=timezone.utc)

    clicks = (
        db.query(Click)
        .options(
            joinedload(Click.campaign).joinedload(Campaign.traffic_source),
            joinedload(Click.landing_page),
            joinedload(Click.offer),
        )
        .filter(Click.created_at >= range_start, Click.created_at <= range_end, *COUNTABLE_CLICK_FILTER)
        .all()
    )

    rows, totals = aggregate_clicks(db, clicks, lambda c: _dimension_key(c, dimension))

    excluded_count = (
        db.query(func.count(Click.id))
        .filter(
            Click.created_at >= range_start,
            Click.created_at <= range_end,
            (Click.is_bot.is_(True)) | (Click.is_duplicate.is_(True)),
        )
        .scalar()
        or 0
    )

    return templates.TemplateResponse(
        "reports.html",
        {
            "request": request,
            "dimensions": DIMENSIONS,
            "dimension": dimension,
            "dimension_label": DIMENSIONS[dimension],
            "rows": rows,
            "totals": totals,
            "excluded_count": excluded_count,
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
        },
    )
