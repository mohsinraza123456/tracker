import random
from typing import TypeVar
from urllib.parse import urlencode, urlparse, parse_qsl, urlunparse

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


def build_redirect_url(target_url: str, click_id: str) -> str:
    """Append the click id to a destination URL so it can be echoed back on conversion.

    If the URL contains a literal "{clickid}" token, substitute it in place
    (useful when an offer requires the id inside the path). Otherwise append
    it as a `clickid` query parameter.
    """
    if "{clickid}" in target_url:
        return target_url.replace("{clickid}", click_id)

    parsed = urlparse(target_url)
    query = dict(parse_qsl(parsed.query))
    query["clickid"] = click_id
    new_query = urlencode(query)
    return urlunparse(parsed._replace(query=new_query))


TRANSPARENT_GIF = bytes.fromhex(
    "47494638396101000100800000000000ffffff21f90401000000002c00000000010001000002024401003b"
)
