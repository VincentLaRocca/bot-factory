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
from .sinks import JsonlSink, LeadBoardSink, SlackSink
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


def build_listener(spec: Dict[str, Any], store: SeenStore, fetcher: Optional[Fetch] = None):
    from .listeners.email import EmailListener
    from .listeners.feeds import FeedListener
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
            max_messages=int(spec.get("max_messages", 50)), port=int(spec.get("port", 993)), store=store)
    if kind == "feed":
        return FeedListener.from_config(name, spec, fetcher=fetcher)
    raise ValueError(f"unknown listener kind {kind!r} for {name}")


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

    specs = [s for s in config.get("listeners", []) if s.get("enabled", True)]
    if only:
        specs = [s for s in specs if s["name"] in only]
    source_rules = {s["name"]: s["rules"] for s in config.get("listeners", []) if s.get("rules")}
    pipeline = Pipeline(store, rules, sinks, source_rules=source_rules, dry_run=dry_run)

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
