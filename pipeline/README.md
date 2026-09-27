# Claude pipeline — ideas to code

Several Claudes, one repo, Vinny at the gates.

**What it's for:** a loose framework for following intuition and playing it out
quickly. An idea goes from hunch to something real fast enough to see whether
the hunch was right, with enough structure (the card, the judge, the gates)
that speed doesn't cost trust.

| Role | Surface | Does |
| --- | --- | --- |
| **Idea Forge** | Claude web | research, framing, drafting the Build Card |
| **Listener / internet worker** | Claude in Chrome | works the internet layer in Vinny's real browser: watches sites, reads what has no feed or API, fills forms, and hands findings to the factory (e.g. `POST /leads`) |
| **Desktop: sessions and reality lens** | Claude desktop | holds the working sessions with Vinny. Brings the different lenses that pull reality into focus: does this match the real world, the real market, what Vinny actually meant? Also handles desktop duties: local files, apps, the 5090, running and testing things on Vinny's machine |
| **Judge** | Claude Code | the factory's judge: checks work against the Build Card's "Done means", runs the tests, rules pass / rework, and builds or fixes code when that's the fastest route |
| **Second opinion** | Grok (sometimes) | called in when an outside read helps, such as a Breaker pass on a Maker's work or a tie-break between Claudes. Its reading is logged like any other |

## Loose, not completely loose

The stations are home bases, not walls. Any station can reach into another's
work when that's where the answer is: web can patch a rule, Chrome can flag a
source the spec missed, desktop can fix what it finds while testing. The judge
still rules on the result.

Decisions get cross-bred:

- **Any station can propose a change to any part of the card or the code.** Put
  it in the card's Log with the station name, what changed and why.
- **A decision that shapes more than one station is a cross-bred decision.**
  Mark it `[cross]` in the Log, e.g. a scope cut found while testing that
  changes both the spec and the code. The next station to pick up the card
  reads the `[cross]` entries first.
- **Disagreement stays visible.** A station that disagrees with an earlier
  call logs its reading beside the earlier one and doesn't overwrite it.
  Vinny picks.

Where the roles meet: Chrome brings in what's out there, Claude Code judges
whether the work meets the card, and desktop checks both against reality with
Vinny. A judge's PASS on code that misses the real point is still a miss;
desktop flags it with its lens, logged as `[cross]`.

What stays fixed:

- **Vinny's gates:** greenlight before building, merge before it goes live.
- **The judge rules before Vinny's merge gate.** Claude Code logs a verdict
  (`PASS` / `REWORK` + reasons) against "Done means" before a merge is asked for.
- **Anything hard to undo waits for Vinny:** merging to main, deploying,
  spending money, sending anything to outside people. For Chrome this means
  it reads and reports freely but doesn't post, message, bid or submit to
  outside parties without Vinny's go.
- **The Build Card is the shared memory.** No station relies on its own chat
  history; if it matters, it's in the card.

## Layout

```
pipeline/
  README.md            this file
  <idea>/spec.md       one Build Card per idea: problem, done-means,
                       constraints, interfaces, checklist, Log
```
