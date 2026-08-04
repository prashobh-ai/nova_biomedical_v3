<h2 align="center">Nova Biomedical</h2>

<h1 align="center">Knowledge Fabric</h1>

<p align="center">
Transforming enterprise knowledge into an explainable, evaluated intelligence network
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Phase-3%20Multi--Source-blue" />
  <img src="https://img.shields.io/badge/Corpus-Verified-brightgreen" />
  <img src="https://img.shields.io/badge/Knowledge%20Graph-Typed-purple" />
  <img src="https://img.shields.io/badge/Answers-Citation%20Backed-orange" />
  <img src="https://img.shields.io/badge/Retrieval-Evaluated-red" />
</p>

---

## The corpus, in numbers you can check

| | Files in this repo | Indexed records |
|---|---:|---:|
| Product manuals (PDF) | 20 | 20 |
| FDA 510(k) documents (PDF) | 62 | 62 |
| FDA structured exports (CSV) | 9 files | 359 rows selected |
| YouTube videos (company channel) | 79 | 79 |
| **Total** | **91 files · 138.8 MB** | **520 records** |

Derived at build time: **3,551** retrievable passages · **416** entities ·
**446** graph edges · **3,551 × 96** embeddings · **13,308**-term lexical vocabulary ·
**36,104** classified sentences.

**"520 records" is not "520 documents".** It is 82 documents + 359 regulatory
records + 79 video records. The distinction is deliberate and is stated everywhere
the number appears — a PDF is one file and one record, while a CSV export
contributes one record per selected row. `knowledge_fabric/INVENTORY.md` lists
every file, and every total above is reproducible:

```bash
python scripts/verify_corpus.py --deep
```

That command recounts records from the raw files rather than reading them back out
of the index, checksums all 91 files against `knowledge_fabric/SOURCES.csv`, and
fails if any published figure cannot be traced to something on disk. It runs as a
deploy gate, so a number that stops reconciling stops the release.

---

## Why Knowledge Fabric

Enterprise knowledge is scattered across documents, regulatory filings, and media.
Traditional search helps you find *documents*.

**Knowledge Fabric finds answers, relationships, and evidence — and shows its
working.** Every sentence in an answer is quoted from a source and carries a
four-level address back to it: document → page → section → paragraph, or for
video, playlist → video → timestamp → sentence.

The distinguishing claim is testable: *can it answer a question no single source
system can answer alone?* With 11 products appearing across product manuals, FDA
filings and channel media, it can — and `eval/` proves it on every deploy.

---

## Repository layout

```
knowledge_fabric/            all source data, segregated by origin
├── product_manuals/         20 IFU and reference manuals (PDF)
├── fda_files/
│   ├── documents/           62 FDA 510(k) clearance and review documents (PDF)
│   └── structured/          9 openFDA CSV exports
├── youtube/
│   ├── manifest.json        79 videos: titles, dates, playlist facets
│   └── transcripts/         timestamped transcripts (see below)
├── SOURCES.csv              every file: URL, byte size, SHA-256
└── INVENTORY.md             generated listing — the answer to "show me the data"

pipeline/                    ingestion, indexing, graph, semantics
├── connectors/              one per source; the pipeline never learns what a CSV is
│   ├── base.py              KnowledgeRecord contract + registry
│   ├── documents.py         PDF / DOCX / MD / TXT, heading-aware, page-accurate
│   ├── fda.py               structured records verbalised for retrieval
│   └── youtube.py           channel metadata + timestamped transcript segments
├── build_index.py           orchestrator
├── docmeta.py               date resolution with provenance and honest gaps
├── textnorm.py              PDF text repair + sentence classification
├── chunker.py               passage packing
├── bm25_index.py            lexical retrieval
├── semantic.py              LSA embeddings
└── graph.py                 typed cross-source knowledge graph

scripts/
├── verify_corpus.py         reconciles every number against the repo  ← deploy gate
├── build_inventory.py       regenerates INVENTORY.md
├── fetch_corpus.py          restores documents from official URLs, checksum-verified
├── youtube_refresh.py       daily metadata reconcile (scheduled)
└── youtube_transcribe.py    local ASR backfill (free, offline)

site/                        static client — no backend, no inference at answer time
eval/                        retrieval evaluation harness; gates deploys
tests/                       pipeline unit tests + browser contract test
```

