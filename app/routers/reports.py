import csv
import io
from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
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


def _resolve_range(start: str | None, end: str | None) -> tuple[date, date, datetime, datetime]:
    today = datetime.now(timezone.utc).date()
    start_date = _parse_date(start, today - timedelta(days=30))
    end_date = _parse_date(end, today)
    range_start = datetime.combine(start_date, time.min, tzinfo=timezone.utc)
    range_end = datetime.combine(end_date, time.max, tzinfo=timezone.utc)
    return start_date, end_date, range_start, range_end


def _build_report(db: Session, dimension: str, range_start: datetime, range_end: datetime):
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
    return rows, totals, excluded_count


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

    start_date, end_date, range_start, range_end = _resolve_range(start, end)
    rows, totals, excluded_count = _build_report(db, dimension, range_start, range_end)

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


@router.get("/export.csv")
def export_report_csv(
    dimension: str = "country",
    start: str | None = None,
    end: str | None = None,
    db: Session = Depends(get_db),
):
    if dimension not in DIMENSIONS:
        dimension = "country"

    start_date, end_date, range_start, range_end = _resolve_range(start, end)
    rows, totals, _ = _build_report(db, dimension, range_start, range_end)

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [DIMENSIONS[dimension], "Clicks", "Conversions", "Conv. Rate (%)", "Cost", "Revenue", "Profit", "ROI (%)"]
    )
    for row in rows:
        writer.writerow(
            [
                row["key"],
                row["clicks"],
                row["conversions"],
                f"{row['cvr']:.2f}",
                f"{row['cost']:.2f}",
                f"{row['revenue']:.2f}",
                f"{row['profit']:.2f}",
                f"{row['roi']:.1f}",
            ]
        )
    writer.writerow(
        [
            "Total",
            totals["clicks"],
            totals["conversions"],
            f"{totals['cvr']:.2f}",
            f"{totals['cost']:.2f}",
            f"{totals['revenue']:.2f}",
            f"{totals['profit']:.2f}",
            f"{totals['roi']:.1f}",
        ]
    )
    buffer.seek(0)

    filename = f"report-{dimension}-{start_date.isoformat()}_{end_date.isoformat()}.csv"
    return StreamingResponse(
        buffer,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
