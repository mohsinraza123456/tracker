import ipaddress

import requests
from user_agents import parse as parse_user_agent_string

_geo_cache: dict[str, dict] = {}


def lookup_geo(ip: str | None) -> dict:
    """Best-effort IP geolocation via ip-api.com. Never raises; returns Nones on failure."""
    empty = {"country": None, "region": None, "city": None}
    if not ip:
        return empty

    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return empty

    if addr.is_private or addr.is_loopback or addr.is_reserved:
        return {"country": "Local", "region": None, "city": None}

    if ip in _geo_cache:
        return _geo_cache[ip]

    result = empty
    try:
        resp = requests.get(
            f"http://ip-api.com/json/{ip}",
            params={"fields": "status,country,regionName,city"},
            timeout=2,
        )
        data = resp.json()
        if data.get("status") == "success":
            result = {
                "country": data.get("country"),
                "region": data.get("regionName"),
                "city": data.get("city"),
            }
    except requests.RequestException:
        pass

    _geo_cache[ip] = result
    return result


BOT_KEYWORDS = (
    "bot", "crawl", "spider", "slurp", "curl", "wget", "python-requests",
    "python-urllib", "scrapy", "httpclient", "headlesschrome", "phantomjs",
    "facebookexternalhit", "monitor", "pingdom", "uptimerobot",
)


def parse_user_agent(ua_string: str | None) -> dict:
    # No User-Agent at all is a strong bot/script signal — real browsers always send one.
    if not ua_string:
        return {"device_type": None, "os": None, "browser": None, "is_bot": True}

    ua = parse_user_agent_string(ua_string)
    if ua.is_mobile:
        device_type = "Mobile"
    elif ua.is_tablet:
        device_type = "Tablet"
    elif ua.is_pc:
        device_type = "Desktop"
    else:
        device_type = "Other"

    is_bot = ua.is_bot or any(kw in ua_string.lower() for kw in BOT_KEYWORDS)

    return {
        "device_type": device_type,
        "os": ua.os.family or None,
        "browser": ua.browser.family or None,
        "is_bot": is_bot,
    }
