#!/usr/bin/env python3
"""mem0 OSS tidy toolkit — enumerate / search / append-merge / delete.

Run with the RUNTIME venv python (the one `hermes doctor` reports as staged),
NOT the legacy checkout venv. Used by the 6-hourly memory-tidy cron and by
manual housekeeping when `mem0_search` tool access is unavailable.

Usage:
  mem0_tidy_ops.py dump  [out.txt]           # full enumeration via Qdrant scroll
  mem0_tidy_ops.py search "<query>" [limit]
  mem0_tidy_ops.py dryrun <ops.json>
  mem0_tidy_ops.py run    <ops.json>

ops.json is a list of either
  {"id": "<uuid>", "delete": true}
  {"id": "<uuid>", "append": "<text>", "prefix_old": "合并自 a, b", "prefix_new": "合并自 a, b, c"}
The "append" form reads the existing text with get() first, so long memories
never have to be re-typed (no transcription loss) and the merged result is
verified by comparing stored length against the intended length.
"""
import json
import os
import sys
from collections import Counter

CFG_PATH = os.path.expanduser("~/.hermes/mem0.json")


def _cfg():
    cfg = json.load(open(CFG_PATH))
    oss = cfg["oss"]
    return cfg, {
        "version": "v1.1",
        "vector_store": oss["vector_store"],
        "embedder": oss["embedder"],
        "llm": oss["llm"],
    }


def _memory():
    from mem0 import Memory

    cfg, conf = _cfg()
    return Memory.from_config(conf), cfg


def _payload(p):
    return p.payload.model_dump() if hasattr(p.payload, "model_dump") else dict(p.payload)


def dump(out_path=None):
    """Full enumeration. Qdrant scroll is the only lossless listing;
    m.search is semantic top-k and returns overlapping hits."""
    from qdrant_client import QdrantClient

    cfg, conf = _cfg()
    vs = conf["vector_store"]["config"]
    client = QdrantClient(host=vs["host"], port=vs["port"], timeout=30)
    coll = vs["collection_name"]
    points, offset = [], None
    while True:
        recs, offset = client.scroll(
            coll, limit=200, offset=offset, with_payload=True, with_vectors=False
        )
        points.extend(recs)
        if offset is None:
            break
    rows = [(p, _payload(p)) for p in points]
    lines = [
        f"RESULT collection={coll} user_id_cfg={cfg.get('user_id')} total_points={len(points)}",
        "user_id distribution: "
        + json.dumps(Counter(str(pl.get("user_id")) for _, pl in rows)),
    ]
    for p, pl in sorted(rows, key=lambda t: str(t[0].id)):
        data = pl.get("data") or pl.get("memory") or ""
        lines += [
            "---",
            f"ID: {p.id}",
            f"USER: {pl.get('user_id')} | CREATED: {pl.get('created_at')} | UPDATED: {pl.get('updated_at')}",
            "DATA: " + " ".join(str(data).split()),
        ]
    text = "\n".join(lines)
    if out_path:
        open(out_path, "w").write(text)
        print(f"wrote {len(text)} chars to {out_path}; total_points={len(points)}")
    else:
        print(text)


def search(query, limit=5):
    m, cfg = _memory()
    res = m.search(query, filters={"user_id": cfg["user_id"]}, limit=limit)
    rows = res.get("results", res) if isinstance(res, dict) else res
    for r in rows:
        print(f"[{r.get('score'):.3f}] {r.get('id')} :: {str(r.get('memory'))[:160]}")


def apply_ops(ops_path, dry=True):
    items = json.load(open(ops_path))
    m, _ = _memory()
    for it in items:
        if it.get("delete"):
            if dry:
                print("DELETE", it["id"])
            else:
                m.delete(memory_id=it["id"])
                print("DELETE ok", it["id"])
            continue
        cur = m.get(it["id"])
        text = cur.get("memory", "") if isinstance(cur, dict) else str(cur)
        new = text
        if it.get("prefix_old"):
            if it["prefix_old"] in new:
                new = new.replace(it["prefix_old"], it["prefix_new"])
            else:
                print("  !! prefix_old NOT FOUND in", it["id"])
        if it.get("append"):
            new = new.rstrip() + " " + it["append"]
        if dry:
            print(f"UPDATE {it['id']}: {len(text)} -> {len(new)} chars")
        else:
            m.update(memory_id=it["id"], data=new)
            back = m.get(it["id"])
            bt = back.get("memory", "") if isinstance(back, dict) else str(back)
            print(
                f"UPDATE ok {it['id']} new_len={len(new)} stored_len={len(bt)} "
                f"appended_present={it.get('append','')[:30] in bt}"
            )


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "dump"
    if cmd == "dump":
        dump(sys.argv[2] if len(sys.argv) > 2 else None)
    elif cmd == "search":
        search(sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 5)
    elif cmd in ("run", "dryrun"):
        apply_ops(sys.argv[2], dry=(cmd == "dryrun"))
    else:
        print(__doc__)
