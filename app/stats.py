from collections import defaultdict
from typing import Callable

from sqlalchemy.orm import Query, Session

from app.models import Click, Conversion

# Applied everywhere clicks are counted for stats/cost — bot and duplicate clicks are
# still recorded (for audit) but must never inflate numbers. Not applied to raw click
# logs, which intentionally show everything.
COUNTABLE_CLICK_FILTER = (Click.is_bot.is_(False), Click.is_duplicate.is_(False))


def countable(query: Query) -> Query:
    return query.filter(*COUNTABLE_CLICK_FILTER)


def aggregate_clicks(db: Session, clicks: list[Click], key_fn: Callable[[Click], str]) -> tuple[list[dict], dict]:
    """Group clicks (and their conversions) by key_fn, returning per-key rows and a totals row."""
    conv_by_click: dict = defaultdict(list)
    if clicks:
        click_ids = [c.id for c in clicks]
        conversions = db.query(Conversion).filter(Conversion.click_id.in_(click_ids)).all()
        for conv in conversions:
            conv_by_click[conv.click_id].append(conv)

    buckets: dict = defaultdict(lambda: {"clicks": 0, "conversions": 0, "cost": 0.0, "revenue": 0.0})
    for click in clicks:
        key = key_fn(click)
        bucket = buckets[key]
        bucket["clicks"] += 1
        bucket["cost"] += click.campaign.cost_per_click
        for conv in conv_by_click.get(click.id, []):
            bucket["conversions"] += 1
            bucket["revenue"] += conv.payout

    rows = []
    totals = {"clicks": 0, "conversions": 0, "cost": 0.0, "revenue": 0.0}
    for key, bucket in buckets.items():
        profit = bucket["revenue"] - bucket["cost"]
        cvr = (bucket["conversions"] / bucket["clicks"] * 100) if bucket["clicks"] else 0.0
        roi = (profit / bucket["cost"] * 100) if bucket["cost"] else (100.0 if bucket["revenue"] else 0.0)
        rows.append({"key": key, **bucket, "profit": profit, "cvr": cvr, "roi": roi})
        totals["clicks"] += bucket["clicks"]
        totals["conversions"] += bucket["conversions"]
        totals["cost"] += bucket["cost"]
        totals["revenue"] += bucket["revenue"]
    rows.sort(key=lambda r: r["clicks"], reverse=True)

    totals["profit"] = totals["revenue"] - totals["cost"]
    totals["cvr"] = (totals["conversions"] / totals["clicks"] * 100) if totals["clicks"] else 0.0
    totals["roi"] = (
        (totals["profit"] / totals["cost"] * 100)
        if totals["cost"]
        else (100.0 if totals["revenue"] else 0.0)
    )
    return rows, totals
