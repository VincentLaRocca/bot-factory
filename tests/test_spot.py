"""Live spot feed: fills blank spot prices so the melt test works on its own.

All offline: a fake fetcher plays recorded gold-api.com replies.
"""

import json
from datetime import datetime, timezone

from leads import config as config_module
from leads.http import Response
from leads.pipeline import Pipeline
from leads.rules import RuleSet
from leads.spot import SpotFeed, resolve
from leads.store import SeenStore


class Feed:
    """Plays gold-api.com: /price/XAU and /price/XAG. Counts calls per symbol."""

    def __init__(self, gold=4185.2, silver=61.14, fail=False):
        self.prices = {"XAU": gold, "XAG": silver}
        self.fail = fail
        self.calls = []

    def __call__(self, url, method="GET", data=None, headers=None, **_):
        self.calls.append(url)
        if url.startswith("https://api.gold-api.com/price/"):
            if self.fail:
                raise OSError("feed down")
            symbol = url.rsplit("/", 1)[1]
            return Response(200, json.dumps({"symbol": symbol, "price": self.prices[symbol]}).encode(), {})
        if url.startswith("https://api.ebay.com/identity"):
            return Response(200, b'{"access_token": "T", "expires_in": 7200}', {})
        if url.startswith("https://api.ebay.com/buy/browse"):
            item = {"itemId": "v1|9|0", "title": "14k gold chain 20 grams", "itemWebUrl": "https://ebay.com/itm/9",
                    "price": {"value": "600.00", "currency": "USD"},
                    "shippingOptions": [{"shippingCost": {"value": "10.00"}}],
                    "buyingOptions": ["FIXED_PRICE"], "condition": "Pre-owned",
                    "itemLocation": {"postalCode": "232**", "country": "US"},
                    "categories": [{"categoryName": "Fine Necklaces & Pendants"}]}
            return Response(200, json.dumps({"itemSummaries": [item]}).encode(), {})
        return Response(200, b"{}", {})


class Clock:
    def __init__(self, t=1_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


def test_blank_spot_fills_live(tmp_path):
    web = Feed()
    spot, source = resolve({"gold": "", "silver": ""}, SpotFeed(web, cache_path=str(tmp_path / "s.json")))
    assert spot == {"gold": 4185.2, "silver": 61.14}
    assert source == {"gold": "live", "silver": "live"}


def test_hand_set_wins_and_skips_the_call(tmp_path):
    web = Feed()
    spot, source = resolve({"gold": "4000", "silver": ""}, SpotFeed(web, cache_path=str(tmp_path / "s.json")))
    assert spot == {"gold": 4000.0, "silver": 61.14}
    assert source["gold"] == "set by hand"
    assert all("XAU" not in url for url in web.calls)      # no call for a metal Vinny set


def test_cache_means_one_call_per_ttl(tmp_path):
    web, clock = Feed(), Clock()
    feed = SpotFeed(web, cache_path=str(tmp_path / "s.json"), ttl_minutes=15, clock=clock)
    feed.prices()
    clock.t += 10 * 60
    SpotFeed(web, cache_path=str(tmp_path / "s.json"), ttl_minutes=15, clock=clock).prices()
    assert len(web.calls) == 2                               # gold + silver once, then cached
    clock.t += 10 * 60
    SpotFeed(web, cache_path=str(tmp_path / "s.json"), ttl_minutes=15, clock=clock).prices()
    assert len(web.calls) == 4                               # past TTL: refreshed


def test_feed_down_uses_stale_then_gives_up(tmp_path):
    path, clock = str(tmp_path / "s.json"), Clock()
    SpotFeed(Feed(), cache_path=path, clock=clock).prices()
    clock.t += 3 * 3600
    down = SpotFeed(Feed(fail=True), cache_path=path, clock=clock)
    assert down.prices() == {"gold": 4185.2, "silver": 61.14}
    assert down.notes["gold"].startswith("stale")
    clock.t += 30 * 3600
    gone = SpotFeed(Feed(fail=True), cache_path=path, clock=clock)
    assert gone.prices() == {}
    assert gone.notes["gold"] == "unavailable"


def test_bad_tick_is_rejected(tmp_path):
    feed = SpotFeed(Feed(gold=40.0, silver=61.14), cache_path=str(tmp_path / "s.json"))
    assert feed.prices() == {"silver": 61.14}               # $40 gold would flag every chain


def test_off_switch(monkeypatch, tmp_path):
    from leads.spot import feed_from_config
    monkeypatch.setenv("SPOT_FEED", "off")
    assert feed_from_config({}) is None
    monkeypatch.setenv("SPOT_FEED", "")
    assert feed_from_config({"spot_feed": {"enabled": False}}) is None
    assert feed_from_config({"spot_feed": {"cache": str(tmp_path / "x.json")}}) is not None


def test_config_to_flag_with_live_spot(monkeypatch, tmp_path):
    """Nothing set by hand: live gold prices a 20 g 14k chain at ~$1,574 melt
    against $610 all-in, and it routes."""
    monkeypatch.setenv("SPOT_FEED", "")
    web = Feed()
    config = {"spot_feed": {"cache": str(tmp_path / "spot.json")},
              "listeners": [{"name": "ebay-jewelry", "kind": "ebay", "client_id": "id", "client_secret": "s",
                             "queries": [{"hunt": "jewelry", "q": "14k gold chain"}],
                             "spot": {"gold": "", "silver": ""}}]}
    system = config_module.build(config, fetcher=web, store_path=str(tmp_path / "l.db"))
    assert config["_spot_source"] == {"gold": "live", "silver": "live"}
    hunt = system.listeners[0]
    assert hunt.spot["gold"] == 4185.2
    hunt.now = datetime(2026, 10, 1, 7, tzinfo=timezone.utc)
    found = list(hunt.listen())
    assert found and "melt $1,574" in found[0].body
    routed = Pipeline(SeenStore(), RuleSet.from_config({"min_score": 45}), []).process(found).routed
    assert [x.external_id for x in routed] == [found[0].external_id]
