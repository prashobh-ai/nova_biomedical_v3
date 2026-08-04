# Setting up novabiomedical_v3

The zip contains everything except the 82 PDFs (133 MB — too large to ship, and
they are all publicly fetchable). Step 2 below restores them, checksum-verified,
and then you commit the whole thing so the raw data lives in the repo.

---

## 1. Unzip and install

```bash
unzip novabiomedical_v3.zip
cd novabiomedical_v3
pip install -r pipeline/requirements.txt
```

## 2. Restore the corpus  ← do this before the first commit

```bash
python scripts/fetch_corpus.py
```

Downloads all 82 documents and verifies each SHA-256 against
`knowledge_fabric/SOURCES.csv`. Roughly 133 MB, a few minutes. Sources:

| Count | From |
|---:|---|
| 12 | `novabiomedicaldocs.com` — product IFUs and manuals |
| 38 | `accessdata.fda.gov` — 510(k) summaries |
| 41 | `raw.githubusercontent.com/prashobh-ai/novabiomedical_v2` — files carried over from v2 |

All 91 URLs were HEAD-verified when the manifest was built. Expect:

```
verified 9 · fetched 82 · missing 0 · failed 0 · checksum issues 0
corpus complete and byte-identical to the manifest
```

If anything fails, the file is still recoverable from the v2 repo by hand — but
`fetch_corpus.py` is idempotent, so just run it again first.

## 3. Confirm the numbers

```bash
python scripts/verify_corpus.py --deep
```

Expect **all 19 checks passed**. `--deep` checksums every file. This is the
command to run in front of a client who asks whether the numbers are real.

## 4. Build and preview

```bash
python -m pipeline.build_index
cd site && python -m http.server 8000
```

The build takes 3–5 minutes. Index artifacts are gitignored — CI rebuilds them on
every push.

## 5. Create the repo

```bash
git init
git add .
git commit -m "feat: Knowledge Fabric v3 — multi-source corpus with verified provenance"
git branch -M main
git remote add origin https://github.com/prashobh-ai/novabiomedical_v3.git
git push -u origin main
```

`.gitignore` deliberately does **not** exclude `knowledge_fabric/`. The raw data
living in the repo is the entire point — the first commit should be ~135 MB, which
is well inside GitHub's limits (100 MB per *file*; the largest here is 32 MB).

## 6. Enable GitHub Pages and Actions

1. **Settings → Pages** → Source: *GitHub Actions*
2. **Settings → Actions → General → Workflow permissions** → *Read and write*
   (the YouTube refresh job commits the updated cache)
3. **Actions** tab → run *Refresh YouTube knowledge source* once manually to
   confirm before relying on the 02:00 UTC schedule

Optional, free, no billing card — makes CI metadata refresh more robust:

- **Settings → Secrets and variables → Actions → Secrets**: `YOUTUBE_API_KEY`
- **Settings → Secrets and variables → Actions → Variables**:
  `YOUTUBE_CHANNEL_ID` = `UC9nZNv6VhSfItRggLrBDqCg`

Without them the daily job still works via yt-dlp + the channel RSS feed, which is
the tested default.

## 7. Transcripts (optional, free, local)

79 videos are indexed on their publisher-written metadata already. Transcripts add
timestamp-level citation — the click-to-the-exact-second evidence:

```bash
python scripts/youtube_transcribe.py --limit 3     # check throughput first
python scripts/youtube_transcribe.py               # 64 English videos, overnight
git add knowledge_fabric/youtube/ && git commit -m "chore: video transcripts"
```

CPU-only, `faster-whisper`, no API key, no cost. GPU: add
`--device cuda --compute-type float16`.

---

## What changed from v2 — the short version

**The problem.** v2's dashboard said *"391 documents · indexed corpus"*. The repo
held 32 PDFs. The other 359 were single CSV rows, and 23 of those were entries in
an IFU *catalogue* — pointers to documents that were not in the repo at all. Anyone
who opened the repo and counted was right to challenge the number.

**The fix, in three parts.**

*More real documents.* The 23 catalogue entries were resolved into actual PDFs (20
fetched; 2 are dead links at the publisher's end), plus 38 further FDA 510(k)
summaries. After content-hash deduplication: **82 real documents, up from 32.**

*Honest labelling.* The headline number is now **records**, never *documents*, and
its composition is stated everywhere it appears: 520 records = 82 documents + 359
regulatory records + 79 video records.

*Verification you can run in the room.* `scripts/verify_corpus.py` recounts records
from the raw files rather than reading them back out of the index, so a figure that
exists only in the index cannot pass. It gates deploys.

| | v2 | v3 |
|---|---:|---:|
| Real documents (PDF) | 32 | **82** |
| Indexed records | 391 | **520** |
| Retrievable passages | 1,314 | **3,551** |
| Entities | 323 | **416** |
| Graph edges | 415 | **446** |
| Embeddings | 1,314 × 96 | **3,551 × 96** |
| Sources | 2 | **3** (+ YouTube) |
| Corpus verification | none | **19 automated checks, gating deploys** |
| Per-file provenance | none | **SHA-256 + verified URL for all 91 files** |

**A real bug, found by scaling.** The v2 build was OOM-killed on the larger corpus.
Cause: `dict.setdefault()` evaluates its default argument eagerly, so
`resolve_date()` ran once per *chunk* (3,551×) instead of once per *document*
(127×) — re-opening and re-parsing every PDF, including a 32 MB manual. Fixed in
`pipeline/build_index.py`, with the reasoning recorded in a comment so it does not
regress.

---

## Answering "show me the raw data"

Open `knowledge_fabric/INVENTORY.md`. It is generated by
`scripts/build_inventory.py`, never hand-written, and lists every file with its
size and origin. Then run:

```bash
python scripts/verify_corpus.py --deep
```

Nineteen checks, each one reconciling a published figure against something on disk:
every manifest entry exists and matches its checksum; no unlisted files; indexed
documents ≤ PDFs present; video records == active videos in the manifest; every
graph edge endpoint resolves; every entity chunk reference resolves; BM25 arrays
aligned with the vocabulary; one embedding per chunk at the stated dimensionality.

The distinction that matters when someone counts: a PDF is one file and one record,
while a CSV export contributes one record per selected row. 359 of roughly 3,200
available rows are indexed — clearances, recalls, classifications and enforcement
actions relevant to these products. The rest stay in the repo, unindexed and
visible.
