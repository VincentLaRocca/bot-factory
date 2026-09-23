"""HTTP fetching for local board scrapers."""

from urllib.error import HTTPError
from urllib.request import Request, urlopen


class FetchBlocked(RuntimeError):
    """Raised when a board blocks the scraper's network location."""


def fetch(url: str, user_agent: str, timeout: int = 30) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": user_agent,
            "Accept-Language": "en-US",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(charset, errors="replace")
    except HTTPError as error:
        if error.code == 403:
            raise FetchBlocked(
                "Craigslist blocks datacenter IPs; the scraper must run from a residential connection."
            ) from error
        raise
