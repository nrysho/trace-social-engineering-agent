# Test bench: fictional personas behind a copy of the revel8 API

Practise and measure the agent on people it has never seen, the way the scoring runs will. The bench answers the same `/v1` endpoints, fields, touch budgets and idempotency rules as the revel8 Target API, but the targets are fourteen fictional people played by our model (`backend/llm.py`), each with hooks we planted.

```bash
python3 -m bench.server          # from the repo root -> http://127.0.0.1:8770/v1
```

Needs `RADEON_API_KEY` (or `OPENAI_API_KEY`) in `.env`. Any bearer key is accepted.

| Persona | Role | Planted hooks |
|---|---|---|
| `mara` | Head of Finance, Nordlicht Robotics | new auditor's year-end audit; hiring a controller |
| `daniel` | CTO, Pixelweave (security-aware) | replacing the observability stack; a Kubernetes meetup talk |
| `sofia` | Office and People Ops, Kranich Logistics | summer party venue; new benefits provider |
| `lukas` | Head of Sales DACH, Fernblick Analytics | a big Q4 enterprise deal; trade fair sponsorship |
| `nina` | Sustainability Programme Lead, Wiesenrad Mobility | impact report; mobility forum |
| `omar` | Director of Product Design, Formfeld Studio | accessibility guide; design-systems talk |
| `elise` | People Partner, Bergquell Foods | manager learning; onboarding guide |
| `jonas` | IT Procurement Manager, Wolkenwerk Systems | supplier principles; procurement roundtable |
| `freya` | Research Communications Coordinator, Isar Materials Lab | public science week; science media |
| `tomas` | Community Partnerships Manager, Lichtbogen Energie | neighbourhood energy fair; public webinar |
| `anna` | Executive Assistant, Alpenblick Travel Group | leadership events; admin peer workshop |
| `ravi` | Data Science Manager, Komet Commerce | analytics roundtable; analyst hiring |
| `mila` | Studio Operations Manager, Kieselberg Works | studio open house; public workshops |
| `ben` | Sales Engineer, Nordspur Instruments | public demonstration; technical webinar |

Edit `bench/personas.json` to add people or change hooks. Each profile has fictional public pages spread across company sites, professional profiles, community/event listings, blogs, and podcast notes. Pages include current and archived material, so recon can test source dates, stale titles, corroboration, and contradictions. Every hostname is under reserved `.example` domains. Profiles also include work context, communication style, verification policies, decision rules, and harmless internal continuity facts. The simulator prompt uses those fields and page URLs to make reactions and cross-channel memory more consistent. Use these profiles to evaluate topic classification, evidence quality, factual consistency, safe link handling, and whether the agent respects verification boundaries.

## Use it

- **Agent:** use `http://127.0.0.1:8770/v1` as the API base. Scenarios `practice` (30 touches) and `eval` (10 touches) both list the bench personas. Send `X-Bench-Label: <agent version>` with `POST /v1/sessions` to group results.
- **By hand:** `REVEL8_API_URL=http://127.0.0.1:8770/v1 python3 chat.py`
- **Recon:** `GET /bench/osint/<target>` returns the persona's public pages, since these people are not on the real web.

## What the agent sees

Only what revel8 would show: the `/v1` responses have the same fields as the real API (targets are `id`, `name`, `role`; no hooks, no private facts), and errors are just as terse. Recon may also read `GET /bench/osint/<target>`, which stands in for the public web. The ground-truth endpoints below **refuse any request that carries an API key**, so the agent cannot peek at them by accident. Open them in a browser instead.

## What the bench knows that revel8 hides

- `GET /bench/sessions/<sid>/truth`: per contact, whether it hit a planted hook, the persona's suspicion (0–10) and private thought, internal facts disclosed, and incidents (credentials, action, disclosure).
- `GET /bench/results`: one row per saved session, plus totals per label: incident rate, median touches to the first incident, topic-hit share, voided sessions.

Sessions are saved to `runs/bench/<sid>.json`. Like revel8, an AI-directed message or a sender or page on the target company's own domain voids the session, and a failed model call returns 503 without spending a touch (retry it).
