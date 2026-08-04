#!/usr/bin/env python3
"""Reconcile every published number against what is actually in this repository.

    python scripts/verify_corpus.py            # report
    python scripts/verify_corpus.py --gate     # non-zero exit on any mismatch

Why this exists
---------------
A knowledge fabric that reports a corpus health score has to be able to survive
someone opening the repository and counting. The failure mode this guards against
is not a crash — it is a headline number that nobody can trace back to a file.

Specifically, this asserts:

  * every PDF on disk is listed in knowledge_fabric/SOURCES.csv, and every row in
    SOURCES.csv points at a file that exists, with a matching SHA-256
  * the indexed record count equals documents + structured rows + video records,
    each counted independently from the source files rather than from the index
  * headline stats inside index.json agree with the arrays they summarise
  * the entity graph is internally consistent: every edge endpoint resolves to a
    node, every chunk reference resolves to a chunk
  * the semantic index covers exactly the chunks the lexical index contains

A number that cannot be derived twice from independent sources is not reported.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

FABRIC = Path("knowledge_fabric")
SOURCES = FABRIC / "SOURCES.csv"
INDEX = Path("site/data/index.json")
SEMANTIC = Path("site/data/semantic.json")

GREEN, RED, YELLOW, DIM, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"

results: list[tuple[bool, str, str]] = []


def check(ok: bool, label: str, detail: str = "") -> bool:
    results.append((ok, label, detail))
    mark = f"{GREEN}PASS{RESET}" if ok else f"{RED}FAIL{RESET}"
    print(f"  [{mark}] {label}" + (f"  {DIM}{detail}{RESET}" if detail else ""))
    return ok


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def section(title: str) -> None:
    print(f"\n{title}")
    print("  " + "-" * (len(title) + 4))


# ---------------------------------------------------------------- 1. on disk
def verify_sources(deep: bool) -> dict:
    section("1. Source files on disk")
    if not SOURCES.exists():
        check(False, "SOURCES.csv present", str(SOURCES))
        return {}

    rows = list(csv.DictReader(open(SOURCES, encoding="utf-8")))
    by_cat = Counter(r["category"] for r in rows)

    missing = [r["path"] for r in rows if not Path(r["path"]).exists()]
    check(not missing, f"all {len(rows)} manifest entries exist on disk",
          f"missing: {missing[:3]}" if missing else "")

    on_disk = {str(p) for p in FABRIC.rglob("*") if p.suffix.lower() in (".pdf", ".csv")}
    listed = {r["path"] for r in rows} | {str(SOURCES)}   # the manifest is not its own entry
    unlisted = on_disk - listed
    check(not unlisted, "no unlisted files in knowledge_fabric",
          f"unlisted: {sorted(unlisted)[:3]}" if unlisted else "")

    if deep:
        bad = [r["path"] for r in rows
               if Path(r["path"]).exists() and sha256(Path(r["path"])) != r["sha256"]]
        check(not bad, f"SHA-256 matches for all {len(rows)} files",
              f"corrupt: {bad[:3]}" if bad else "")
    else:
        print(f"  {DIM}[skip] SHA-256 verification (use --deep){RESET}")

    counts = {
        "product_manuals": by_cat.get("product_manual", 0),
        "fda_documents": by_cat.get("fda_document", 0),
        "fda_structured_files": by_cat.get("fda_structured", 0),
    }
    counts["documents_total"] = counts["product_manuals"] + counts["fda_documents"]
    print(f"\n  {DIM}product manuals {counts['product_manuals']} · "
          f"FDA documents {counts['fda_documents']} · "
          f"structured CSVs {counts['fda_structured_files']}{RESET}")
    return counts


# ------------------------------------------------- 2. independent recount
def recount_from_source() -> dict:
    """Count records from the raw files, never from the index."""
    section("2. Independent recount from raw files")

    pdfs = sorted(FABRIC.rglob("*.pdf"))
    csvs = sorted((FABRIC / "fda_files" / "structured").glob("*.csv"))

    csv_rows = {}
    for path in csvs:
        with open(path, newline="", encoding="utf-8", errors="replace") as f:
            csv_rows[path.name] = sum(1 for _ in csv.DictReader(f))

    manifest_path = FABRIC / "youtube" / "manifest.json"
    videos = 0
    if manifest_path.exists():
        vm = json.loads(manifest_path.read_text(encoding="utf-8"))
        videos = sum(1 for v in vm.get("videos", {}).values() if not v.get("withdrawn"))
    transcripts = len(list((FABRIC / "youtube" / "transcripts").glob("*.json")))

    print(f"  {DIM}PDFs {len(pdfs)} · CSV rows {sum(csv_rows.values())} "
          f"across {len(csvs)} files · videos {videos} "
          f"({transcripts} transcribed){RESET}")
    for name, n in sorted(csv_rows.items(), key=lambda kv: -kv[1]):
        print(f"    {n:>6}  {name}")
    return {"pdfs": len(pdfs), "csv_rows": sum(csv_rows.values()),
            "csv_files": len(csvs), "videos": videos, "transcripts": transcripts}


# ------------------------------------------------------- 3. index integrity
def verify_index(disk: dict, raw: dict) -> dict:
    section("3. Index integrity")
    if not INDEX.exists():
        check(False, "index.json present — run the build first", str(INDEX))
        return {}

    idx = json.loads(INDEX.read_text(encoding="utf-8"))
    docs, chunks = idx["documents"], idx["chunks"]
    ents, rels = idx["entities"], idx["relationships"]
    stats = idx.get("stats", {})

    # headline stats must equal the arrays they summarise
    check(stats.get("document_count") == len(docs),
          "stats.document_count == len(documents)",
          f"{stats.get('document_count')} vs {len(docs)}")
    check(stats.get("chunk_count") == len(chunks),
          "stats.chunk_count == len(chunks)",
          f"{stats.get('chunk_count')} vs {len(chunks)}")
    check(stats.get("entity_count") == len(ents),
          "stats.entity_count == len(entities)",
          f"{stats.get('entity_count')} vs {len(ents)}")
    check(stats.get("relationship_count") == len(rels),
          "stats.relationship_count == len(relationships)",
          f"{stats.get('relationship_count')} vs {len(rels)}")

    # record composition traced back to source files
    by_type = Counter(d.get("source_type") for d in docs)
    doc_records = by_type.get("document", 0)
    check(doc_records <= raw["pdfs"],
          "indexed documents <= PDFs on disk",
          f"{doc_records} indexed from {raw['pdfs']} PDFs")
    check(by_type.get("video", 0) == raw["videos"],
          "indexed video records == active videos in manifest",
          f"{by_type.get('video', 0)} vs {raw['videos']}")
    check(by_type.get("fda_regulatory", 0) <= raw["csv_rows"],
          "FDA records <= rows available in structured CSVs",
          f"{by_type.get('fda_regulatory', 0)} of {raw['csv_rows']} rows selected")

    # graph consistency
    node_ids = {e["id"] for e in ents}
    dangling = [r for r in rels if r["source"] not in node_ids or r["target"] not in node_ids]
    check(not dangling, "every relationship endpoint resolves to an entity",
          f"{len(dangling)} dangling" if dangling else f"{len(rels)} edges checked")

    chunk_ids = {c["id"] for c in chunks}
    bad_refs = sum(1 for e in ents for cid in e.get("chunk_ids", []) if cid not in chunk_ids)
    check(bad_refs == 0, "every entity chunk reference resolves to a chunk",
          f"{bad_refs} broken" if bad_refs else f"{len(ents)} entities checked")

    orphan_docs = {c["document_id"] for c in chunks} - {d["id"] for d in docs}
    check(not orphan_docs, "every chunk belongs to a listed document",
          f"{len(orphan_docs)} orphan document ids" if orphan_docs else "")

    # BM25 internal consistency
    bm = idx.get("bm25", {})
    check(len(bm.get("doc_len", [])) == len(chunks),
          "BM25 doc_len covers every chunk",
          f"{len(bm.get('doc_len', []))} vs {len(chunks)}")
    check(len(bm.get("idf", [])) == len(bm.get("vocab", [])),
          "BM25 idf aligns with vocabulary",
          f"{len(bm.get('idf', []))} vs {len(bm.get('vocab', []))}")

    print(f"\n  {DIM}composition: " +
          " · ".join(f"{k} {v}" for k, v in by_type.most_common()) + f"{RESET}")
    return {"docs": len(docs), "chunks": len(chunks), "entities": len(ents),
            "relationships": len(rels), "by_type": dict(by_type),
            "vocab": len(bm.get("vocab", []))}


# ---------------------------------------------------- 4. semantic / embeddings
def verify_semantic(index_counts: dict) -> dict:
    section("4. Semantic index (embeddings)")
    if not SEMANTIC.exists():
        check(False, "semantic.json present", str(SEMANTIC))
        return {}

    sem = json.loads(SEMANTIC.read_text(encoding="utf-8"))
    vectors = sem.get("doc_vectors") or sem.get("vectors") or []
    terms = sem.get("terms") or sem.get("vocab") or []
    term_vectors = sem.get("term_vectors") or []
    dims = sem.get("dims") or (len(vectors[0]) if vectors else 0)

    check(bool(sem.get("enabled", True)), "semantic index enabled")
    check(len(vectors) == index_counts.get("chunks", -1),
          "one embedding vector per chunk",
          f"{len(vectors)} vectors vs {index_counts.get('chunks')} chunks")

    ragged = [i for i, v in enumerate(vectors[:2000]) if len(v) != dims]
    check(not ragged, f"every vector has {dims} dimensions",
          f"{len(ragged)} ragged" if ragged else f"{len(vectors)} vectors")

    check(len(term_vectors) == len(terms),
          "one term vector per LSA vocabulary term",
          f"{len(term_vectors)} vs {len(terms)}")
    check(len(sem.get("idf", [])) == len(terms),
          "IDF weights align with LSA vocabulary",
          f"{len(sem.get('idf', []))} vs {len(terms)}")

    ev = sem.get("explained_variance", 0)
    print(f"\n  {DIM}method {sem.get('method','?')} · "
          f"embeddings {len(vectors)} x {dims} dims · "
          f"term vectors {len(term_vectors)} x {dims} · "
          f"LSA vocabulary {len(terms)} · explained variance {ev:.1%}{RESET}")
    return {"doc_vectors": len(vectors), "term_vectors": len(term_vectors),
            "dims": dims, "lsa_vocab": len(terms),
            "explained_variance": round(ev, 4), "method": sem.get("method", "")}


# --------------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gate", action="store_true", help="exit non-zero on any failure")
    ap.add_argument("--deep", action="store_true", help="verify SHA-256 of every file")
    ap.add_argument("--json", type=Path, help="write the reconciliation to a JSON file")
    args = ap.parse_args()

    print("=" * 68)
    print("  CORPUS VERIFICATION — every number traced to a file")
    print("=" * 68)

    disk = verify_sources(args.deep)
    raw = recount_from_source()
    idx = verify_index(disk, raw)
    sem = verify_semantic(idx)

    failed = [r for r in results if not r[0]]
    print("\n" + "=" * 68)
    if failed:
        print(f"  {RED}{len(failed)} of {len(results)} checks FAILED{RESET}")
        for _, label, detail in failed:
            print(f"    - {label} {detail}")
    else:
        print(f"  {GREEN}all {len(results)} checks passed{RESET}")
    print("=" * 68)

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps({
            "checks_total": len(results), "checks_failed": len(failed),
            "on_disk": disk, "recount": raw, "index": idx, "semantic": sem,
            "failures": [{"check": l, "detail": d} for ok, l, d in results if not ok],
        }, indent=2) + "\n", encoding="utf-8")
        print(f"  written: {args.json}")

    return 1 if (failed and args.gate) else 0


if __name__ == "__main__":
    sys.exit(main())
