#!/Users/macmini/.hermes/hermes-agent/venv/bin/python
"""mem0 OSS self-hosted memory backend — health probe.

Exit 0 = healthy. Exit 1 = problem found (each problem printed).
Run directly; shebang targets the Hermes venv python (sentence-transformers,
qdrant_client, mem0 SDK must all live there).

Checks (each independently useful for a 检查记忆系统 session):
  1. Qdrant reachability + collection point counts
  2. Active collection: point count + user_id distribution vs mem0.json
  3. Local bge embedder loads and encodes (dim check)
  4. End-to-end mem0 SDK search with the configured user_id

Verified against: Qdrant 1.19.0 @ 10.0.0.3:6333, qdrant_client 1.18.0,
sentence-transformers 5.7.0, mem0 SDK 2.0.10.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

HERMES_HOME = Path.home() / ".hermes"
MEM0_JSON = HERMES_HOME / "mem0.json"
# The plugin (plugins/memory/mem0/__init__.py) treats this literal as unset
# and falls back to gateway-native ids -> search fragmentation. Never use it.
DEFAULT_UNSET_USER_ID = "hermes-user"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="10.0.0.3")
    ap.add_argument("--port", type=int, default=6333)
    args = ap.parse_args()

    cfg = {}
    if MEM0_JSON.exists():
        cfg = json.loads(MEM0_JSON.read_text(encoding="utf-8"))
    else:
        print(f"[WARN] {MEM0_JSON} not found - config checks skipped")

    oss = cfg.get("oss", {})
    # collection_name lives under vector_store.config in mem0.json (not at
    # vector_store top level). Fallback = the current active hybrid collection.
    coll = (
        oss.get("vector_store", {}).get("config", {}).get(
            "collection_name", "hermes_memories_v2_hybrid"
        )
    )
    uid = cfg.get("user_id", "")
    problems: list[str] = []

    # 1. Qdrant
    try:
        from qdrant_client import QdrantClient

        client = QdrantClient(host=args.host, port=args.port)
        cols = client.get_collections().collections
        print(f"[ok] Qdrant @ {args.host}:{args.port} reachable, {len(cols)} collections")
        for c in cols:
            info = client.get_collection(c.name)
            marker = "  <- active" if c.name == coll else ""
            print(f"      {c.name}: {info.points_count} points{marker}")
    except Exception as e:
        print(f"[FAIL] Qdrant unreachable: {e}")
        return 1

    # 2. user_id config sanity
    if not uid:
        problems.append("mem0.json has no top-level user_id (plugin falls back to gateway id)")
        print(f"[FAIL] user_id missing in {MEM0_JSON}")
    elif uid == DEFAULT_UNSET_USER_ID:
        problems.append(
            "user_id is the default 'hermes-user' literal, which the plugin treats as UNSET "
            "-> gateway-id fallback -> search fragmentation"
        )
        print(f"[FAIL] user_id={uid!r} is the default literal - treated as unset by the plugin")
    else:
        print(f"[ok] mem0.json user_id = {uid!r}")

    # 3. Active collection payload sanity + user_id distribution
    try:
        scroll = client.scroll(coll, limit=1000, with_payload=True, with_vectors=False)
        pts = scroll[0]
        dist = Counter(p.payload.get("user_id") for p in pts)
        print(
            f"[info] {coll}: {len(pts)} points; user_id distribution: "
            f"{dict(dist) or '(no payload user_id - data invisible to search?)'}"
        )
        if uid and uid not in (DEFAULT_UNSET_USER_ID, ""):
            mismatched = sum(1 for p in pts if p.payload.get("user_id") != uid)
            if mismatched:
                problems.append(
                    f"{mismatched}/{len(pts)} points carry user_id != {uid!r} "
                    "-> those memories are invisible to mem0_search"
                )
                print(f"[FAIL] {mismatched}/{len(pts)} points have a different user_id than mem0.json")
    except Exception as e:
        print(f"[FAIL] cannot scroll {coll}: {e}")
        return 1

    # 4. Embedder
    try:
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer("BAAI/bge-small-zh-v1.5", device="cpu")
        vec = model.encode("记忆系统健康检查", normalize_embeddings=True)
        print(f"[ok] embedder BAAI/bge-small-zh-v1.5 -> dim {vec.shape[0]}")
    except Exception as e:
        problems.append(f"embedder failed: {e}")
        print(f"[FAIL] embedder: {e}")

    # 5. End-to-end mem0 search (expanded config + mandatory filters)
    if uid and uid != DEFAULT_UNSET_USER_ID:
        try:
            from mem0 import Memory

            m = Memory.from_config(
                {
                    "version": "v1.1",
                    "vector_store": oss["vector_store"],
                    "embedder": oss["embedder"],
                    "llm": oss["llm"],
                }
            )
            res = m.search("用户家庭网络配置", limit=3, filters={"user_id": uid})
            hits = res.get("results", [])
            if hits:
                print(f"[ok] mem0 search hit {len(hits)} rows; top score {hits[0].get('score', 0):.3f}")
            else:
                problems.append("mem0 search returned 0 hits despite data present")
                print("[FAIL] mem0 search returned 0 hits")
        except Exception as e:
            problems.append(f"mem0 search failed: {e}")
            print(f"[FAIL] mem0 search: {e}")
    else:
        print("[skip] mem0 search test (no usable user_id)")

    print()
    if problems:
        print("PROBLEMS:")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("HEALTHY: mem0 OSS backend OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
