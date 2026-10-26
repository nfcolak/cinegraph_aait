#!/usr/bin/env python3
"""
Score the agent on tests/intent_eval.jsonl (a report, not a test: always exits 0).

Loads the real graph and embeddings the way server/api.py warm() does, asks every
question through Responser.generate_response and prints a table per category.

    env -u PYTHONPATH .venv/bin/python -B scripts/eval_intent.py [--out PATH] [--limit N]

Per row:
  answer_ok   an expect_any label occurs in the answer (case-insensitive). When the row
              has expect_all, every item must occur (an item may be a list of alternatives).
              Rows with empty expect_any are unanswerable: ok when the answer is a miss.
  relation_ok last_meta['relation'] equals the gold relation (gold None: meta has none).
  subject_ok  last_meta['entity_uri'] ends with subject_qid (None when the row has no gold QID).
"""

import argparse
import contextlib
import io
import json
import os
import sys
import time
from collections import OrderedDict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

DEFAULT_SET = os.path.join(ROOT, "tests", "intent_eval.jsonl")
MISS_MARKERS = (
    "could not", "not found", "no answer", "unable", "cannot", "can't", "not a recommendation",
    "no information", "not in the", "does not", "doesn't", "no result", "not recognized",
    "relation not", "please rephrase", "no name in the graph",
)


def load_rows(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _has(answer_l, item):
    if isinstance(item, list):
        return any(_has(answer_l, x) for x in item)
    return item.lower() in answer_l


def answer_ok(row, answer):
    answer_l = (answer or "").lower()
    expect_any = row.get("expect_any") or []
    if not expect_any:
        return (not answer_l.strip()) or any(m in answer_l for m in MISS_MARKERS)
    if row.get("expect_all"):
        return all(_has(answer_l, it) for it in row["expect_all"])
    return any(_has(answer_l, it) for it in expect_any)


def subject_ok(row, meta):
    qid = row.get("subject_qid")
    if not qid:
        return None
    uri = meta.get("entity_uri")
    return bool(uri) and str(uri).endswith("/" + qid)


def load_agent():
    from core.data import build_label_maps, load_embeddings, load_graph
    from core.responser import Responser

    graph = load_graph()
    try:
        ent, rel, ent_ids, rel_ids, id_to_ent = load_embeddings()
        responser = Responser(ent, rel, ent_ids, rel_ids, id_to_ent)
    except Exception as exc:  # embeddings are optional
        print(f"[eval] embeddings unavailable: {exc}")
        responser = Responser()
    ent_to_lbl, _, _ = build_label_maps(graph)
    try:  # present once the linker exists; the baseline runs without it
        from core.linker import get_linker
        get_linker(graph, ent_to_lbl)
    except Exception:
        pass
    return graph, responser


def run(rows, graph, responser):
    results = []
    for i, row in enumerate(rows, 1):
        t0 = time.time()
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                answer = responser.generate_response(row["question"], graph)
            err = None
        except Exception as exc:
            answer, err = "", f"{type(exc).__name__}: {exc}"
        meta = dict(getattr(responser, "last_meta", {}) or {})
        res = {
            "id": row["id"],
            "category": row["category"],
            "question": row["question"],
            "answer": answer if isinstance(answer, str) else str(answer),
            "route": meta.get("route"),
            "relation": meta.get("relation"),
            "entity_uri": meta.get("entity_uri"),
            "answer_ok": answer_ok(row, answer if isinstance(answer, str) else str(answer)),
            "relation_ok": (meta.get("relation") == row["relation"]) if row.get("relation")
            else not meta.get("relation"),
            "subject_ok": subject_ok(row, meta),
            "seconds": round(time.time() - t0, 3),
            "error": err,
        }
        results.append(res)
        print(f"[{i}/{len(rows)}] {'ok ' if res['answer_ok'] else 'bad'} {row['id']} {row['question']}")
    return results


def table(results):
    cats = OrderedDict()
    for r in results:
        cats.setdefault(r["category"], []).append(r)

    def cell(vals):
        vals = [v for v in vals if v is not None]
        return f"{sum(vals)}/{len(vals)}" if vals else "-"

    lines = [f"{'category':<22}{'rows':>5}{'answer_ok':>11}{'relation_ok':>13}{'subject_ok':>12}",
             "-" * 63]
    for cat, rs in list(cats.items()) + [("OVERALL", results)]:
        if cat == "OVERALL":
            lines.append("-" * 63)
        lines.append(f"{cat:<22}{len(rs):>5}{cell([r['answer_ok'] for r in rs]):>11}"
                     f"{cell([r['relation_ok'] for r in rs]):>13}{cell([r['subject_ok'] for r in rs]):>12}")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--set", default=DEFAULT_SET, help="evaluation file (jsonl)")
    ap.add_argument("--out", help="write per-row results as JSON to this path")
    ap.add_argument("--limit", type=int, help="only the first N rows")
    args = ap.parse_args()

    rows = load_rows(args.set)
    if args.limit:
        rows = rows[: args.limit]
    graph, responser = load_agent()
    results = run(rows, graph, responser)
    summary = table(results)
    print("\n" + summary)

    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump({"summary": summary.split("\n"), "rows": results}, f, ensure_ascii=False, indent=1)
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
