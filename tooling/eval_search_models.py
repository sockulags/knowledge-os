"""Compare embedding models for local semantic search (issue #102).

Runs each candidate on a small bilingual (Swedish/English) set of pages and
queries: some worded differently from the page, some in the other language,
and some that match nothing. Prints, per model, how often the right page ranks
first, the mean reciprocal rank, how far the best score of a real match stands
above the median compared with a query that matches nothing, the download size,
and the time to embed the pages.

    pip install onnxruntime tokenizers numpy huggingface_hub
    python tooling/eval_search_models.py            # every candidate
    python tooling/eval_search_models.py e5-small   # one

Run by .github/workflows/eval-search-models.yml, which can reach Hugging Face.
"""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass

import numpy as np

PAGES = {
    "retry-policy": ("Retry policy", "Requests are retried three times with an exponential backoff that starts at 200 ms."),
    "retry-alerts": ("Retry alerts", "When the third retry fails, the on-call engineer is paged through PagerDuty."),
    "cache-warmup": ("Cache warmup", "Warm the cache on every deploy so the first users do not wait."),
    "deploy-checklist": ("Deploy checklist", "Before deploying, run the tests, check the dashboards, and announce the deploy in the channel."),
    "onboarding": ("Onboarding", "New team members get a laptop and access to GitHub on their first day."),
    "api-versioning": ("API versioning", "Breaking changes to the public API get a new major version; old versions live for six months."),
    "incident-review": ("Incident review", "After an outage we write a blameless review within five working days."),
    "code-review": ("Code review", "Every pull request needs one approving review before it is merged."),
    "semester": ("Semester", "Anställda har 25 dagars semester per år. Semester ansöks i HR-systemet."),
    "kaffemaskinen": ("Kaffemaskinen", "Kaffemaskinen på tredje våningen avkalkas varje fredag."),
    "brandskydd": ("Brandskydd", "Brandsläckare finns vid varje trapphus. Utrymningsplatsen är parkeringen."),
    "backup": ("Databasbackup", "Databasen säkerhetskopieras varje natt klockan två och sparas i trettio dagar."),
    "lon": ("Löneutbetalning", "Lönen betalas ut den 25:e varje månad."),
    "distansarbete": ("Distansarbete", "Du får arbeta hemifrån tre dagar i veckan efter överenskommelse med din chef."),
    "reseersattning": ("Reseersättning", "Tjänsteresor bokas via resebyrån och kvitton lämnas in inom en månad."),
    "losenord": ("Lösenord", "Lösenord byts var nittionde dag och måste ha minst tolv tecken."),
}

# (query, expected page); None expects nothing.
QUERIES = [
    ("retry count", "retry-policy"),
    ("how long do we wait between attempts", "retry-policy"),
    ("hur många gånger försöker vi igen när en förfrågan misslyckas", "retry-policy"),
    ("vem larmas när det fortsätter att fela", "retry-alerts"),
    ("what happens when a deploy is released", "deploy-checklist"),
    ("förbered cachen inför lansering", "cache-warmup"),
    ("första dagen för nyanställda", "onboarding"),
    ("hur länge stöds gamla API-versioner", "api-versioning"),
    ("postmortem after downtime", "incident-review"),
    ("granskning innan merge", "code-review"),
    ("vacation days", "semester"),
    ("how do I clean the coffee machine", "kaffemaskinen"),
    ("fire safety", "brandskydd"),
    ("hur ofta tas backup", "backup"),
    ("when is salary paid", "lon"),
    ("working from home", "distansarbete"),
    ("travel expenses and receipts", "reseersattning"),
    ("password rules", "losenord"),
    ("kubernetes autoscaling", None),
    ("the weather in Paris", None),
    ("recept på kanelbullar", None),
    ("quarterly sales targets", None),
]


@dataclass(frozen=True)
class Candidate:
    key: str
    repo: str
    onnx: str
    pooling: str  # "mean", "cls", "last", or an output name holding the sentence embedding
    query: str = "{}"
    passage: str = "{}"
    extra: tuple[str, ...] = ()  # more files the ONNX model needs (external data)


CANDIDATES = [
    Candidate("e5-small-q8", "Xenova/multilingual-e5-small", "onnx/model_quantized.onnx", "mean", "query: {}", "passage: {}"),
    Candidate("e5-small-fp32", "Xenova/multilingual-e5-small", "onnx/model.onnx", "mean", "query: {}", "passage: {}"),
    Candidate("e5-base-q8", "Xenova/multilingual-e5-base", "onnx/model_quantized.onnx", "mean", "query: {}", "passage: {}"),
    Candidate("bge-m3-q8", "Xenova/bge-m3", "onnx/model_quantized.onnx", "cls"),
    Candidate(
        "gemma-300m-q8",
        "onnx-community/embeddinggemma-300m-ONNX",
        "onnx/model_quantized.onnx",
        "sentence_embedding",
        "task: search result | query: {}",
        "title: none | text: {}",
    ),
    Candidate(
        "qwen3-0.6b-q8",
        "onnx-community/Qwen3-Embedding-0.6B-ONNX",
        "onnx/model_quantized.onnx",
        "last",
        "Instruct: Given a web search query, retrieve relevant passages that answer the query\nQuery:{}",
        "{}",
    ),
]


