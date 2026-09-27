"""Vinny's price sheet: comparable values, one row per kind of thing.

A plain CSV he can edit in any spreadsheet app. Columns:

    domain,match,year_from,year_to,value,note
    vehicle,ford f-150,2012,2016,14000,"4x4 crew cab, runs, 150k mi"
    equipment,skid steer,,,18000,"~2,500 hrs, runs"

``match`` is words that must all appear in the listing (lower-case). The most
specific matching row (most words, then a year range that contains the
listing's year) wins. The example sheet holds PLACEHOLDER numbers; replace
them with real sold prices before trusting an estimate.
"""

from __future__ import annotations

import csv
import os
import re
from dataclasses import dataclass
from typing import List, Optional

EXAMPLE = os.path.join(os.path.dirname(__file__), "comps.example.csv")


@dataclass
class Comp:
    domain: str
    words: List[str]
    year_from: Optional[int]
    year_to: Optional[int]
    value: float
    note: str


def load(path: Optional[str] = None) -> List[Comp]:
    path = path or os.environ.get("VALUE_COMPS_CSV") or EXAMPLE
    rows: List[Comp] = []
    if not os.path.exists(path):
        return rows
    with open(path, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            try:
                rows.append(Comp(
                    domain=row["domain"].strip().lower(), words=row["match"].lower().split(),
                    year_from=int(row["year_from"]) if (row.get("year_from") or "").strip() else None,
                    year_to=int(row["year_to"]) if (row.get("year_to") or "").strip() else None,
                    value=float(row["value"]), note=(row.get("note") or "").strip()))
            except (KeyError, ValueError):
                continue
    return rows


def best(comps: List[Comp], domain: str, text: str, year: Optional[int] = None) -> Optional[Comp]:
    text = " " + text.lower() + " "
    fits = []
    for comp in comps:
        if comp.domain != domain or not all(re.search(r"\b" + re.escape(w) + r"(?:s|es)?\b", text) for w in comp.words):
            continue
        if year and ((comp.year_from and year < comp.year_from) or (comp.year_to and year > comp.year_to)):
            continue
        dated = bool(year and (comp.year_from or comp.year_to))
        fits.append((len(comp.words), dated, comp))
    return max(fits, key=lambda f: (f[0], f[1]))[2] if fits else None
