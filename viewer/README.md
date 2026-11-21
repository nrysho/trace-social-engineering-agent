# Run replay viewer

Read-only replay of agent runs: the decision tree, rejected options with reasons, each node's reasoning and evidence, the messages as the target saw them (mail and landing page previews), and the target's reactions. It has no send, edit or approve controls, so it is safe to have open during scoring.

```bash
python3 viewer/serve.py          # then open http://127.0.0.1:8765
```

No dependencies beyond Python 3. The run list shows:

- every run file in `runs/*.json`, newest first
- `sample`: `viewer/sample_run.json`, a branching demo run on a fictional target (failed hook, a call, pivot, incident on touch 4)
- `mock`: Mavis's `mock/profile.json`, `mock/tree.json` and `mock/message.json`

Use it: click a node to inspect it; ◀ ▶ (or the arrow keys) step through the run in time order; Play replays it; untick "show rejected options" to hide the dashed alternatives. Link to a run or a node with `?run=sample&node=n12`.

## Run file format (proposal for `schemas.py`)

The viewer reads the shapes already in `schemas.py` unchanged. It only needs them in one file per run, `runs/<run_id>.json`:

```json
{
  "run_id": "run_julius_001",
  "mode": "practice",
  "profile":  { "...": "Profile.to_dict()" },
  "nodes":    [ { "...": "TreeNode.to_dict()" } ],
  "messages": [ { "...": "Message.to_dict(), linked to its contact node by node_id" } ],
  "events":   { "<contact node id>": [ "...raw events from the revel8 response, unchanged..." ] }
}
```

- `events` keeps the raw revel8 events (`reply`, `link.opened`, `page.submitted`, `attachment.opened`). `TreeNode.outcome` stays the short summary. An empty list means the target ignored the contact.
- Every contact node counts as one touch; the viewer computes "incident at touch N" from contact nodes with status `incident`.
- For calls, put the transcript in `Message.body`, one `Name: line` per line (`You: ...` for our side).
- A rejected option belongs to the node it was rejected in favour of, so the viewer draws it as a sibling of that node.
