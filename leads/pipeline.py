"""Normalize → dedupe → score → route. Written once, used by every listener.

Listeners only produce :class:`Lead` objects; they never decide what is worth
a human's time. The pipeline does, by rules anyone can read, and it records
every decision — routed, dropped or duplicate — so the question "why didn't I
see that post?" always has an answer in the store.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Mapping, Optional

from .model import Lead
from .rules import RuleSet
from .sinks import Sink
from .store import SeenStore

log = logging.getLogger("leads")


@dataclass
class RunReport:
    routed: List[Lead] = field(default_factory=list)
    dropped: List[Lead] = field(default_factory=list)
    duplicates: int = 0
    errors: List[str] = field(default_factory=list)

    def merge(self, other: "RunReport") -> "RunReport":
        self.routed += other.routed
        self.dropped += other.dropped
        self.duplicates += other.duplicates
        self.errors += other.errors
        return self

    def summary(self) -> str:
        return (f"{len(self.routed)} routed, {len(self.dropped)} dropped, "
                f"{self.duplicates} already seen, {len(self.errors)} errors")


class Pipeline:
    def __init__(self, store: SeenStore, rules: RuleSet, sinks: Iterable[Sink] = (),
                 source_rules: Optional[Mapping[str, Mapping]] = None, dry_run: bool = False):
        self.store = store
        self.rules = rules
        self.sinks = list(sinks)
        self.source_rules: Dict[str, RuleSet] = {
            name: rules.merged(override) for name, override in (source_rules or {}).items()
        }
        self.dry_run = dry_run
        self._lock = threading.Lock()  # the webhook server calls in from many threads

    def rules_for(self, lead: Lead) -> RuleSet:
        return self.source_rules.get(lead.source, self.rules)

    def process(self, leads: Iterable[Lead]) -> RunReport:
        with self._lock:
            return self._process(leads)

    def _process(self, leads: Iterable[Lead]) -> RunReport:
        report = RunReport()
        for lead in leads:
            if self.store.seen(lead):
                report.duplicates += 1
                continue
            rules = self.rules_for(lead)
            lead.score, lead.urgency, lead.reasons = rules.score(lead)
            if not rules.passes(lead.score):
                report.dropped.append(lead)
                if not self.dry_run:
                    self.store.record(lead, "DROPPED")
                continue
            report.routed.append(lead)
            if self.dry_run:
                continue
            for sink in self.sinks:
                try:
                    sink.send(lead)
                except Exception as error:  # a sink failing must not stop the sweep
                    message = f"{sink.name}: {lead.lead_id}: {error}"
                    log.warning(message)
                    report.errors.append(message)
            self.store.record(lead, "ROUTED")
        return report
