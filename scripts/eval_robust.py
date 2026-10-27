#!/usr/bin/env python3
"""
Score the agent on tests/robust_eval.jsonl (a report, not a test: always exits 0).

Loads the app once in process the way the server does (server.api.warm()) and asks every
question through server.api.answer, the function behind POST /api/chat. No uvicorn, no HTTP.

    env -u PYTHONPATH .venv/bin/python -B scripts/eval_robust.py [--set PATH] [--family F]
                                                                 [--limit N] [--out PATH]

The scored text is the reply's answer text plus the titles of its cards. Pass rules per
row route (see openspec/changes/question-robustness/design.md section 3):
  factual         reply route is factual; at least min_hits of expect_any occur; every expect_all
                  item occurs (an item may be a list of alternatives); expect_count occurs as a
                  number; no forbid label occurs.
  recommendation  reply route is recommendation; at least 3 recommended films; every seed_qid is
                  among the reported seeds; no recommended film carries a seed's title; no forbid.
  multimedia      reply route is multimedia with an image.
  miss            the answer says what is missing or that it cannot answer, shows no cards and
                  no forbid label.
A failed row gets a cause: route, parse, link, graph_gap, answer_text, recommender, crash.
"""

import argparse
import json
import os
import re
import sys
import time
import unicodedata
from collections import OrderedDict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

DEFAULT_SET = os.path.join(ROOT, "tests", "robust_eval.jsonl")
FAMILIES = [
    "cast_filmography", "crew_filmography", "company_films", "count", "filtered_filmography",
    "shared", "overview", "film_fact", "character_series", "multi_part", "recommendation",
    "multimedia", "noise", "typo", "missing_data", "out_of_scope",
]
MIN_RECOMMENDED = 3
HEAD_CHARS = 140
# Phrases of an answer that reports a gap or refuses (matched on the lower-cased reply text).
MISS_MARKERS = (
    "could not", "not found", "no answer", "unable", "cannot", "can't", "not a recommendation",
    "no information", "not in the", "does not", "doesn't", "no result", "not recognized",
    "relation not", "please rephrase", "no name in the graph", "the graph has no",
    "graph has no", "no entity", "not sure", "don't know", "do not know", "don't have",
    "do not have", "only answer", "only about", "ask me about", "i can answer", "i can help",
    "outside", "no film", "not a film",
)


