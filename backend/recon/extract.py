"""pull sourced facts from search results with the llm.

- the model returns json facts, each tagged with one of the provided source urls
- we keep only facts whose url was actually in the batch, so nothing is invented
"""
import json
import re
import threading
from concurrent.futures import ThreadPoolExecutor

from backend import llm
from schemas import Fact, FACT_CATEGORIES

CHUNK = 6             # results per llm call, to bound the prompt
CONTENT_CHARS = 1500  # how much page text per result we show the model
MIN_CONF = 0.5        # drop facts the model is not reasonably sure are about the target

# extract chunks and company aspects run concurrently; this caps how many of those
# llm calls are in flight at once. measured: openai served ~13 concurrent recon calls
# with no 429 and no qwen fallback, so 8 leaves headroom while staying well clear of
# the rate limit on a busier key. shared with company.py so the whole recon extraction
# stage respects one global cap. llm.chat still retries 429 and falls back on its own.
_LLM_GATE = threading.Semaphore(8)

SYSTEM = (
    "You research ONE specific person and extract facts about THEM only, for an authorised "
    "research exercise. Return JSON only: {\"facts\": [{\"category\": ..., \"value\": ..., "
    "\"source_url\": ..., \"date\": ..., \"confidence\": 0-1}]}. category is one of: "
    + ", ".join(FACT_CATEGORIES) + ". Many results are about OTHER people - a colleague, the "
    "company's founder, or a different person with the same name. Extract a fact ONLY when the "
    "text is clearly about the target person; if a result is about someone else, return nothing "
    "for it, and NEVER attribute another person's role, history or activity to the target. value "
    "is one short factual sentence. source_url MUST be copied exactly from the result. date is "
    "YYYY-MM (or YYYY) when it happened or ended, \"present\" if current, or \"\" if not stated; "
    "never guess a date. confidence (0-1) is how sure you are the fact is about the target and true."
)
JSON_MODE = {"type": "json_object"}


def _chunks(items, n):
    for i in range(0, len(items), n):
        yield items[i:i + n]


def _slice(text):
    m = re.search(r"\{.*\}", text, re.S)  # tolerate fences or prose around the json
    return m.group(0) if m else text


def _extract_chunk(who, batch, urls, titles):
    block = "\n\n".join(
        f"URL: {r.url}\nTITLE: {r.title}\nTEXT: {(r.content or r.snippet)[:CONTENT_CHARS]}"
        for r in batch
    )
    user = f"Target person: {who}.\n\nResults:\n{block}"
    try:
        with _LLM_GATE:  # bound concurrent extraction calls across the whole recon stage
            text = llm.chat([{"role": "system", "content": SYSTEM},
                             {"role": "user", "content": user}], response_format=JSON_MODE, temperature=0)
        data = json.loads(_slice(text))
    except Exception as e:
        print(f"  extract chunk failed: {e}")
        return []
    out = []
    for f in data.get("facts", []):
        url = f.get("source_url", "")
        if (url in urls and f.get("category") in FACT_CATEGORIES and f.get("value")
                and float(f.get("confidence", 0.5)) >= MIN_CONF):
            out.append(Fact(
                category=f["category"], value=str(f["value"]).strip(),
                source_url=url, source_title=titles.get(url, ""),
                date=str(f.get("date", "")).strip(),
                confidence=float(f.get("confidence", 0.5)),
            ))
    return out


def extract_facts(name, company, results, role=""):
    # chunks run concurrently, bounded by _LLM_GATE. measured: this stays on openai (no
    # qwen fallback) and cuts the extract phase from ~16-22s to ~5-6s. ex.map keeps input
    # order, so the merged fact list is stable run to run (aside from the model's own noise).
    urls = {r.url for r in results}
    titles = {r.url: r.title for r in results}
    who = f"{name}, {role} at {company}" if role else f"{name} at {company}"
    batches = list(_chunks(results, CHUNK))
    if not batches:
        return []
    facts = []
    with ThreadPoolExecutor(max_workers=len(batches)) as ex:
        for part in ex.map(lambda b: _extract_chunk(who, b, urls, titles), batches):
            facts += part
    return facts
