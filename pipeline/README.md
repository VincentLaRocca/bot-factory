# Claude pipeline — ideas to code

Three Claudes, one repo, Vinny at the gates.

| Station | Surface | Leans toward |
| --- | --- | --- |
| Idea Forge | Claude web | research, framing, the Build Card |
| Build Bay | Claude Code | code, tests, PRs |
| Proving Ground | Claude desktop | running it for real on Vinny's machine |

## Loose, not completely loose

The stations are home bases, not walls. Any station can reach into another's
work when that's where the answer is: web can patch a rule, Code can reshape
the spec, desktop can fix what it finds while testing.

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

What stays fixed:

- **Vinny's gates:** greenlight before building, merge before it goes live.
- **Anything hard to undo waits for Vinny:** merging to main, deploying,
  spending money, sending anything to outside people.
- **The Build Card is the shared memory.** No station relies on its own chat
  history; if it matters, it's in the card.

## Layout

```
pipeline/
  README.md            this file
  <idea>/spec.md       one Build Card per idea: problem, done-means,
                       constraints, interfaces, checklist, Log
```
