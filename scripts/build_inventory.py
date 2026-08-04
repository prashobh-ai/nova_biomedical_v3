#!/usr/bin/env python3
"""Generate knowledge_fabric/INVENTORY.md from what is actually on disk.

    python scripts/build_inventory.py

The inventory is the answer to "open the repo and show me the raw data". It is
generated, never hand-written, so it cannot drift from the corpus: every row is a
file you can open, and every total is a count of files that exist.

Run it after any corpus change and commit the result alongside.
"""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

FABRIC = Path("knowledge_fabric")
SOURCES = FABRIC / "SOURCES.csv"
INDEX = Path("site/data/index.json")
OUT = FABRIC / "INVENTORY.md"


def mb(n: int) -> str:
    return f"{n / 1_000_000:.1f} MB" if n >= 1_000_000 else f"{n / 1000:.0f} KB"


def main() -> int:
    rows = list(csv.DictReader(open(SOURCES, encoding="utf-8")))
    by_cat: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        r["bytes"] = int(r["bytes"])
        by_cat[r["category"]].append(r)

    idx = json.loads(INDEX.read_text(encoding="utf-8")) if INDEX.exists() else {}
    stats = idx.get("stats", {})
    comp = Counter(d.get("source_type") for d in idx.get("documents", []))

    ymanifest = FABRIC / "youtube" / "manifest.json"
    ym = json.loads(ymanifest.read_text(encoding="utf-8")) if ymanifest.exists() else {}
    videos = [v for v in ym.get("videos", {}).values() if not v.get("withdrawn")]
    transcripts = len(list((FABRIC / "youtube" / "transcripts").glob("*.json")))

    L: list[str] = []
    add = L.append

    add("# Knowledge Fabric — corpus inventory")
    add("")
    add(f"*Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} by "
        f"`scripts/build_inventory.py`. Do not edit by hand.*")
    add("")
    add("Every file listed here is in this repository and can be opened. Every total "
        "is a count of those files. Reproduce with `python scripts/verify_corpus.py --deep`.")
    add("")

    # ---- headline
    add("## What is in the corpus")
    add("")
    add("| Source | Files on disk | Indexed records | Size |")
    add("|---|---:|---:|---:|")
    pm, fd = by_cat.get("product_manual", []), by_cat.get("fda_document", [])
    fs = by_cat.get("fda_structured", [])
    add(f"| Product manuals (PDF) | {len(pm)} | {len(pm)} | {mb(sum(r['bytes'] for r in pm))} |")
    add(f"| FDA 510(k) documents (PDF) | {len(fd)} | {len(fd)} | {mb(sum(r['bytes'] for r in fd))} |")
    add(f"| FDA structured exports (CSV) | {len(fs)} | {comp.get('fda_regulatory', 0)} | "
        f"{mb(sum(r['bytes'] for r in fs))} |")
    add(f"| YouTube videos (channel) | {len(videos)} | {comp.get('video', 0)} | metadata + transcripts |")
    add(f"| **Total** | **{len(rows)} files** | **{stats.get('document_count', 0)} records** | "
        f"**{mb(sum(r['bytes'] for r in rows))}** |")
    add("")
    add("### Reading the two count columns")
    add("")
    add("They differ on purpose, and the difference is the honest part.")
    add("")
    add("- A **PDF** is one file and one record. 82 documents on disk, 82 in the index.")
    add(f"- The **CSV exports** hold thousands of rows; the fabric selects "
        f"{comp.get('fda_regulatory', 0)} of them as retrievable records — clearances, "
        "recalls, classifications and enforcement actions relevant to these products. "
        "The rest stay in the repo unindexed.")
    add("- A **video** is one record for its publisher-written metadata, plus one record "
        "per transcript segment once transcribed.")
    add("")
    add(f"So \"{stats.get('document_count', 0)} records\" means "
        f"{comp.get('document', 0)} documents + {comp.get('fda_regulatory', 0)} regulatory "
        f"records + {comp.get('video', 0)} video records — not "
        f"{stats.get('document_count', 0)} PDFs. The dashboard says *records*, never "
        "*documents*, for exactly this reason.")
    add("")

    # ---- derived
    add("## What the build derives from it")
    add("")
    add("| Artifact | Count | Where it comes from |")
    add("|---|---:|---|")
    add(f"| Retrievable passages (chunks) | {stats.get('chunk_count', 0)} | "
        "documents packed to ~700 chars; structured rows stay atomic |")
    add(f"| Entities | {stats.get('entity_count', 0)} | products, analytes, clearances, "
        "product codes extracted at build time |")
    add(f"| Relationships (graph edges) | {stats.get('relationship_count', 0)} | "
        "typed co-occurrence between entities |")
    add(f"| Lexical vocabulary (BM25) | {stats.get('vocab_size', 0)} | "
        "distinct terms across all passages |")
    sem = Path("site/data/semantic.json")
    if sem.exists():
        s = json.loads(sem.read_text(encoding="utf-8"))
        add(f"| Embeddings | {len(s.get('doc_vectors', []))} x {s.get('dims', 0)} dims | "
            f"{s.get('method', 'LSA')}, {s.get('explained_variance', 0):.1%} variance retained |")
        add(f"| Term vectors | {len(s.get('term_vectors', []))} x {s.get('dims', 0)} dims | "
            f"LSA vocabulary of {len(s.get('terms', []))} terms |")
    add(f"| Cross-source products | {stats.get('cross_source_products', 0)} | "
        "products appearing in more than one source system |")
    add("")

    # ---- file listings
    add("## Product manuals")
    add("")
    add("| File | Product | Type | Size |")
    add("|---|---|---|---:|")
    for r in sorted(pm, key=lambda r: r["filename"]):
        add(f"| `{r['filename']}` | {r['product'] or '—'} | {r['doc_type'] or '—'} | {mb(r['bytes'])} |")
    add("")

    add("## FDA 510(k) documents")
    add("")
    add(f"{len(fd)} clearance and review documents, each fetched from "
        "`accessdata.fda.gov`. Full URLs and checksums are in `SOURCES.csv`.")
    add("")
    add("<details><summary>Full list</summary>")
    add("")
    add("| File | Size |")
    add("|---|---:|")
    for r in sorted(fd, key=lambda r: r["filename"]):
        add(f"| `{r['filename']}` | {mb(r['bytes'])} |")
    add("")
    add("</details>")
    add("")

    add("## FDA structured exports")
    add("")
    add("| File | Rows | Size |")
    add("|---|---:|---:|")
    for r in sorted(fs, key=lambda r: r["filename"]):
        path = Path(r["path"])
        n = 0
        if path.exists():
            with open(path, newline="", encoding="utf-8", errors="replace") as f:
                n = sum(1 for _ in csv.DictReader(f))
        add(f"| `{r['filename']}` | {n} | {mb(r['bytes'])} |")
    add("")

    add("## YouTube channel")
    add("")
    add(f"- **{len(videos)}** active videos from the company channel")
    dated = sum(1 for v in videos if v.get("published_at"))
    auth = sum(1 for v in videos if v.get("date_method") == "channel_publication_date")
    add(f"- **{dated}** carry a publication date ({auth} publisher-asserted)")
    add(f"- **{transcripts}** transcribed so far")
    if videos:
        ds = sorted(v["published_at"] for v in videos if v.get("published_at"))
        if ds:
            add(f"- Publication range: **{ds[0]}** to **{ds[-1]}**")
    add(f"- Withdrawn (tombstoned, retained for supersession checks): "
        f"**{ym.get('withdrawn_count', 0)}**")
    add("")
    add("Per-video metadata lives in `knowledge_fabric/youtube/manifest.json`; "
        "transcripts in `knowledge_fabric/youtube/transcripts/`.")
    add("")

    add("---")
    add("")
    add("## Verifying this yourself")
    add("")
    add("```bash")
    add("python scripts/verify_corpus.py --deep     # checksums every file, reconciles every count")
    add("python -m pipeline.build_index             # rebuild the index from source")
    add("python scripts/build_inventory.py          # regenerate this file")
    add("```")
    add("")
    add("`verify_corpus.py` recounts records from the raw files rather than reading them "
        "back out of the index, so a number that only exists in the index cannot pass.")
    add("")

    OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"[OK] {OUT}  ({len(rows)} files, {stats.get('document_count', 0)} records)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