def load_rows(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                print(f"[eval] {path}:{n} is not JSON: {exc}", file=sys.stderr)
    return rows


def norm(text):
    """Lower case, no accents, punctuation as single spaces, padded so ' a b ' matches whole words."""
    s = unicodedata.normalize("NFKD", text or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).casefold()
    s = re.sub(r"[^0-9a-z]+", " ", s)
    return f" {s.strip()} "


def has(text_n, item):
    if isinstance(item, list):
        return any(has(text_n, x) for x in item)
    return norm(item) in text_n


def has_number(text, n):
    return re.search(rf"(?<![\d,.]){int(n)}(?![\d,]|\.\d)", text or "") is not None


def card_titles(cards):
    return [c.get("label") for c in cards or [] if c.get("label")]


def scored_text(reply):
    return " ".join([reply.get("answer") or ""] + card_titles(reply.get("cards")))


def says_miss(reply):
    text = (reply.get("answer") or "").lower()
    return (not reply.get("ok", True)) or (not text.strip()) or any(m in text for m in MISS_MARKERS)


def reply_qid(reply):
    return (reply.get("subject") or {}).get("qid")


# ---------- checks per route ----------

def check_factual(row, reply):
    """Returns (passed, cause, reasons)."""
    reasons = []
    text = scored_text(reply)
    text_n = norm(text)
    if reply.get("route") != "factual":
        reasons.append(f"route is {reply.get('route')}")
    expect_any = row.get("expect_any") or []
    if expect_any:
        hits = [x for x in expect_any if has(text_n, x)]
        need = row.get("min_hits", 1)
        if len(hits) < need:
            reasons.append(f"{len(hits)}/{need} expect_any hits")
    for item in row.get("expect_all") or []:
        if not has(text_n, item):
            reasons.append(f"missing {item!r}")
    if row.get("expect_count") is not None and not has_number(reply.get("answer"), row["expect_count"]):
        reasons.append(f"count {row['expect_count']} not in answer")
    for bad in row.get("forbid") or []:
        if has(text_n, bad):
            reasons.append(f"forbidden {bad!r}")
    if not reasons:
        return True, None, []
    return False, factual_cause(row, reply), reasons


def factual_cause(row, reply):
    if (reply.get("answer") or "").startswith("Could not generate an answer"):
        return "crash"
    route = reply.get("route")
    if route in ("recommendation", "multimedia"):
        return "route"
    reading = reply.get("reading")  # None when the intent parser did not claim the question
    if route == "prediction":
        return "parse"
    if row.get("relation") and reply.get("relation") and reply["relation"] != row["relation"]:
        return "parse"
    if row.get("subject_qid") and reply_qid(reply) != row["subject_qid"]:
        return "link" if reading else "parse"
    if not reading:
        return "answer_text" if reply_qid(reply) else "parse"
    if not reply_qid(reply) and not reading.get("subject"):
        return "link"
    return "answer_text"


def check_recommendation(row, reply):
    reasons = []
    text_n = norm(scored_text(reply))
    recs = card_titles(reply.get("cards"))
    if reply.get("route") != "recommendation":
        reasons.append(f"route is {reply.get('route')}")
    elif len(recs) < MIN_RECOMMENDED:
        reasons.append(f"{len(recs)} recommended films")
    seeds = {c.get("qid"): c.get("label") for c in reply.get("seeds") or []}
    for q in row.get("seed_qids") or []:
        if q not in seeds:
            reasons.append(f"seed {q} not reported")
    seed_titles = {norm(t) for t in seeds.values() if t}
    if reply.get("route") == "recommendation" and any(norm(t) in seed_titles for t in recs):
        reasons.append("a recommended film is a seed")
    for bad in row.get("forbid") or []:
        if has(text_n, bad):
            reasons.append(f"forbidden {bad!r}")
    if not reasons:
        return True, None, []
    if (reply.get("answer") or "").startswith("Could not generate an answer"):
        return False, "crash", reasons
    if reply.get("route") != "recommendation":
        return False, "route", reasons
    return False, "recommender", reasons


def check_multimedia(row, reply):
    reasons = []
    if reply.get("route") != "multimedia":
        reasons.append(f"route is {reply.get('route')}")
    elif not reply.get("image"):
        reasons.append("no image")
    if not reasons:
        return True, None, []
    if (reply.get("answer") or "").startswith("Could not generate an answer"):
        return False, "crash", reasons
    if reply.get("route") != "multimedia":
        return False, "route", reasons
    return False, "link", reasons  # multimedia route, but no picture found for the entity


def check_miss(row, reply):
    reasons = []
    text_n = norm(scored_text(reply))
    if not says_miss(reply):
        reasons.append("answer does not report a gap")
    if reply.get("cards"):
        reasons.append(f"cards shown: {card_titles(reply['cards'])[:3]}")
    for bad in row.get("forbid") or []:
        if has(text_n, bad):
            reasons.append(f"forbidden {bad!r}")
    if not reasons:
        return True, None, []
    if (reply.get("answer") or "").startswith("Could not generate an answer"):
        return False, "crash", reasons
    return False, "graph_gap", reasons


CHECKS = {
    "factual": check_factual,
    "recommendation": check_recommendation,
    "multimedia": check_multimedia,
    "miss": check_miss,
}


def score_row(row, api):
    t0 = time.time()
    try:
        reply = api.answer(row["question"])
    except Exception as exc:  # the api catches generator errors; this is anything left over
        return {"passed": False, "cause": "crash", "reasons": [repr(exc)], "reply": None,
                "ms": round((time.time() - t0) * 1000)}
    check = CHECKS.get(row.get("route"), check_factual)
    passed, cause, reasons = check(row, reply)
    return {"passed": passed, "cause": cause, "reasons": reasons, "reply": reply,
            "ms": round((time.time() - t0) * 1000)}


def head(text, n=HEAD_CHARS):
    text = re.sub(r"\s+", " ", text or "").strip()
    return text if len(text) <= n else text[: n - 1] + "…"


def summarize(row, result):
    reply = result["reply"] or {}
    return {
        "id": row["id"],
        "family": row["family"],
        "question": row["question"],
        "expected_route": row.get("route"),
        "passed": result["passed"],
        "cause": result["cause"],
        "reasons": result["reasons"],
        "route": reply.get("route"),
        "relation": reply.get("relation"),
        "subject": reply.get("subject") and {"qid": reply["subject"].get("qid"), "label": reply["subject"].get("label")},
        "answer": reply.get("answer"),
        "cards": card_titles(reply.get("cards")),
        "seeds": card_titles(reply.get("seeds")),
        "image": bool(reply.get("image")),
        "ok": reply.get("ok"),
        "latency_ms": reply.get("latency_ms", result["ms"]),
    }


def print_table(results):
    fams = OrderedDict((f, [0, 0]) for f in FAMILIES)
    for r in results:
        t = fams.setdefault(r["family"], [0, 0])
        t[0] += 1
        t[1] += 1 if r["passed"] else 0
    print(f"\n{'family':<22}{'rows':>6}{'pass':>6}{'pass %':>8}")
    for fam, (n, ok) in fams.items():
        if n:
            print(f"{fam:<22}{n:>6}{ok:>6}{100 * ok / n:>7.1f}%")
    n = sum(v[0] for v in fams.values())
    ok = sum(v[1] for v in fams.values())
    print(f"{'TOTAL':<22}{n:>6}{ok:>6}{(100 * ok / n if n else 0):>7.1f}%")


def print_failures(results):
    bad = [r for r in results if not r["passed"]]
    print(f"\nFailures: {len(bad)}")
    for r in sorted(bad, key=lambda r: (r["cause"] or "", r["id"])):
        print(f"- {r['id']} [{r['cause']}] {r['question']!r}")
        print(f"    {'; '.join(r['reasons'])}")
        print(f"    route={r['route']} relation={r['relation']} -> {head(r['answer'])!r}")
    causes = OrderedDict()
    for r in bad:
        causes[r["cause"]] = causes.get(r["cause"], 0) + 1
    print("By cause:", ", ".join(f"{c}={n}" for c, n in causes.items()) or "none")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--set", default=DEFAULT_SET, help="JSONL question set (default tests/robust_eval.jsonl)")
    ap.add_argument("--family", help="only rows of this family")
    ap.add_argument("--limit", type=int, help="only the first N rows (after --family)")
    ap.add_argument("--out", help="write every row and the table as JSON to this path")
    args = ap.parse_args()

    rows = load_rows(args.set)
    if args.family:
        rows = [r for r in rows if r.get("family") == args.family]
    if args.limit:
        rows = rows[: args.limit]
    if not rows:
        print("[eval] no rows to score")
        return 0

    from server import api  # imported late: it pulls in the whole app

    t0 = time.time()
    api.warm()
    print(f"[eval] app ready in {time.time() - t0:.0f}s; scoring {len(rows)} rows from {args.set}")

    results = []
    for i, row in enumerate(rows, 1):
        res = score_row(row, api)
        s = summarize(row, res)
        results.append(s)
        mark = "ok  " if s["passed"] else f"FAIL"
        print(f"[{i}/{len(rows)}] {mark} {row['id']} {row['question']!r}", file=sys.stderr)

    print_table(results)
    print_failures(results)

    if args.out:
        fams = OrderedDict()
        for r in results:
            t = fams.setdefault(r["family"], {"rows": 0, "pass": 0})
            t["rows"] += 1
            t["pass"] += 1 if r["passed"] else 0
        for t in fams.values():
            t["pass_pct"] = round(100 * t["pass"] / t["rows"], 1)
        total = {"rows": len(results), "pass": sum(1 for r in results if r["passed"])}
        total["pass_pct"] = round(100 * total["pass"] / total["rows"], 1)
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump({"set": os.path.relpath(args.set, ROOT), "families": fams, "total": total, "rows": results},
                      f, ensure_ascii=False, indent=1)
        print(f"[eval] wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
