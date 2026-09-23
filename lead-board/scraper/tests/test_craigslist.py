import json
from pathlib import Path

import pytest

from leadscraper.adapters.craigslist import parse
from leadscraper.models import Listing, listing_to_lead
from leadscraper import poster
from leadscraper.state import is_seen, load, mark_seen, save


FIXTURE = Path(__file__).parent / "fixtures" / "craigslist_static.html"
BASE_URL = "https://richmond.craigslist.org/search/lbg"


def test_parse_static_and_jsonld_fixture():
    listings = parse(FIXTURE.read_text(encoding="utf-8"), BASE_URL)
    assert len(listings) == 3
    by_title = {listing.title: listing for listing in listings}
    assert by_title["HVAC valves"].price == 75
    assert by_title["Tool set"].price == 0
    assert by_title["Recovery tank"].price == 1200
    assert by_title["HVAC valves"].url == (
        "https://richmond.craigslist.org/lbg/d/hvac-valves/123456.html"
    )
    assert by_title["HVAC valves"].location == "Richmond"


def test_listing_to_lead_mapping():
    listing = Listing(
        url="https://example.test/listing/1",
        title="Cargo",
        price=55,
        location="Richmond",
        posted_at="2026-09-23T12:00:00Z",
    )
    lead = listing_to_lead(listing, {"listener_channel": "Open Boards"})
    assert lead["lead_id"].startswith("CL-")
    assert len(lead["lead_id"]) == 13
    assert lead["listener_channel"] == "Open Boards"
    assert lead["source_medium"] == "Board Scraping"
    assert lead["source_contact"] == listing.url
    assert lead["origin"] == "Richmond"
    assert lead["destination"] == ""
    assert lead["cargo_summary"] == "Cargo"
    assert lead["payout_offered"] == 55
    assert lead["mileage_est"] == 0
    assert lead["urgency_level"] == "MEDIUM"
    assert lead["window_deadline"] == listing.posted_at


def test_state_prunes_old_entries(tmp_path):
    path = tmp_path / "state.json"
    state = {"seen": {"old": "2020-01-01T00:00:00Z", "new": "2099-01-01T00:00:00Z"}}
    save(str(path), state)
    loaded = load(str(path))
    assert "old" not in loaded["seen"]
    assert "new" in loaded["seen"]
    assert not is_seen(loaded, "missing")
    mark_seen(loaded, "new-lead", "2099-01-02T00:00:00Z")
    assert is_seen(loaded, "new-lead")


def test_poster_raises_on_error(monkeypatch):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def read(self):
            return json.dumps({"status": "ERROR", "message": "bad lead"}).encode("utf-8")

    def fake_urlopen(request, timeout):
        return Response()

    monkeypatch.setattr(poster, "urlopen", fake_urlopen)
    with pytest.raises(RuntimeError, match="bad lead"):
        poster.post_lead("https://example.test/exec", {"lead_id": "x"})
