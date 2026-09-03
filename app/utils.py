import random
from typing import TYPE_CHECKING, TypeVar
from urllib.parse import quote, urlencode, urlparse, parse_qsl, urlunparse

if TYPE_CHECKING:
    from app.models import Click

T = TypeVar("T")


def weighted_choice(options: list[tuple[T, int]]) -> T | None:
    """Pick one item at random, proportional to its weight. Ignores non-positive weights."""
    positive = [(item, weight) for item, weight in options if weight and weight > 0]
    if not positive:
        return None
    total = sum(weight for _, weight in positive)
    r = random.uniform(0, total)
    upto = 0.0
    for item, weight in positive:
        upto += weight
        if r <= upto:
            return item
    return positive[-1][0]


def build_redirect_url(target_url: str, click: "Click") -> str:
    """Substitute {clickid} and any other {macro} tokens found in a destination URL
    with data from this click, then append clickid as a query param if {clickid}
    wasn't used explicitly.

    Available macros: {clickid}, {country}, {region}, {city}, {device}, {os},
    {browser}, {sub1}..{sub5}. Unrecognized {tokens} are left untouched.
    """
    macros = {
        "{clickid}": str(click.id),
        "{country}": click.country or "",
        "{region}": click.region or "",
        "{city}": click.city or "",
        "{device}": click.device_type or "",
        "{os}": click.os or "",
        "{browser}": click.browser or "",
        "{sub1}": click.sub1 or "",
        "{sub2}": click.sub2 or "",
        "{sub3}": click.sub3 or "",
        "{sub4}": click.sub4 or "",
        "{sub5}": click.sub5 or "",
    }

    result = target_url
    used_clickid_macro = False
    for token, value in macros.items():
        if token in result:
            result = result.replace(token, quote(value, safe=""))
            if token == "{clickid}":
                used_clickid_macro = True

    if used_clickid_macro:
        return result

    parsed = urlparse(result)
    query = dict(parse_qsl(parsed.query))
    query["clickid"] = str(click.id)
    new_query = urlencode(query)
    return urlunparse(parsed._replace(query=new_query))


TRANSPARENT_GIF = bytes.fromhex(
    "47494638396101000100800000000000ffffff21f90401000000002c00000000010001000002024401003b"
)
