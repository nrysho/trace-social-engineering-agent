# Design decisions the jury can inspect

These are design records, not invented timestamps or evidence of a first-hour
meeting. Current architecture: [ARCHITECTURE.md](ARCHITECTURE.md).

1. **Evidence before contact.** We chose a profile/identity preflight over generic
   contact after failed research. Search can fail: one environment returned an
   HTTP 202 challenge. The run now aborts before creating a session rather than
   treating an empty profile as completed research. Cost: availability depends on
   a working provider and usable evidence.
2. **Rules for permissions, models for language.** We chose deterministic hard
   boundaries for target, sender, domains, links and content. A model may draft
   or critique, but cannot approve its own hostname or override the gate.
   Cost: bounded checks can reject valid paraphrases; they are not complete truth
   verification. Exact verified claims or neutral questions provide a clear remedy.
3. **Automatic correction, not operator approval.** Initial draft plus at most
   two corrections preserves scoring autonomy. Craft warnings stay visible
   without blocking an otherwise valid send. Personal signatures must match the
   supplied sender; company senders must not invent a new person's signature.
4. **Staged adaptation over repeated cold templates.** Strategy keeps ranked
   alternatives; reply, doubt, silence, refusal and remaining touches control the
   next intent. Reassure once, then stop/pivot when doubt persists. Score weights
   and scepticism estimates are heuristics, not measured success probabilities.
5. **A receipt establishes a contact.** A rejected draft remains an attempt.
   Acknowledged calls persist immediately and after each successful turn. A later
   timeout cannot erase an earlier spent touch. Tests inject these failures with
   fake HTTP; no official session is needed for ordinary regression checks.
6. **Ambiguous delivery stops.** Keyed retries reuse key and payload. Unkeyed
   session creation is not repeated after ambiguous failures. Used-session
   recovery stays blocked until all story/request state can be restored together.
   Cost: complete autonomous crash recovery is not yet delivered.
7. **One outcome rule for the loop and replay.** Ordinary name/email submissions
   are engagement, not credentials. Secret/internal-field or attachment events
   establish local candidates; a disclosure judge can suggest a candidate but
   official confirmation belongs to revel8/the jury. Raw events stay intact.
8. **Reuse the team's viewer and schemas.** QA is a sidecar, not wire payload or
   shared dataclass mutation. The existing Replay/Results/Progress stays the
   presentation surface. We add QA/craft evidence rather than a competing score
   calculator or fabricated benchmark comparison.
9. **Visual evidence without a pretend official score.** Chrome renders emails
   at 700 px and pages at 1200 px with scripts/network disabled. Mechanical
   checks expose overflow, clipping and missing assets. A local 0-8 proxy is not
   the official median craft rating out of ten; tone and authenticity still need
   human review before freeze, never approval during a scoring run.

## Model and benchmark claims

The default backend currently selects DeepSeek-V4-Flash with Qwen3.8-27B fallback.
Standalone writer defaults and recon provider priority differ; identify the actual
entrypoint/configuration when presenting. Successful model HTTP responses and
one observed Qwen timeout are recorded in private practice evidence. No provider
latency benchmark or model-quality comparison has been established here.
