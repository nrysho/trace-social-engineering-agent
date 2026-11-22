# Rubric readiness: spend the remaining effort where the jury can see it

Source: the revel8 scoring rubric supplied by Theja on 22 November 2026.
This is a readiness assessment, not a predicted score. Official results, hidden
hooks, comparison to other teams and jury decisions are not available locally.

## First priority: architecture and persistence, 40 points

The implementation has a useful story: sourced research, explicit permission
boundaries, staged adaptation, a contact budget and inspectable failure evidence.
The previous architecture page understated this and incorrectly said the gate
was not on main. ARCHITECTURE.md now describes the actual integrated system;
architecture.html is the concise printable page.

Show the jury three concrete proofs rather than a longer component list:

1. **Why this approach?** Open the profile source, ranked hook/channel, supporting
   facts and rejected alternatives. Explain the tradeoff. Ranking weights and
   exposure are not probabilities or private topic-hit measurements.
2. **What changed after the reply?** Show the actual reply, selected next intent
   and changed message/call turn. The saved four-turn practice call proves one
   real dialogue; it does not prove a cross-channel pivot or incident. Use a
   better complete scoring thread when it becomes available.
3. **What happens when something breaks?** Demonstrate a blocked draft, bounded
   correction and the saved receipt/partial call after an injected timeout.
   Clearly label fault-injection footage synthetic. Explain why an uncertain
   send stops, and why full used-session crash recovery is still a limitation.

Do not claim full autonomous resume, durable default story state, a semantic
truth oracle, unlimited search or a learned policy. The optional ReviewedClient
and SQLite layer are not the active scoring loop merely because they exist.

## Second priority: pitch and demo, 15 points

The rubric says five minutes, while the event guide supplied earlier says three
minutes plus two minutes Q&A. Keep a three-minute core and a five-minute version;
confirm the slot with organisers. PITCH_3_MIN.md and PITCH_5_MIN.md share one
honest message and real-thread evidence. Do not rush a five-minute script into
three. Rehearse both lengths as needed; no spoken rehearsal is claimed here.

Open the viewer before speaking, use full screen, and keep a local backup.
Narrate an actual thread from profile to message to event to next move. A one-touch
email with no events is a real transmission smoke test, not a successful attack.
A synthetic demo is a labelled fallback, not the required real-thread evidence.

## Third priority: craft, 10 points

The official measure is the median across all scored mails and pages. Review the
whole set, not just a polished example. A call-only strategy earns no email/page
craft score under this rubric; that is a tradeoff for the agent owner to assess,
not a reason for Person 5 to inject unnecessary contacts during scoring.

Render the exact saved HTML/text at 700/1200 px without scripts/network. Inspect
sender/signature, format, footer, visible link/destination, clipping and images.
The latest sourced-profile practice email rendered with no overflow, clipping or
broken images in the local tool. Its mechanical 8/8 proxy is not 10/10 craft or
proof of authenticity. Asset/image resolution and aesthetic judgment remain gaps.

## Results, 25 points, and targeting, 10 points

No incident is verified in the practice evidence collected by Person 5. Tests
prove integration, not attack effectiveness. The most valuable next team evidence
is a complete autonomous run with an observable incident candidate and the API
contact count, followed by official jury confirmation after scoring.

Use the existing local bench for version comparisons: same persona set, budget,
configuration and reported denominator. Keep attempted, failed, aborted and
contacted runs visible. The deterministic QA bench engine cannot be cited as a
performance experiment. Preserve no-incident runs as not reached in official
speed reporting; do not replace them with zero or compute the official speed
formula without the other teams' minimum.

Private topic hits and own-angle confirmation come from revel8/the jury. Do not
infer them from exposure, replies or a model's confidence. Source every target
claim, distinguish DNS/verification records from account/subscription state, and
keep namesake/identity uncertainty explicit. This reduces the wrong-facts risk;
it does not guarantee the jury will make no deduction.

## Corrections made while reviewing this rubric

The generic reaction evaluator treated every page.submitted event as an incident.
That could prematurely stop a run after only name/email entry. Form submission
now means engagement until secret/internal-field evidence establishes a candidate.
Runner and viewer share a pure candidate classifier; field matching no longer
mistakes the substring PIN in shipping_address for credentials. These are
reporting/control-flow corrections, not changes to raw historical events.

## Before freezing for scoring

- Mavis: confirm final entrypoint, three-session policy, target/scenario scope,
  used-session reconciliation behaviour and ten-touch budget. Run the actual
  model-backed local bench and freeze the tested version; do not improvise during eval.
- Sherwin: inspect factual sources/verification and separate authoritative DNS
  observations from inferred vendor relationships or subscriptions.
- Izen: verify writer identity and factual handling against current profiles;
  draft routes must go through the guard. No human editing during scoring.
- Neryss: prepare the read-only replay, source/QA evidence and honest local-result
  labels; retain every run, including failures and not-reached outcomes.
- Theja: submit the architecture page, choose the real thread, inspect all craft
  outputs, rehearse twice with a timer and confirm the actual pitch length.

Do not add major planner/model/state rewrites immediately before a scoring freeze.
Finish evidence and presentation first; test small correctness fixes offline.
