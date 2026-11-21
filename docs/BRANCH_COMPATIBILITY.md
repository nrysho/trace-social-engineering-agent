> Historical iteration/snapshot. Current branch and status: [PERSON5_HANDOFF.md](PERSON5_HANDOFF.md) and [CONSOLIDATION.md](CONSOLIDATION.md). Earlier test counts and integration limitations below are not the current combined result.

# Branch compatibility: Person 5 update

Snapshot inspected 21 November 2026. No team implementation files or shared schemas were edited by this adaptation.

## main: 16ae78b

New backend/run.py is a bare autonomous practice loop: minimal role lookup, placeholder model writer, event-based evaluator, saved runs/trees/<run_id>.json. It is linear and capped by max_contacts; it is not full tree search or crash-resume/budget enforcement. The repository records the team's four-touch practice test; this Person 5 iteration made no fresh live request.

GuardedClient now supports scenarios/channels, practice-session creation, scoped reads and cleanup in addition to checked messages/pages/call turns. It works with the new loop's client interface in offline tests. Closed sessions/calls lose their authorised scope. Eval creation remains blocked. The actual backend/run.py still instantiates Revel8Client directly, so the team must deliberately select the wrapper. Tests inject it temporarily; production monkeypatching is not the integration recommendation.

The current placeholder writer does not accept QA feedback, and a QualityBlocked exception from send ends the loop after saving its tree. Izen/Mavis still need to connect the bounded writer callback for automatic correction. No real factual verification is inferred from the placeholder writer's plausible event details.

## neryss/viewer: a7da34e

The viewer expects one bundle with run_id, mode, profile, nodes, messages and events keyed by contact node ID. Its sample is fictional. Our exporter joins an explicitly selected tree and API log without guessing a session from a run name:

```powershell
python -m quality.viewer_export --tree runs/trees/RUN_ID.json --api-log runs/api/SESSION_ID.jsonl --profile path/to/profile.json --output runs/RUN_ID.json
python -m quality.cli report runs/RUN_ID.json --output output/quality/RUN_ID
```

Profile is optional. Omitting it leaves identity/profile fields empty, not invented. Do not substitute a mock profile for a real run. Exported message records are viewer representations, not complete replayable send payloads: API logs do not retain the original idempotency keys/session metadata.

Open Neryss's viewer branch with that bundle in runs/. We verified an exported synthetic fixture against her actual server/UI in an isolated checkout over localhost, with no external browser access and no page errors. Evidence is local under output/quality/branch-compat/.

Exported nodes and raw events preserve their original content. Duplicate event IDs are removed; conflicts, unmatched sent-node IDs and contradictory event references fail rather than silently joining. Contact nodes without sent records are flagged and not treated as completed sends. Events that cannot be joined remain in quality_evidence.unjoined_events. Current call.start logs have no node_id, so their call events/transcripts cannot be safely assigned to a viewer node. The selected log's recorded contact count includes calls, while linked message counts remain separate.

Important viewer limitation: current chips infer touches from contact-node counts and incidents from evaluator statuses. Those can overstate attempted/unsent contacts or uncertain outcomes. Our quality report uses recorded send/call evidence and keeps official outcomes unknown. Neryss should label these statuses as local evaluator labels and use quality_evidence / summary metrics when available. The exporter does not rewrite her UI or silently change source statuses.

## recon-osint: b718bcc

The branch adds search-provider fallback, readable-page fetch and DNS collectors. The shared Profile/Fact shapes remain compatible. Person 5 does not invoke collectors or alter research ownership.

```powershell
python -m quality.cli profile path/to/profile.json --output output/quality/profile-review
```

review_profile accepts a shared Profile or JSON dictionary. It checks categories, nonempty fact values, finite confidence range and evidence-URL structure. A verified flag with fewer than two distinct source hosts raises a warning. Multiple hosts do not prove independent registrable domains or factual truth. The checker does not promote any fact to verified, fetch a URL, or recalculate exposure/hook scores.

## Other branches

feat/agent-loop and feat/revel8-client have no commits ahead of current main in this snapshot; their implemented work is represented there. ui/chat is already represented in main's practice chat. theja-branch remains the older TRACE dashboard prototype; theja-person5-main is the team-compatible QA package. Do not merge the older prototype merely to obtain these helpers.

## Verified acceptance

68 tests pass with optional Chrome checks enabled; default suite has 66 pass and two browser skips. Tests execute the actual new loop, shared schemas and API client with fake HTTP/writer callbacks, never live contacts. Coverage includes an unsent rejected contact, viewer export/round-trip metrics, evaluator-label disagreement, source joins, profile structure and closed-session scope.

Mavis: select the guard and wire writer feedback. Neryss: import bundles and separate evaluator labels from authoritative metrics. Sherwin: provide real sourced profiles. Izen: consume error feedback and write from supported facts. Actual adoption, human pitch rehearsal and official outcomes remain pending.

## Reproduce export without private data

```powershell
python -m quality.viewer_export --tree quality/samples/replay_tree.json --api-log quality/samples/replay_api.jsonl --profile quality/samples/replay_profile.json --output output/quality/branch-compat/viewer-bundle.json
python -m quality.cli report output/quality/branch-compat/viewer-bundle.json --output output/quality/branch-compat/report
```

These versioned fixtures are synthetic and mode=mock. Copy the generated bundle into the viewer checkout's runs/ directory to inspect it with Neryss's viewer. Real run exports remain private. The profile checker also accepts quality/samples/replay_profile.json, whose empty fact list is intentionally not research evidence.

## izen/autonomous-strategy-lab: 91f10d5

This branch appeared during the final refresh and was reviewed before publication. It adds strategy hypotheses/ranking, writer.py and a separate Node strategy-lab UI/server. writer.generate_message and generate_call_line return content plus model/fallback/refusal metadata; sender configuration uses email. make_landing_page returns title/html/fields without a URL.

quality.writer_adapter.checked_writer_message maps that result into our shared checked contract. Sender email becomes address; conflicting address/email blocks. Supply an explicit page_url for generated pages and independently approved domain context. Generation metadata stays outside the API payload. Convert the prepared object with quality.integration.as_shared_message and send through GuardedClient, which revalidates at the final boundary. checked_writer_turn maps body to say and keeps provenance separate. Missing model/fallback metadata stays unknown. These adapters are tested with synthetic writer results, not live model requests.

```python
from quality.writer_adapter import checked_writer_message
from quality.integration import as_shared_message

prepared = checked_writer_message(
    writer_result, context, sender=chosen_sender, target_id=target_id, channel=channel,
    session_id=session_id, node_id=node_id, idempotency_key=contact_key,
    landing_page=generated_page, page_url=registered_url,
)
response = guarded.send_message(as_shared_message(prepared))
# Store prepared['generation'] and prepared['report'] as local trace metadata.
```

Izen's writer has its own simpler quality gate; passing it does not replace the final boundary. The separate frontend/server.mjs sends messages/pages/call turns directly through its own Node routes. Our Python wrapper is NOT automatically active there. Those routes need explicit equivalent validation/integration before anyone claims all strategy-lab sends are gated. No Izen source was edited or merged into our branch.

The strategy's top-level profile facts/probabilities are producer hypotheses; Person 5 does not certify them or convert them into topic-hit/official outcome scores.

The actual Izen writer function and page generator were additionally verified from the inspected branch using a fake completion; this is source-level compatibility evidence, not an actual model run.
