"""Config → a running system. JSON (stdlib), with ``${ENV_VAR}`` expansion so
secrets live in the environment / GitHub Secrets, never in the file."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .http import Fetch
from .pipeline import Pipeline
from .rules import RuleSet
from .sinks import JsonlSink, LeadBoardSink, SlackSink, WebhookSink
from .store import SeenStore

_VAR = re.compile(r"\$\{([A-Z0-9_]+)(?::-([^}]*))?\}")


def expand(value: Any) -> Any:
    if isinstance(value, str):
        return _VAR.sub(lambda m: os.environ.get(m.group(1), m.group(2) or ""), value)
    if isinstance(value, list):
        return [expand(v) for v in value]
    if isinstance(value, dict):
        return {k: expand(v) for k, v in value.items()}
    return value


def load(path: str) -> Dict[str, Any]:
    with open(path, encoding="utf-8") as handle:
        return expand(json.load(handle))


@dataclass
class System:
    config: Dict[str, Any]
    store: SeenStore
    pipeline: Pipeline
    listeners: List[Any]
    skipped: List[Tuple[str, str]]
    webhook: Optional[Dict[str, Any]]


def _recovery(spec: Dict[str, Any]):
    from .valuation import Recovery
    return Recovery.from_config(dict(spec.get("recovery") or {}))


def build_listener(spec: Dict[str, Any], store: SeenStore, fetcher: Optional[Fetch] = None):
    from .listeners.email import EmailListener
    from .listeners.feeds import FeedListener
    from .listeners.reddit_threads import RedditThreadListener
    from .listeners.ebay import EbayHuntListener
    from .listeners.gsa_auctions import GsaAuctionsListener
    from .listeners.sam import SamListener

    kind, name = spec.get("kind"), spec["name"]
    if kind == "sam":
        return SamListener(
            name, spec.get("api_key", ""), naics=spec.get("naics", []), set_asides=spec.get("set_asides", []),
            states=spec.get("states"), ptypes=spec.get("ptypes"), lookback_days=int(spec.get("lookback_days", 3)),
            page_size=int(spec.get("page_size", 100)), max_pages=int(spec.get("max_pages", 3)), fetcher=fetcher)
    if kind == "email":
        return EmailListener(
            name, spec.get("host", "imap.gmail.com"), spec.get("user", ""), spec.get("password", ""),
            folder=spec.get("folder", "INBOX"), only_from=spec.get("only_from"),
            max_messages=int(spec.get("max_messages", 50)), port=int(spec.get("port", 993)), store=store,
            channel=spec.get("channel", "Commercial / B2B"), tags=spec.get("tags"),
            skip_from=spec.get("skip_from"), spot=spec.get("spot"), decipher=bool(spec.get("decipher", False)))
    if kind == "ebay_watch":
        return EbayHuntListener.for_watches(
            name, spec.get("client_id", ""), spec.get("client_secret", ""), watch_file=spec.get("watch_file") or None,
            spot=spec.get("spot"), fetcher=fetcher, recovery=_recovery(spec))
    if kind == "ebay":
        return EbayHuntListener(
            name, spec.get("client_id", ""), spec.get("client_secret", ""), spec.get("queries", []),
            spot=spec.get("spot"), margin=float(spec.get("margin", 0.10)), max_ppc=spec.get("max_price_per_carat"),
            limit=int(spec.get("limit", 100)), fetcher=fetcher,
            recovery=_recovery(spec))
    if kind == "gsa_auctions":
        return GsaAuctionsListener(name, spec.get("api_key", "DEMO_KEY"), states=spec.get("states"),
                                   spot=spec.get("spot"), margin=float(spec.get("margin", 0.10)), fetcher=fetcher,
                                   recovery=_recovery(spec), appraiser=spec.get("appraiser", "auto"),
                                   scrap_per_ton=float(spec.get("scrap_per_ton") or 180),
                                   cat_value=float(spec.get("cat_value") or 100), comps_csv=spec.get("comps_csv") or None)
    if kind == "reddit_threads":
        return RedditThreadListener(
            name, spec.get("username", ""), watch_days=int(spec.get("watch_days", 7)),
            max_threads=int(spec.get("max_threads", 10)), location=spec.get("location", ""),
            fetcher=fetcher, store=store,
            subreddits=spec["subreddits"].split(",") if isinstance(spec.get("subreddits"), str) else spec.get("subreddits"),
            follow_user=bool(spec.get("follow_user", True)), tags=spec.get("tags"))
    if kind == "feed":
        return FeedListener.from_config(name, spec, fetcher=fetcher)
    raise ValueError(f"unknown listener kind {kind!r} for {name}")


def _fill_spot(config: Dict[str, Any], specs: List[Dict[str, Any]],
               fetcher: Optional[Fetch]) -> List[Dict[str, Any]]:
    """Blank spot prices get filled from the live feed; hand-set ones stay.
    One feed (and at most one call per metal) for the whole sweep."""
    if not any("spot" in s for s in specs):
        return specs
    from .spot import feed_from_config, resolve
    feed = feed_from_config(config, fetcher)
    filled, merged = [], None
    for spec in specs:
        if "spot" in spec:
            spot, source = resolve(spec.get("spot"), feed)
            spec = dict(spec, spot=spot, spot_source=source)
            merged = merged or source
        filled.append(spec)
    config.setdefault("_spot_source", merged or {})
    return filled


def build(config: Dict[str, Any], dry_run: bool = False, only: Optional[List[str]] = None,
          fetcher: Optional[Fetch] = None, store_path: Optional[str] = None) -> System:
    store = SeenStore(store_path or config.get("store", "var/leads.db"))
    rules = RuleSet.from_config(config.get("rules"))

    sinks = []
    sink_cfg = config.get("sinks", {})
    if config.get("ledger"):
        sinks.append(JsonlSink(config["ledger"]))
    board = (sink_cfg.get("lead_board") or {}).get("url")
    if board:
        sinks.append(LeadBoardSink(board, fetcher))
    slack = sink_cfg.get("slack") or {}
    if slack.get("url"):
        sinks.append(SlackSink(slack["url"], slack.get("min_urgency", "HIGH"), fetcher))

    for hook in sink_cfg.get("webhooks", []):
        if hook.get("url") and hook.get("enabled", True):
            sinks.append(WebhookSink(hook.get("name", "webhook"), hook["url"], hook.get("token", ""),
                                     hook.get("shape", "board"), hook.get("min_urgency", "LOW"), fetcher))

    specs = [s for s in config.get("listeners", []) if s.get("enabled", True)]
    if only:
        specs = [s for s in specs if s["name"] in only]
    source_rules = {s["name"]: s["rules"] for s in config.get("listeners", []) if s.get("rules")}
    pipeline = Pipeline(store, rules, sinks, source_rules=source_rules, dry_run=dry_run)

    specs = _fill_spot(config, specs, fetcher)

    listeners, skipped, webhook = [], [], None
    for spec in specs:
        if spec.get("kind") == "webhook":
            webhook = spec
            continue
        try:
            listener = build_listener(spec, store, fetcher)
            listener.min_interval = int(spec.get("min_interval_minutes", 0))
            listeners.append(listener)
        except ValueError as error:  # missing credentials: skip, don't crash the sweep
            skipped.append((spec["name"], str(error)))
    return System(config, store, pipeline, listeners, skipped, webhook)
