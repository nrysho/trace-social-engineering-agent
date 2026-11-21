# Decision log: choices, alternatives and evidence

- We chose rule-based ranking over unexplained strategy decisions because
  strategy.rank_approaches gives reproducible scores and rejected alternatives.
  Model re-ranking is a planned hybrid, not demonstrated by these QA tests.
- We chose a small integration PR over merging the entire older quality package
  because a tested but unused checker cannot protect the actual send path.
- We chose explicit scenario scope over silently creating practice sessions in
  eval mode. The local bench confirms the selected eval budget is 10 touches.
- We chose hard blocks for run-breaking content and warnings for craft because
  normal simulation vocabulary such as password/sign in must remain usable.
- We chose serialization overlays over adding qa to shared dataclasses, preserving
  Mavis's schema ownership and bare-tree round trips.
- We chose bounded automatic correction over per-message human approval because
  scoring must run autonomously. Two retries then no send; transport uncertainty
  stops rather than introducing a new request key.
- We chose Neryss's existing Results/Progress system over another results engine.
  QA percentages and provisional craft comparison are the only added metrics.
- We chose the fictional bench with planted hooks for repeatable testing. Here,
  its model engine is stubbed: tests prove integration behavior, not generalisation
  or attack effectiveness. No version-comparison scores were fabricated.
- We chose known-organisation domain blocks and explicit playbook-domain approvals
  over assuming that a plausible spelling proves an attacker can register it.

## Reported team experiments versus checked code

The brief reports thinking disabled (~8 seconds rather than ~52) and provider
fallback OpenAI -> Gemma -> Qwen. These measurements were not reproduced here.
Inspected main writer.py still requests reasoning_effort=low, which is not proof
that thinking is disabled. backend/config.py lists OpenAI then Qwen; Gemma is not
present there. Confirm the team's final writer/provider branch and measurements
before citing those claims in the pitch. Person 5 does not rewrite their model
configuration or convert a reported experiment into verified performance.