def load(candidate: Candidate):  # type: ignore[no-untyped-def]
    import onnxruntime as ort
    from huggingface_hub import hf_hub_download
    from tokenizers import Tokenizer

    model = hf_hub_download(candidate.repo, candidate.onnx)
    for name in candidate.extra:
        hf_hub_download(candidate.repo, name)
    data = model + "_data"
    size = os.path.getsize(model) + (os.path.getsize(data) if os.path.exists(data) else 0)
    tokenizer = Tokenizer.from_file(hf_hub_download(candidate.repo, "tokenizer.json"))
    tokenizer.enable_truncation(512)
    tokenizer.enable_padding(direction="left" if candidate.pooling == "last" else "right")
    session = ort.InferenceSession(model, providers=["CPUExecutionProvider"])
    return tokenizer, session, size


def embed(candidate: Candidate, tokenizer, session, texts: list[str]) -> np.ndarray:  # type: ignore[no-untyped-def]
    encoded = tokenizer.encode_batch(texts)
    ids = np.array([item.ids for item in encoded], dtype=np.int64)
    mask = np.array([item.attention_mask for item in encoded], dtype=np.int64)
    names = {item.name for item in session.get_inputs()}
    feed = {"input_ids": ids, "attention_mask": mask}
    if "token_type_ids" in names:
        feed["token_type_ids"] = np.zeros_like(ids)
    if "position_ids" in names:
        feed["position_ids"] = np.cumsum(mask, axis=1) - 1
    outputs = {item.name: value for item, value in zip(session.get_outputs(), session.run(None, feed))}
    if candidate.pooling in outputs:
        vectors = outputs[candidate.pooling]
    else:
        hidden = outputs.get("last_hidden_state", next(iter(outputs.values())))
        if candidate.pooling == "cls":
            vectors = hidden[:, 0]
        elif candidate.pooling == "last":
            vectors = hidden[:, -1]
        else:
            vectors = (hidden * mask[..., None]).sum(1) / mask.sum(1, keepdims=True)
    vectors = vectors.astype(np.float32)
    return vectors / np.linalg.norm(vectors, axis=1, keepdims=True)


def evaluate(candidate: Candidate) -> dict[str, object]:
    tokenizer, session, size = load(candidate)
    ids = list(PAGES)
    passages = [candidate.passage.format(f"{title}\n{body}") for title, body in PAGES.values()]
    started = time.perf_counter()
    pages = np.concatenate([embed(candidate, tokenizer, session, passages[i : i + 8]) for i in range(0, len(passages), 8)])
    seconds = time.perf_counter() - started
    top1 = 0
    reciprocal = []
    real_margins = []
    empty_margins = []
    misses = []
    for query, expected in QUERIES:
        scores = pages @ embed(candidate, tokenizer, session, [candidate.query.format(query)])[0]
        order = list(np.argsort(-scores))
        margin = float(scores[order[0]] - np.median(scores))
        if expected is None:
            empty_margins.append(margin)
            continue
        rank = order.index(ids.index(expected)) + 1
        reciprocal.append(1 / rank)
        real_margins.append(margin)
        if rank == 1:
            top1 += 1
        else:
            misses.append(f"{query} -> {ids[order[0]]}")
    answered = sum(1 for _, expected in QUERIES if expected is not None)
    return {
        "model": candidate.key,
        "top1": f"{top1}/{answered}",
        "mrr": round(float(np.mean(reciprocal)), 3),
        "real_margin": round(float(np.mean(real_margins)), 3),
        "empty_margin": round(float(np.mean(empty_margins)), 3),
        "size_mb": round(size / 1e6),
        "embed_pages_s": round(seconds, 2),
        "misses": misses,
    }


def main(argv: list[str]) -> int:
    wanted = [candidate for candidate in CANDIDATES if not argv or candidate.key in argv]
    for candidate in wanted:
        try:
            print(json.dumps(evaluate(candidate), ensure_ascii=False), flush=True)
        except Exception as exc:  # a candidate that cannot load is reported, not fatal
            print(json.dumps({"model": candidate.key, "error": f"{type(exc).__name__}: {exc}"[:300]}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
