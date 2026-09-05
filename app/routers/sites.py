import io
import zipfile
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.charts import build_trend_chart
from app.config import BASE_URL
from app.database import get_db
from app.models import PageView, Site, User

router = APIRouter(prefix="/sites", tags=["sites"])
templates = Jinja2Templates(directory="app/templates")

COLOR_VIEWS = "#4f46e5"

# Bot traffic (scripts, uptime monitors, crawlers) is still recorded for audit but
# must never inflate a site's visitor numbers.
COUNTABLE_VIEW_FILTER = (PageView.is_bot.is_(False),)

# A visitor is "online now" if their last recorded page view is within this window.
LIVE_WINDOW_SECONDS = 300


def _parse_date(value: str | None, fallback: date) -> date:
    if not value:
        return fallback
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return fallback


def _get_owned_site(db: Session, site_id: int, user_id: int) -> Site:
    site = db.query(Site).filter(Site.id == site_id, Site.user_id == user_id).first()
    if not site:
        raise HTTPException(status_code=404)
    return site


def _views_today(db: Session, site_id: int) -> int:
    start_of_day = datetime.combine(datetime.now(timezone.utc).date(), time.min, tzinfo=timezone.utc)
    return (
        db.query(func.count(PageView.id))
        .filter(PageView.site_id == site_id, PageView.created_at >= start_of_day, *COUNTABLE_VIEW_FILTER)
        .scalar()
        or 0
    )


def _online_now(db: Session, site_id: int) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=LIVE_WINDOW_SECONDS)
    return (
        db.query(func.count(func.distinct(PageView.visitor_hash)))
        .filter(PageView.site_id == site_id, PageView.created_at >= cutoff, *COUNTABLE_VIEW_FILTER)
        .scalar()
        or 0
    )


def _aggregate(views: list[PageView], key_fn) -> list[dict]:
    buckets: dict[str, dict] = defaultdict(lambda: {"views": 0, "visitors": set()})
    for view in views:
        bucket = buckets[key_fn(view)]
        bucket["views"] += 1
        bucket["visitors"].add(view.visitor_hash)
    rows = [
        {"key": key, "views": b["views"], "visitors": len(b["visitors"])}
        for key, b in buckets.items()
    ]
    rows.sort(key=lambda r: r["views"], reverse=True)
    return rows[:15]


@router.get("")
def list_sites(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    sites = db.query(Site).filter(Site.user_id == current_user.id).order_by(Site.name).all()
    views_today = {s.id: _views_today(db, s.id) for s in sites}
    online_now = {s.id: _online_now(db, s.id) for s in sites}
    return templates.TemplateResponse(
        "sites/list.html",
        {
            "request": request,
            "sites": sites,
            "views_today": views_today,
            "online_now": online_now,
            "base_url": BASE_URL,
        },
    )


@router.get("/new")
def new_site_form(request: Request, current_user: User = Depends(get_current_user)):
    return templates.TemplateResponse("sites/form.html", {"request": request, "site": None})


@router.post("/new")
def create_site(
    name: str = Form(...),
    domain: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    site = Site(user_id=current_user.id, name=name, domain=domain)
    db.add(site)
    db.commit()
    return RedirectResponse(url="/sites?msg=Site added", status_code=303)


@router.get("/{site_id}/edit")
def edit_site_form(
    site_id: int, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    site = _get_owned_site(db, site_id, current_user.id)
    return templates.TemplateResponse("sites/form.html", {"request": request, "site": site})


@router.post("/{site_id}/edit")
def update_site(
    site_id: int,
    name: str = Form(...),
    domain: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    site = _get_owned_site(db, site_id, current_user.id)
    site.name = name
    site.domain = domain
    db.commit()
    return RedirectResponse(url="/sites?msg=Site updated", status_code=303)


@router.get("/{site_id}/delete")
def delete_site(site_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    site = db.query(Site).filter(Site.id == site_id, Site.user_id == current_user.id).first()
    if site:
        db.delete(site)
        db.commit()
    return RedirectResponse(url="/sites?msg=Site deleted", status_code=303)


@router.get("/{site_id}/live.json")
def live_visitor_count(site_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    site = _get_owned_site(db, site_id, current_user.id)
    return {"online": _online_now(db, site.id)}


@router.get("/{site_id}/plugin.zip")
def download_wordpress_plugin(
    site_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    site = _get_owned_site(db, site_id, current_user.id)
    slug = "yourself-tracker"
    plugin_php = f"""<?php
/**
 * Plugin Name: YourSelf Tracker
 * Description: Sends page view analytics for this site to your YourSelf Tracker dashboard ({site.name}).
 * Version: 1.0.0
 */

if (!defined('ABSPATH')) {{
    exit;
}}

add_action('wp_footer', function () {{
    echo '<script defer src="{BASE_URL}/t.js" data-site="{site.site_key}"></script>';
}});
"""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{slug}/{slug}.php", plugin_php)
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{slug}.zip"'},
    )


@router.get("/{site_id}")
def site_detail(
    site_id: int,
    request: Request,
    start: str | None = None,
    end: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    site = _get_owned_site(db, site_id, current_user.id)

    today = datetime.now(timezone.utc).date()
    start_date = _parse_date(start, today - timedelta(days=13))
    end_date = _parse_date(end, today)
    range_start = datetime.combine(start_date, time.min, tzinfo=timezone.utc)
    range_end = datetime.combine(end_date, time.max, tzinfo=timezone.utc)

    views = (
        db.query(PageView)
        .filter(
            PageView.site_id == site.id,
            PageView.created_at >= range_start,
            PageView.created_at <= range_end,
            *COUNTABLE_VIEW_FILTER,
        )
        .all()
    )

    total_views = len(views)
    unique_visitors = len({v.visitor_hash for v in views})

    day_counts: dict[date, int] = defaultdict(int)
    for view in views:
        day_counts[view.created_at.astimezone(timezone.utc).date()] += 1
    views_series = []
    day = start_date
    while day <= end_date:
        views_series.append((day, day_counts.get(day, 0)))
        day += timedelta(days=1)

    top_pages = _aggregate(views, lambda v: v.url)
    top_referrers = _aggregate(views, lambda v: v.referrer or "(direct)")
    by_device = _aggregate(views, lambda v: v.device_type or "(unknown)")
    by_country = _aggregate(views, lambda v: v.country or "(unknown)")

    excluded_count = (
        db.query(func.count(PageView.id))
        .filter(
            PageView.site_id == site.id,
            PageView.created_at >= range_start,
            PageView.created_at <= range_end,
            PageView.is_bot.is_(True),
        )
        .scalar()
        or 0
    )

    return templates.TemplateResponse(
        "sites/detail.html",
        {
            "request": request,
            "site": site,
            "base_url": BASE_URL,
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
            "total_views": total_views,
            "unique_visitors": unique_visitors,
            "online_now": _online_now(db, site.id),
            "views_chart_svg": build_trend_chart(views_series, COLOR_VIEWS),
            "top_pages": top_pages,
            "top_referrers": top_referrers,
            "by_device": by_device,
            "by_country": by_country,
            "excluded_count": excluded_count,
        },
    )
