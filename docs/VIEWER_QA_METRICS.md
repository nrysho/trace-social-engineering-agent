# Viewer QA additions

Existing incident, hook and contact calculations are unchanged. The existing
/api/runs summary now includes qa, and GET /api/quality/versions groups only QA
and local craft by explicit agent_version (otherwise unknown). No parallel
results tracker or scoring estimator was created.

QA keys: checked, blocked, warnings, bypassed, missing_verdicts,
conflicting_verdicts, blocked_percent, warning_percent and top_reasons.
Node/message copies with the same node ID count once. Conflicts are excluded;
bypasses are reported separately and do not count as checked. Empty denominators
remain null. Rates describe final recorded candidates, not every writer retry.
Local craft means use scored items only; official_craft_score remains null.

Neryss's locally described QA display consumes the same passed/errors/warnings
contract. These server additions do not overwrite her pending UI edits. Feed
bundle-with-craft.json from the offline craft tool into the viewer to include
its craft rows. Set an explicit agent_version on benchmark bundles; never infer
one from model names or label bench numbers as official scoring.

Updated for main 1c68d1f: existing /api/results rows also carry qa, recorded bench metrics.label supplies the version, and complete bundles take precedence over bare trees so QA overlays are retained. Existing Results/Progress calculations and UI are preserved.

The universal tone/factual-review disclaimer is documentation, not a warning emitted on every draft; this keeps actionable warning rates meaningful. Passing still does not certify facts or aesthetic quality.
