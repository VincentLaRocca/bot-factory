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
| **Assist** | Grok (sometimes) | called in when an outside read or extra hands help, such as a Breaker pass on a Maker's work, a tie-break between Claudes, or a piece of the build. Its input is logged like any other |
| **Library** | Gemini | keeper of the NotebookLM library. Asked what already exists (their specs, notebooks and prior work) before anything new is built |
| **Site builds** | ChatGPT (Apps SDK sites) | when a piece needs a hosted web app or site, borrow ChatGPT's site skills, as with the Mid-Atlantic Lead Board and the RSS feed leads app. The factory talks to them over their webhooks/feeds, and Claude publishes a documented API + a paste-ready brief (e.g. docs/CUSTOMER_API.md) |

**Each AI where it's strongest** (Vinny): Claude builds engines, the listeners,
appraisers and value logic; ChatGPT builds sites; Gemini keeps the library; Grok
assists; Vinny approves. Interfaces between them are plain JSON APIs, webhooks
and feeds, so any one can be swapped without breaking the others.

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

**Borrow first.** Before building, check what already exists: our own code
(bot-factory, the lead board, earlier listeners), Gemini's library for their
side of the work, and Grok for help. Reuse or adapt beats a rewrite. The card
lists what was borrowed and from where.

**Roadblock → take it to the 5090 level.** When a cloud surface hits a wall
(a rate limit, a blocked site, a sandbox that can't reach something, API
costs or quotas, a model that won't run small enough), escalate to Vinny's
5090 machine instead of working around it or shrinking the idea: a residential
IP, full local compute, local models, his real files and apps. Log the
escalation as `[5090]` in the card with what hit the wall and what moved.
Examples from Session 1:

- Reddit throttles cloud IPs (HTTP 429) → the social feeds run from the 5090 box
- LLM scoring (v1) → a local model on the 5090 instead of paid API calls
- Anything needing a long-running process or GPU → the 5090, exposed with a Cloudflare Tunnel

## Architect Mode

At points in time Vinny declares **Architect Mode**. Inside it, Claude has
autonomous, laissez-faire rights to build: no asking permission step by step.
Claude designs, builds, refactors, adds listeners and tools, works across
stations, calls in Grok or Gemini, escalates to the 5090, and keeps moving on
its own judgment.

- **On:** Vinny says "Architect Mode" (for a session, a card, or a stretch of time).
- **While on:** build first, explain after. Every move goes in the card's Log
  marked `[architect]`, so the trail is complete when Vinny comes back.
- **Off:** when Vinny says so, or when the declared scope is done. Claude then
  gives a short account: what was built, what was decided, what's waiting.
- **Still gated, unless Vinny widens it for that run:** merging to main,
  deploying to production, spending money, and sending anything to outside
  people. Architect Mode fills the branch; Vinny's gate opens main.

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
