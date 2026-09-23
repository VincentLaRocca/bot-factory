"""Scraper data models and Apps Script lead conversion."""

import hashlib
from dataclasses import dataclass
from typing import Dict


@dataclass
class Listing:
    url: str
    title: str
    price: float
    location: str
    posted_at: str
    body: str = ""


def listing_to_lead(listing: Listing, board_cfg: Dict[str, str]) -> dict:
    lead_id = "CL-" + hashlib.sha1(listing.url.encode("utf-8")).hexdigest()[:10]
    return {
        "lead_id": lead_id,
        "listener_channel": board_cfg.get("listener_channel", "Open Boards"),
        "source_medium": "Board Scraping",
        "source_contact": listing.url,
        "origin": listing.location,
        "destination": "",
        "cargo_summary": listing.title,
        "payout_offered": listing.price,
        "mileage_est": 0,
        "urgency_level": "MEDIUM",
        "window_deadline": listing.posted_at,
    }