---

## Quick start

```bash
pip install -r pipeline/requirements.txt

# 1. confirm the corpus is intact (or restore it — see note below)
python scripts/fetch_corpus.py --verify

# 2. build
python -m pipeline.build_index

# 3. check every published number against the files
python scripts/verify_corpus.py --deep

# 4. serve
cd site && python -m http.server 8000
```

**If the PDFs are absent** (a fresh clone that excluded them), `python
scripts/fetch_corpus.py` restores all documents that have a public URL — 59 of 91
files — directly from `novabiomedicaldocs.com` and `accessdata.fda.gov`, verifying
each SHA-256 against the manifest. The remaining 32 have no stable public URL and
are carried in the repository itself.

---

## What is running

| Capability | Status | Implementation |
|---|---|---|
| Multi-source ingestion | Live | `pipeline/connectors/` — pluggable contract, 3 connectors |
| Document intelligence | Live | PDF/DOCX/MD/TXT, heading-aware, page-accurate |
| Structured-record ingestion | Live | openFDA records verbalised for retrieval |
| Video ingestion | Live | Channel metadata + playlist facets; transcripts opt-in |
| Timestamp-level citation | Live | `watch?v=ID&t=NNNs` beside the sentence spoken there |
| Lexical retrieval | Live | BM25, client-side |
| Semantic retrieval | Live | LSA, 96 dims, 42.4% variance retained |
| Hybrid fusion | Live | Reciprocal rank fusion |
| Typed knowledge graph | Live | 416 entities, 446 edges, 6 relationship types |
| Date provenance | Live | 6 resolution methods, each with a confidence band |
| Corpus verification | Live | `scripts/verify_corpus.py`, gates deploys |
| Retrieval evaluation | Live | `eval/`, gates deploys |

---

## Evidence tiers

Not all knowledge is equally provable, and the fabric records the difference
rather than flattening it:

| Tier | Sources | How it is cited |
|---|---|---|
| `publisher_authored` | Manuals, FDA filings, video titles and descriptions | Document → page → section → paragraph |
| `machine_transcribed` | Video transcripts (ASR) | Playlist → video → timestamp, marked as transcribed, one click to the second it was spoken |

A machine transcript can support an answer, but it is always labelled, and its
citation lands on the audio so a reader can verify it directly. That is a stronger
verification affordance than a page number, not a weaker one.

---

## YouTube: daily refresh

`.github/workflows/refresh_youtube.yml` runs daily at 02:00 UTC. It fetches
metadata only — never audio — reconciles against the manifest, and commits when
the channel changes. That commit triggers the normal deploy, so builds stay
deterministic: `build_index` only ever reads committed files.

Dates resolve in priority order: YouTube Data API (if a key is set) → channel RSS
feed (works from CI, covers recent uploads) → carry-forward → run date, recorded
as a distinct lower-confidence method and never presented as a publication date.

Transcription is a separate local step, because YouTube throttles datacentre IPs
for audio:

```bash
python scripts/youtube_transcribe.py --limit 3    # sanity check
python scripts/youtube_transcribe.py              # full queue, overnight, free
```

It uses `faster-whisper` on CPU with a domain-primed prompt and corrects against
the corpus's own vocabulary — no paid API and no LLM in the loop.

---

## Design notes

**No inference at answer time.** Retrieval is BM25 + LSA, both classical; answers
are extractive. The site is static. That is why it deploys to GitHub Pages at zero
cost, and why answers are quotable rather than generated.

**Exclusions are documented, not silent.** Freshness scoring excludes event-dated
regulatory records because a 1989 clearance is a historical fact, not stale
knowledge. Undated documents are excluded rather than assumed old. Every exclusion
is stated where the score is shown.

**Provenance beats convenience.** `SOURCES.csv` carries a SHA-256 for every file
so the corpus is reproducible rather than a folder someone once downloaded.
`docmeta.py` reports `null` for an unrecoverable date instead of a plausible guess.
