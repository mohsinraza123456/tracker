from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.enrichment import lookup_geo, parse_user_agent
from app.models import PageView, Site
from app.utils import TRANSPARENT_GIF, visitor_hash

router = APIRouter(tags=["collect"])

TRACKER_JS = """(function () {
  var script = document.currentScript;
  var siteKey = script.getAttribute('data-site');
  if (!siteKey) return;
  var base = script.src.slice(0, script.src.lastIndexOf('/'));
  var params = [
    'site=' + encodeURIComponent(siteKey),
    'url=' + encodeURIComponent(location.pathname + location.search),
    'ref=' + encodeURIComponent(document.referrer || ''),
    'title=' + encodeURIComponent(document.title || '')
  ];
  var img = new Image(1, 1);
  img.src = base + '/collect?' + params.join('&');
})();
"""


@router.get("/t.js")
def tracker_script():
    return Response(content=TRACKER_JS, media_type="application/javascript")


@router.get("/collect")
def collect_page_view(
    request: Request,
    site: str = "",
    url: str = "",
    ref: str = "",
    title: str = "",
    db: Session = Depends(get_db),
):
    # Always respond with the pixel, even for an unknown/blank site key — never let
    # this endpoint leak which keys are valid via a different status code.
    site_row = db.query(Site).filter(Site.site_key == site).first() if site else None
    if site_row:
        ip_address = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent")
        geo = lookup_geo(ip_address)
        ua_info = parse_user_agent(user_agent)
        db.add(
            PageView(
                site_id=site_row.id,
                url=(url or "/")[:2000],
                referrer=(ref or None) and ref[:2000],
                title=(title or None) and title[:500],
                visitor_hash=visitor_hash(site_row.site_key, ip_address, user_agent),
                ip_address=ip_address,
                country=geo["country"],
                region=geo["region"],
                city=geo["city"],
                device_type=ua_info["device_type"],
                os=ua_info["os"],
                browser=ua_info["browser"],
                is_bot=ua_info["is_bot"],
            )
        )
        db.commit()

    return Response(content=TRANSPARENT_GIF, media_type="image/gif")
