"""POST normalized leads to the Apps Script endpoint."""

import json
from urllib.request import Request, urlopen


def post_lead(api_url: str, lead: dict, timeout: int = 30) -> dict:
    request = Request(
        api_url,
        data=json.dumps(lead).encode("utf-8"),
        headers={"Content-Type": "text/plain"},
        method="POST",
    )
    with urlopen(request, timeout=timeout) as response:
        result = json.loads(response.read().decode("utf-8"))
    if result.get("status") != "SUCCESS":
        raise RuntimeError("Apps Script rejected lead: " + str(result.get("message", result)))
    return result
