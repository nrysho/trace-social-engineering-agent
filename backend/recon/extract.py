"""pull sourced facts from search results with the llm.

- the model returns json facts, each tagged with one of the provided source urls
- we keep only facts whose url was actually in the batch, so nothing is invented
"""
import json
import re

from backend import llm
from schemas import Fact, FACT_CATEGORIES

CHUNK = 6             # results per llm call, to bound the prompt
CONTENT_CHARS = 1500  # how much page text per result we show the model

SYSTEM = (
    "You extract facts about a person from web search results for an authorised research "
    "exercise. Return JSON only: {\"facts\": [{\"category\": ..., \"value\": ..., "
    "\"source_url\": ..., \"confidence\": 0-1}]}. category is one of: "
    + ", ".join(FACT_CATEGORIES) + ". value is one short factual sentence. source_url MUST be "
    "copied exactly from the result the fact came from. Do not infer or guess; state only what "
    "the text supports. Skip anything not clearly about this person."
)
JSON_MODE = {"type": "json_object"}


def _chunks(items, n):
    for i in range(0, len(items), n):
        yield items[i:i + n]


def _slice(text):
    m = re.search(r"\{.*\}", text, re.S)  # tolerate fences or prose around the json
    return m.group(0) if m else text


def extract_facts(name, company, results):
    urls = {r.url for r in results}
    titles = {r.url: r.title for r in results}
    facts = []
    for batch in _chunks(results, CHUNK):
        block = "\n\n".join(
            f"URL: {r.url}\nTITLE: {r.title}\nTEXT: {(r.content or r.snippet)[:CONTENT_CHARS]}"
            for r in batch
        )
        user = f"Person: {name} ({company}).\n\nResults:\n{block}"
        try:
            text = llm.chat([{"role": "system", "content": SYSTEM},
                             {"role": "user", "content": user}], response_format=JSON_MODE)
            data = json.loads(_slice(text))
        except Exception as e:
            print(f"  extract chunk failed: {e}")
            continue
        for f in data.get("facts", []):
            url = f.get("source_url", "")
            if url in urls and f.get("category") in FACT_CATEGORIES and f.get("value"):
                facts.append(Fact(
                    category=f["category"], value=str(f["value"]).strip(),
                    source_url=url, source_title=titles.get(url, ""),
                    confidence=float(f.get("confidence", 0.5)),
                ))
    return facts
