#!/usr/bin/env python3
"""Run one local board scrape and post new listings."""

import argparse
import json
import sys
import time
from typing import Dict

from leadscraper.adapters import ADAPTERS
from leadscraper.fetch import FetchBlocked, fetch
from leadscraper.models import listing_to_lead
from leadscraper.poster import post_lead
from leadscraper.state import is_seen, load, mark_seen, save


def run(config: Dict, dry_run: bool = False, max_new: int = 0) -> int:
    state = load(config["state_file"])
    failures = 0
    for board in config.get("boards", []):
        url = board["url"]
        listings = []
        posted = 0
        new_count = 0
        try:
            html = fetch(url, config["user_agent"])
            parser = ADAPTERS[board["adapter"]]
            listings = parser(html, url)
            for listing in listings:
                lead = listing_to_lead(listing, board)
                if is_seen(state, lead["lead_id"]):
                    continue
                new_count += 1
                if max_new and new_count > max_new:
                    continue
                if dry_run:
                    print(json.dumps(lead, sort_keys=True))
                else:
                    post_lead(config["api_url"], lead)
                    posted += 1
                    mark_seen(state, lead["lead_id"])
                    time.sleep(2)
        except FetchBlocked as error:
            failures += 1
            print("FetchBlocked: " + str(error), file=sys.stderr)
        except Exception as error:
            failures += 1
            print("board " + url + " failed: " + str(error), file=sys.stderr)
        print(
            "board {}: {} listings, {} new, {} posted".format(
                url, len(listings), new_count, posted
            )
        )
    if not dry_run:
        save(config["state_file"], state)
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Scrape local boards into LiveQueue")
    parser.add_argument("--config", required=True, help="path to scraper config JSON")
    parser.add_argument("--dry-run", action="store_true", help="print leads without posting")
    parser.add_argument("--once", action="store_true", help="run one pass (the default)")
    parser.add_argument("--max-new", type=int, default=25,
                        help="post at most N new listings per board per run (0 = unlimited)")
    args = parser.parse_args()
    with open(args.config, "r", encoding="utf-8") as handle:
        config = json.load(handle)
    return run(config, dry_run=args.dry_run, max_new=args.max_new)


if __name__ == "__main__":
    sys.exit(main())
