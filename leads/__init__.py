"""bot-factory lead system — listeners in, one pipeline, humans at the board.

    bids (SAM.gov) ─┐
    email (IMAP)  ──┤                                     ┌─→ lead board (triage)
    social (RSS) ───┼─→ Lead → dedupe → score (rules) ──┼─→ Slack (HIGH+ only)
    inbound (HTTP) ─┘                                     └─→ JSONL ledger

Stdlib only, like the rest of bot-factory. See docs/LEADS.md.
"""

from .model import Lead, make_lead_id
from .pipeline import Pipeline, RunReport
from .rules import RuleSet
from .store import SeenStore

__all__ = ["Lead", "Pipeline", "RuleSet", "RunReport", "SeenStore", "make_lead_id"]
