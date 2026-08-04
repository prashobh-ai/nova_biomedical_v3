#!/usr/bin/env python3
"""Fetch the document corpus from its official sources and verify every file.

    python scripts/fetch_corpus.py              # fetch anything missing
    python scripts/fetch_corpus.py --verify     # checksum what is already here
    python scripts/fetch_corpus.py --force      # re-fetch everything

`knowledge_fabric/SOURCES.csv` is the contract: for every document it records the
destination path, the official URL it came from, its exact byte size and its
SHA-256. That makes the corpus reproducible and auditable rather than a folder of
PDFs somebody once downloaded — you can prove that the file in this repo is
byte-identical to the one the publisher serves.

Run this once after cloning if the PDFs are not present, then commit them. Every
document is public: Nova Biomedical product literature from novabiomedicaldocs.com
and 510(k) summaries from accessdata.fda.gov.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import ssl
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

SOURCES = Path("knowledge_fabric/SOURCES.csv")

# novabiomedicaldocs.com applies bot protection and will return 403 to a bare
# User-Agent or to rapid sequential requests. Browser-like headers plus backoff
# make the fetch reliable; a Referer is required for some of its paths.
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"),
    "Accept": "application/pdf,text/csv,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
}
RETRY_STATUS = {403, 408, 429, 500, 502, 503, 504}
MAX_ATTEMPTS = 4


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def fetch(url: str, dest: Path, ctx) -> tuple[bool, str]:
    """Fetch with exponential backoff. Rate limiting is the common failure here,
    and it is transient — retrying beats failing the whole corpus restore."""
    referer = "/".join(url.split("/")[:3]) + "/"
    headers = {**HEADERS, "Referer": referer}
    last = ""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=120, context=ctx) as resp:
                data = resp.read()
        except urllib.error.HTTPError as exc:
            last = f"HTTP {exc.code}"
            if exc.code in RETRY_STATUS and attempt < MAX_ATTEMPTS:
                time.sleep(3 * attempt)
                continue
            return False, last
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last = str(exc)[:70]
            if attempt < MAX_ATTEMPTS:
                time.sleep(3 * attempt)
                continue
            return False, last

        if dest.suffix.lower() == ".pdf" and data[:4] != b"%PDF":
            return False, "response was not a PDF"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        return True, ""
    return False, last or "exhausted retries"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true", help="checksum only, fetch nothing")
    ap.add_argument("--force", action="store_true", help="re-fetch even if present")
    ap.add_argument("--delay", type=float, default=0.6,
                    help="seconds between requests; raise if the publisher rate-limits")
    args = ap.parse_args()

    if not SOURCES.exists():
        print(f"missing {SOURCES}", file=sys.stderr)
        return 1

    rows = list(csv.DictReader(open(SOURCES, encoding="utf-8")))
    ctx = ssl.create_default_context()

    present = missing = repaired = failed = corrupt = 0
    problems: list[str] = []

    for r in rows:
        dest = Path(r["path"])
        want = r["sha256"]
        url = (r.get("source_url") or "").strip()

        if dest.exists() and not args.force:
            got = sha256(dest)
            if got == want:
                present += 1
                continue
            corrupt += 1
            print(f"  [checksum mismatch] {dest.name}")
            if args.verify:
                problems.append(f"{dest} checksum mismatch")
                continue
        elif args.verify:
            missing += 1
            problems.append(f"{dest} missing")
            continue

        if not url:
            # Files with no public URL must be carried in the repo itself.
            missing += 1
            problems.append(f"{dest} missing and has no source_url — restore from git")
            print(f"  [no url] {dest.name}")
            continue

        ok, err = fetch(url, dest, ctx)
        if ok and sha256(dest) == want:
            repaired += 1
            print(f"  [ok] {dest.name}")
        elif ok:
            corrupt += 1
            problems.append(f"{dest} fetched but checksum differs from manifest")
            print(f"  [checksum differs after fetch] {dest.name}")
        else:
            failed += 1
            problems.append(f"{dest}: {err}")
            print(f"  [fail] {dest.name}: {err}")
        time.sleep(args.delay)

    print()
    print(f"  verified {present} · fetched {repaired} · missing {missing} · "
          f"failed {failed} · checksum issues {corrupt}")
    if problems:
        print("\n  problems:")
        for p in problems[:20]:
            print(f"    - {p}")
        return 1
    print("  corpus complete and byte-identical to the manifest")
    return 0


if __name__ == "__main__":
    sys.exit(main())
