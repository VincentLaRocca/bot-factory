"""Command line.

    python -m leads check                 which listeners are ready, which are missing keys
    python -m leads sweep [--dry-run]     run every pull listener once (bids, email, feeds)
    python -m leads loop --every 900      sweep forever, every N seconds
    python -m leads serve --port 8080     inbound lead listener (forms, Zapier, SMS)
    python -m leads recent                last routed leads from the store
    python -m leads digest [--send]       top open leads of the last 24h (Slack with --send)

Global: --config PATH (default leads.config.json, falling back to the example).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import threading
import time
from datetime import datetime, timedelta, timezone

from . import config as config_module
from .pipeline import RunReport

log = logging.getLogger("leads")
DEFAULT_CONFIG = "leads.config.json"
EXAMPLE_CONFIG = os.path.join(os.path.dirname(__file__), "config.example.json")


def _config_path(arg: str) -> str:
    if arg:
        return arg
    return DEFAULT_CONFIG if os.path.exists(DEFAULT_CONFIG) else EXAMPLE_CONFIG


def _due(system, listener, force: bool) -> bool:
    """Respect a listener's min_interval_minutes (e.g. SAM.gov's small daily quota)."""
    minutes = getattr(listener, "min_interval", 0)
    if force or not minutes:
        return True
    last = system.store.cursor(f"last_run:{listener.name}")
    if not last:
        return True
    return datetime.now(timezone.utc) - datetime.fromisoformat(last) >= timedelta(minutes=minutes)


def sweep(system, force: bool = False) -> RunReport:
    total = RunReport()
    for listener in system.listeners:
        if not _due(system, listener, force):
            log.info("%-18s not due yet (every %s min)", listener.name, listener.min_interval)
            continue
        if not system.pipeline.dry_run:
            system.store.set_cursor(f"last_run:{listener.name}", datetime.now(timezone.utc).isoformat())
        try:
            report = system.pipeline.process(listener.listen())
        except Exception as error:  # one broken source must not stop the others
            log.error("%s failed: %s", listener.name, error)
            total.errors.append(f"{listener.name}: {error}")
            continue
        report.errors += [f"{listener.name}: {e}" for e in getattr(listener, "errors", [])]
        log.info("%-18s %s", listener.name, report.summary())
        for lead in report.routed:
            log.info("  → [%s %3d] %s", lead.urgency, lead.score, lead.title[:90])
        total.merge(report)
    for name, reason in system.skipped:
        log.warning("%-18s skipped: %s", name, reason)
    return total


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m leads", description="bot-factory lead system")
    parser.add_argument("--config", default="")
    parser.add_argument("--store", default=None, help="override the sqlite store path")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    p_sweep = sub.add_parser("sweep")
    p_sweep.add_argument("--dry-run", action="store_true", help="score and print; send nothing, remember nothing")
    p_sweep.add_argument("--only", nargs="*", help="listener names")
    p_sweep.add_argument("--json", action="store_true", help="print routed leads as JSON")
    p_sweep.add_argument("--force", action="store_true", help="ignore min_interval_minutes")

    p_loop = sub.add_parser("loop")
    p_loop.add_argument("--every", type=int, default=900)
    p_loop.add_argument("--serve", action="store_true", help="also run the inbound listener")
    p_loop.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8080)))

    p_serve = sub.add_parser("serve")
    p_serve.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8080)))
    p_serve.add_argument("--host", default="0.0.0.0")

    p_digest = sub.add_parser("digest")
    p_digest.add_argument("--hours", type=int, default=24)
    p_digest.add_argument("--top", type=int, default=10)
    p_digest.add_argument("--send", action="store_true", help="post to the Slack webhook")

    p_watch = sub.add_parser("watch", help="special listens: standing eBay watches (Shelby, Mazdaspeed6…)")
    p_watch.add_argument("action", choices=["list", "add", "remove", "import"])
    p_watch.add_argument("name", nargs="?")
    p_watch.add_argument("--q", help="eBay search, e.g. '(mazdaspeed6, mazdaspeed 6)'")
    p_watch.add_argument("--hunt", default="auto", help="auto | vehicle | jewelry | electronics | equipment")
    p_watch.add_argument("--max", type=float, default=None, help="max price")
    p_watch.add_argument("--zip", default=None, help="local pickup around this ZIP")
    p_watch.add_argument("--miles", type=int, default=150)
    p_watch.add_argument("--notify", choices=["all", "deals"], default="all",
                         help="all = every new listing; deals = only when the appraisers like the price")
    p_watch.add_argument("--for", dest="customer", default=None, help="customer whose wish list this is on")

    sub.add_parser("check")
    p_recent = sub.add_parser("recent")
    p_recent.add_argument("--limit", type=int, default=25)

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S")
    if args.command == "watch":
        from . import watches
        if args.action == "list":
            for w in watches.seed_examples():
                if args.customer and (w.get("customer") or "").lower() != args.customer.lower():
                    continue
                extra = " · ".join(x for x in (f"≤ ${w['max_price']:,.0f}" if w.get("max_price") else "",
                                               f"near {w['near']['zip']}" if w.get("near") else "", w.get("notify", "all")) if x)
                who = f"{w['customer']}: " if w.get("customer") else ""
                print(f"{who}{w['name']:<18} {w['q']}  [{w.get('hunt', 'auto')}] {extra}")
            return 0
        if args.action == "import":
            source = args.name or os.environ.get("WISHLIST_MATRIX", "")
            if not source:
                parser.error("watch import needs a CSV path or a published Google Sheet CSV link (or WISHLIST_MATRIX)")
            wants = watches.import_matrix(source)
            people = sorted({w.get("customer", "") for w in wants if w.get("customer")})
            print(f"imported {len(wants)} wants for {len(people)} customers: {', '.join(people)}")
            return 0
        if not args.name:
            parser.error("watch add/remove needs a name")
        if args.action == "remove":
            print("removed" if watches.remove(args.name, customer=args.customer) else "no such watch")
            return 0
        near = {"zip": args.zip, "miles": args.miles} if args.zip else None
        w = watches.add(args.name, args.q or args.name, args.hunt, args.max, near, args.notify, customer=args.customer)
        print(f"watching: {w['name']} → {w['q']}" + (f" (wish list: {w['customer']})" if w.get("customer") else ""))
        return 0

    path = _config_path(args.config)
    config = config_module.load(path)
    dry = getattr(args, "dry_run", False)
    system = config_module.build(config, dry_run=dry, only=getattr(args, "only", None), store_path=args.store)

    if args.command == "check":
        print(f"config: {path}")
        print(f"sinks:  {', '.join(s.name for s in system.pipeline.sinks) or '(none — leads only land in the store)'}")
        for listener in system.listeners:
            print(f"  ready    {listener.name} ({listener.kind})")
        if system.webhook:
            state = "ready" if system.webhook.get("token") else "no token"
            print(f"  {state:<8} {system.webhook['name']} (webhook)")
        for name, reason in system.skipped:
            print(f"  skipped  {name}: {reason}")
        return 0

    if args.command == "recent":
        for row in system.store.recent(args.limit):
            print(f"{row['first_seen'][:16]}  {row['urgency']:<8} {row['score']:>3}  {row['source']:<16} {row['title'][:70]}")
            if row["url"]:
                print(f"{'':>45}{row['url']}")
        return 0

    if args.command == "digest":
        from . import digest

        sinks = config.get("sinks", {})
        board = (sinks.get("lead_board") or {}).get("url")
        rows = digest.from_board(board) if board else digest.from_store(system.store)
        text = digest.render(digest.select(rows, args.hours, args.top), args.hours,
                             config.get("board_view_url", ""))
        print(text)
        slack = (sinks.get("slack") or {}).get("url")
        if args.send:
            if not slack:
                log.error("--send needs SLACK_WEBHOOK_URL")
                return 1
            digest.send(text, slack)
        return 0

    if args.command == "serve":
        return _serve(system, args.host, args.port)

    if args.command == "sweep":
        report = sweep(system, force=args.force)
        log.info("sweep done: %s%s", report.summary(), " (dry run)" if dry else "")
        if args.json:
            print(json.dumps([lead.to_dict() for lead in report.routed], indent=2, default=str))
        return 1 if report.errors and not report.routed and not report.dropped else 0

    if args.command == "loop":
        if args.serve and system.webhook:
            threading.Thread(target=_serve, args=(system, "0.0.0.0", args.port), daemon=True).start()
        while True:
            report = sweep(system)
            log.info("sweep done: %s — next in %ss", report.summary(), args.every)
            time.sleep(args.every)
    return 0


def _serve(system, host: str, port: int) -> int:
    from .listeners.webhook import serve

    spec = system.webhook or {}
    server = serve(system.pipeline, spec.get("token", ""), host, port, spec.get("name", "webhook"))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
