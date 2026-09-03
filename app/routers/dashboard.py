from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.charts import COLOR_CLICKS, COLOR_CONVERSIONS, build_trend_chart
from app.database import get_db
from app.models import Campaign, Click, Conversion, User
from app.stats import COUNTABLE_CLICK_FILTER

router = APIRouter(tags=["dashboard"])
templates = Jinja2Templates(directory="app/templates")


def _parse_date(value: str | None, fallback: date) -> date:
    if not value:
        return fallback
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return fallback


@router.get("/dashboard")
def dashboard(
    request: Request,
    start: str | None = None,
    end: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    today = datetime.now(timezone.utc).date()
    start_date = _parse_date(start, today - timedelta(days=30))
    end_date = _parse_date(end, today)

    range_start = datetime.combine(start_date, time.min, tzinfo=timezone.utc)
    range_end = datetime.combine(end_date, time.max, tzinfo=timezone.utc)

    campaigns = db.query(Campaign).filter(Campaign.user_id == current_user.id).order_by(Campaign.name).all()

    rows = []
    totals = {"clicks": 0, "conversions": 0, "cost": 0.0, "revenue": 0.0}

    for campaign in campaigns:
        clicks = (
            db.query(func.count(Click.id))
            .filter(
                Click.campaign_id == campaign.id,
                Click.created_at >= range_start,
                Click.created_at <= range_end,
                *COUNTABLE_CLICK_FILTER,
            )
            .scalar()
            or 0
        )
        conversions, revenue = (
            db.query(func.count(Conversion.id), func.coalesce(func.sum(Conversion.payout), 0.0))
            .join(Click, Conversion.click_id == Click.id)
            .filter(
                Click.campaign_id == campaign.id,
                Conversion.created_at >= range_start,
                Conversion.created_at <= range_end,
                *COUNTABLE_CLICK_FILTER,
            )
            .first()
        )
        cost = clicks * campaign.cost_per_click
        profit = revenue - cost
        cvr = (conversions / clicks * 100) if clicks else 0.0
        roi = (profit / cost * 100) if cost else (100.0 if revenue else 0.0)

        rows.append(
            {
                "campaign": campaign,
                "clicks": clicks,
                "conversions": conversions,
                "revenue": revenue,
                "cost": cost,
                "profit": profit,
                "cvr": cvr,
                "roi": roi,
            }
        )
        totals["clicks"] += clicks
        totals["conversions"] += conversions
        totals["cost"] += cost
        totals["revenue"] += revenue

    totals["profit"] = totals["revenue"] - totals["cost"]
    totals["cvr"] = (totals["conversions"] / totals["clicks"] * 100) if totals["clicks"] else 0.0
    totals["roi"] = (
        (totals["profit"] / totals["cost"] * 100)
        if totals["cost"]
        else (100.0 if totals["revenue"] else 0.0)
    )

    # Daily buckets across all campaigns, for the trend charts. Two measures of very
    # different scale (clicks vs. conversions) get two single-series charts rather
    # than one dual-axis chart.
    campaign_ids = [c.id for c in campaigns]

    click_day_counts: dict[date, int] = defaultdict(int)
    if campaign_ids:
        for (created_at,) in (
            db.query(Click.created_at)
            .filter(
                Click.campaign_id.in_(campaign_ids),
                Click.created_at >= range_start,
                Click.created_at <= range_end,
                *COUNTABLE_CLICK_FILTER,
            )
            .all()
        ):
            click_day_counts[created_at.astimezone(timezone.utc).date()] += 1

    conv_day_counts: dict[date, int] = defaultdict(int)
    if campaign_ids:
        for (created_at,) in (
            db.query(Conversion.created_at)
            .join(Click, Conversion.click_id == Click.id)
            .filter(
                Click.campaign_id.in_(campaign_ids),
                Conversion.created_at >= range_start,
                Conversion.created_at <= range_end,
                *COUNTABLE_CLICK_FILTER,
            )
            .all()
        ):
            conv_day_counts[created_at.astimezone(timezone.utc).date()] += 1

    clicks_series = []
    conversions_series = []
    day = start_date
    while day <= end_date:
        clicks_series.append((day, click_day_counts.get(day, 0)))
        conversions_series.append((day, conv_day_counts.get(day, 0)))
        day += timedelta(days=1)

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "rows": rows,
            "totals": totals,
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
            "clicks_chart_svg": build_trend_chart(clicks_series, COLOR_CLICKS),
            "conversions_chart_svg": build_trend_chart(conversions_series, COLOR_CONVERSIONS),
        },
    )
